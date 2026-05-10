"""
Composable node filters and event transforms for building an information-flow tensor used for NTF.

Two pipeline primitives:
    * NodeFilter   - keep-only; computes a kept set from NodeStats; the runner drops every
                     event whose src or dst is not in the kept set. Used to exclude
                     ephemeral nodes which do not exhibit meaningful temporal patterns.
    * EventTransform - rewrite events (uuid remapping, edge dropping). Implemented because
                       collapsing ephemeral processes into their parents is fundamentally
                       a remap, not a filter. Has access to an ObjectLookup so it can
                       reason about role and parent_uuid chains.

Both are applied sequentially by 'filtered_graph_builder.build_filtered_host_graphs';
each step gets the state left by earlier steps.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from provenance_explorer.common_record.object_lookup import (
    ObjectLookup, ObjectRoleCompact, bytes_to_uuid,
)


@dataclass
class NodeStats:
    """Per-node summary recomputed on the current event list before each filter."""
    degree: Dict[str, int] # total endpoint count (src + dst)
    bins_active: Dict[str, Set[int]] # distinct bin indices the node touches
    first_bin: Dict[str, int]
    last_bin: Dict[str, int]

    @classmethod
    def from_events(cls, events: List[Tuple[int, str, str]]) -> "NodeStats":
        degree: Dict[str, int] = defaultdict(int)
        bins_active: Dict[str, Set[int]] = defaultdict(set)
        first_bin: Dict[str, int] = {}
        last_bin: Dict[str, int] = {}
        for b, s, d in events:
            for u in (s, d):
                degree[u] += 1
                bins_active[u].add(b)
                if u not in first_bin or b < first_bin[u]:
                    first_bin[u] = b
                if u not in last_bin or b > last_bin[u]:
                    last_bin[u] = b
        return cls(degree=dict(degree), bins_active=dict(bins_active),
                   first_bin=first_bin, last_bin=last_bin)


class NodeFilter(ABC):
    """
    Subclasses implement 'keep(stats, n_bins) -> kept_uuids'.
    The runner then drops every event whose src or dst is not in 'kept_uuids'.
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def keep(self, stats: NodeStats, n_bins: int) -> Set[str]: ...

    def describe(self) -> str:
        return self.name


class PersistenceFilter(NodeFilter):
    """Keep only nodes active in at least 'min_bins' distinct time bins."""
    def __init__(self, min_bins: int):
        if min_bins < 1:
            raise ValueError("min_bins must be >= 1")
        self.min_bins = min_bins

    def keep(self, stats: NodeStats, n_bins: int) -> Set[str]:
        return {u for u, bins in stats.bins_active.items() if len(bins) >= self.min_bins}

    def describe(self) -> str:
        return f"Persistence(min_bins={self.min_bins})"


class ActivityFloorFilter(NodeFilter):
    """
    Keep nodes whose degree is larger than min_events (or alternatively a relative quantile).
    """
    def __init__(self, min_events: Optional[int] = None, quantile: Optional[float] = None):
        if min_events is None and quantile is None:
            raise
        if quantile is not None and not (0.0 <= quantile < 1.0):
            raise
        self.min_events = min_events
        self.quantile = quantile

    def keep(self, stats: NodeStats, n_bins: int) -> Set[str]:
        if not stats.degree:
            return set()
        thr = 1
        if self.min_events is not None:
            thr = max(thr, self.min_events)
        if self.quantile is not None:
            import numpy as np
            degs = np.fromiter(stats.degree.values(), dtype=np.int64)
            thr = max(thr, int(np.quantile(degs, self.quantile)))
        return {u for u, d in stats.degree.items() if d >= thr}

    def describe(self) -> str:
        return f"ActivityFloor(min_events={self.min_events}, quantile={self.quantile})"


# class LifespanFilter(NodeFilter):
#     """
#     (last_bin - first_bin + 1) / n_bins >= 'min_span_frac'.
#     """

#     def __init__(self, min_span_frac: float):
#         if not (0.0 < min_span_frac <= 1.0):
#             raise ValueError("min_span_frac must be in (0, 1]")
#         self.min_span_frac = min_span_frac

#     def keep(self, stats: NodeStats, n_bins: int) -> Set[str]:
#         if n_bins <= 0:
#             return set()
#         need = self.min_span_frac * n_bins
#         return {
#             u for u in stats.first_bin
#             if (stats.last_bin[u] - stats.first_bin[u] + 1) >= need
#         }

#     def describe(self) -> str:
#         return f"Lifespan(min_span_frac={self.min_span_frac})"


class TopKFilter(NodeFilter):
    """
    'max_nodes' nodes logic, keeping nodes with highest degree.
    """
    def __init__(self, max_nodes: int):
        if max_nodes < 1:
            raise
        self.max_nodes = max_nodes

    def keep(self, stats: NodeStats, n_bins: int) -> Set[str]:
        if len(stats.degree) <= self.max_nodes:
            return set(stats.degree.keys())
        ordered = sorted(stats.degree.items(), key=lambda kv: (-kv[1], kv[0]))
        return {u for u, _ in ordered[: self.max_nodes]}

    def describe(self) -> str:
        return f"TopK(max_nodes={self.max_nodes})"


# Event transforms (uuid remapping, edge dropping)


class EventTransform(ABC):
    """Pipeline step that *rewrites* events instead of just filtering them.

    Returns ``(new_events, info)`` where ``info`` is a small flat dict suitable for the
    pipeline funnel DataFrame plus an optional ``"extra"`` key holding non-flat data
    (e.g. a remap dict) that the builder stashes in per-host meta rather than the funnel.
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def apply(
        self,
        events: List[Tuple[int, str, str]],
        n_bins: int,
        lookup: Optional[ObjectLookup],
    ) -> Tuple[List[Tuple[int, str, str]], Dict[str, Any]]: ...

    def describe(self) -> str:
        return self.name


def _resolve_to_in_slice_ancestor(
    seed_uuid: str,
    *,
    lookup: ObjectLookup,
    in_slice: Set[str],
    is_ephemeral: Set[str],
    max_depth: int,
) -> Tuple[List[str], bool]:
    """Walk parent_uuid chain from seed_uuid up to max_depth steps.

    Returns ``(chain, found_stable)`` where:
        * chain[0] == seed_uuid; each subsequent entry is the parent_uuid (uppercase
          dashed string) one step up, restricted to nodes that are in `in_slice`.
        * found_stable is True iff the last entry of `chain` is a non-ephemeral node
          (i.e. survives `min_bins`). False means we exhausted the chain or hit
          max_depth without ever leaving the ephemeral set.

    The chain stops as soon as it reaches a non-ephemeral node, at max_depth, when the
    next parent is not in the slice, when there is no parent_uuid, or on a cycle.
    """
    chain: List[str] = [seed_uuid]
    visited: Set[str] = {seed_uuid}
    cur = seed_uuid
    for _ in range(max_depth):
        info = lookup.get_str(cur)
        if info is None or info.parent_uuid is None:
            break
        try:
            par = bytes_to_uuid(info.parent_uuid).upper()
        except Exception:
            break
        if par in visited:  # cycle
            break
        if par not in in_slice:
            break
        visited.add(par)
        chain.append(par)
        cur = par
        if cur not in is_ephemeral:
            return chain, True
    found_stable = chain[-1] not in is_ephemeral
    return chain, found_stable


class CollapseEphemeralProcesses(EventTransform):
    """Collapse ephemeral *process* nodes into their parent process via FORK/parent_uuid.

    Motivation:
        ``PersistenceFilter(min_bins=K)`` butchers graphs because legitimate process
        families (cron jobs, build trees, ssh forks, systemd-spawned helpers) consist
        of many short-lived child processes whose individual bin-coverage is < K but
        whose collective behaviour is highly regular. Dropping them throws away most
        of the host's information flow. Collapsing each ephemeral process into its
        deepest in-slice ancestor preserves that flow as the activity of the family.

    Algorithm:
        1. Compute per-node bin coverage from the current event list.
        2. Mark a node "ephemeral" if it appears in fewer than ``min_bins`` distinct
           bins. Of those, only ``role == PROCESS`` (per ``ObjectLookup``) are
           candidates - non-process ephemerals (one-shot tmp files, transient
           sockets) are left alone for downstream filters.
        3. For each candidate, walk ``parent_uuid`` upward (in `lookup`) at most
           ``max_depth`` steps, restricted to nodes that are in the current slice.
           Union-find merges the candidate into its deepest reachable in-slice
           ancestor; if that ancestor is itself ephemeral, the union still happens
           so siblings can aggregate.
        4. Rewrite events by replacing every collapsed source/destination uuid with
           its representative.
        5. Drop self-loops produced by step 4 (FORK edges parent->child become
           parent->parent and carry no information).

    Notes:
        * EXECUTE edges target the executable *image* (FILE), not the child process,
          so they survive the collapse intact.
        * The transform must run *before* ``PersistenceFilter`` to be useful;
          afterwards there is nothing left to merge.
    """

    def __init__(self, min_bins: int, max_depth: int = 8):
        if min_bins < 1:
            raise ValueError("min_bins must be >= 1")
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        self.min_bins = min_bins
        self.max_depth = max_depth

    def describe(self) -> str:
        return f"CollapseEphemeralProcesses(min_bins={self.min_bins}, max_depth={self.max_depth})"

    def apply(
        self,
        events: List[Tuple[int, str, str]],
        n_bins: int,
        lookup: Optional[ObjectLookup],
    ) -> Tuple[List[Tuple[int, str, str]], Dict[str, Any]]:
        if lookup is None:
            raise ValueError(
                f"{self.name} requires an ObjectLookup; pass one to "
                "build_filtered_host_graphs(..., object_lookup=...)"
            )

        if not events:
            return events, {
                "n_candidates": 0, "n_collapsed": 0, "n_self_loops_dropped": 0,
                "n_groups": 0, "max_group_size": 0, "extra": {"remap": {}},
            }

        stats = NodeStats.from_events(events)
        in_slice: Set[str] = set(stats.bins_active.keys())
        # Normalise: all uuids in the slice are expected uppercase already, but be
        # defensive so downstream comparisons against bytes_to_uuid (which returns
        # uppercase) line up.
        if any(u != u.upper() for u in in_slice):
            in_slice = {u.upper() for u in in_slice}

        is_ephemeral: Set[str] = {
            u for u, bins in stats.bins_active.items() if len(bins) < self.min_bins
        }
        # Restrict candidates to PROCESS role
        candidates: List[str] = []
        for u in is_ephemeral:
            info = lookup.get_str(u)
            if info is None:
                continue
            if info.role == ObjectRoleCompact.PROCESS:
                candidates.append(u)

        # Union-find with parent always becoming the canonical root
        parent_of: Dict[str, str] = {u: u for u in in_slice}

        def _find(u: str) -> str:
            root = u
            while parent_of[root] != root:
                root = parent_of[root]
            # path compression
            while parent_of[u] != root:
                nxt = parent_of[u]
                parent_of[u] = root
                u = nxt
            return root

        def _union_to_parent(child: str, par: str) -> None:
            rc, rp = _find(child), _find(par)
            if rc != rp:
                parent_of[rc] = rp

        for u in candidates:
            chain, _ = _resolve_to_in_slice_ancestor(
                u, lookup=lookup, in_slice=in_slice,
                is_ephemeral=is_ephemeral, max_depth=self.max_depth,
            )
            # walk pairs (chain[i], chain[i+1]) and union child->parent
            for child, par in zip(chain[:-1], chain[1:]):
                _union_to_parent(child, par)

        # Build the remap (only entries whose root != self)
        remap: Dict[str, str] = {}
        for u in candidates:
            r = _find(u)
            if r != u:
                remap[u] = r

        # Rewrite events
        new_events: List[Tuple[int, str, str]] = []
        n_self_loops = 0
        if remap:
            for b, s, d in events:
                ns = remap.get(s, s)
                nd = remap.get(d, d)
                if ns == nd:
                    n_self_loops += 1
                    continue
                new_events.append((b, ns, nd))
        else:
            new_events = events

        # Group sizes for diagnostics
        group_sizes: Dict[str, int] = defaultdict(int)
        for u, t in remap.items():
            group_sizes[t] += 1
        # +1 for the representative itself (only if it was actually collapsed-into)
        for t in list(group_sizes.keys()):
            group_sizes[t] += 1
        max_group = max(group_sizes.values()) if group_sizes else 0

        info = {
            "n_candidates": len(candidates),
            "n_collapsed": len(remap),
            "n_self_loops_dropped": n_self_loops,
            "n_groups": len(group_sizes),
            "max_group_size": max_group,
            "extra": {
                "remap": remap,
                "group_sizes": dict(group_sizes),
            },
        }
        return new_events, info

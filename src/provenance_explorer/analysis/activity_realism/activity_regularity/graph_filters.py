"""
Composable node filters for building an information-flow tensor used for NTF. 
Filters are applied sequentially by 'filtered_graph_builder.build_filtered_host_graphs'; 
Each filter gets the state left by earlier filters.

This is mainly meant to exclude ephemaral nodes, as they do not exhibit meaningful temporal patterns. 
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


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

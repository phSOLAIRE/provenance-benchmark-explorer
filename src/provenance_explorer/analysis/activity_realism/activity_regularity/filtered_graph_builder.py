"""
Per-host information-flow tensors with a pluggable filter pipeline.

    - accepts an explicit list of filters rather than a single top-K cap,
    - reports per-stage (N, n_events, kept fractions) as a DataFrame,
    - can target a specific host to avoid buffering data for unrelated ones.
"""
from __future__ import annotations

import gc
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from provenance_explorer.common_record import iterate_common_records, DropLog
from provenance_explorer.common_record.schema import EdgeCategory
from provenance_explorer.common_record.object_lookup import ObjectLookup

from provenance_explorer.analysis.activity_realism.activity_regularity.mttkrp_helpers import (
    SparseTensor3,
    build_sparse_tensor,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.graph_filters import (
    EventTransform,
    NodeFilter,
    NodeStats,
    TopKFilter,
)

PipelineStep = object  # Union[NodeFilter, EventTransform]

FLOW_DIRECTION = {
    EdgeCategory.FORK:    True,
    EdgeCategory.EXECUTE: False,
    EdgeCategory.READ:    False,
    EdgeCategory.WRITE:   True,
    EdgeCategory.SEND:    True,
    EdgeCategory.RECV:    False,
}

NS_PER_SEC = 1_000_000_000
DEFAULT_BIN_WIDTH_NS = 60 * NS_PER_SEC

DEFAULT_MAX_NODES_FALLBACK = 10_000

def _collect_events(
    dataset: str,
    sub_dataset: str,
    start_ns: int,
    end_ns: int,
    bin_width_ns: int,
    host_ids: Optional[Sequence[str]],
) -> Tuple[Dict[str, List[Tuple[int, str, str]]], int]:
    """Single pass over common records -> per-host list of (bin, src, dst)."""
    n_bins = int((end_ns - start_ns) // bin_width_ns) + 1
    wanted = set(host_ids) if host_ids is not None else None

    raw: Dict[str, List[Tuple[int, str, str]]] = defaultdict(list)
    logger = DropLog()
    n_total = 0
    for rec in iterate_common_records(
        dataset, sub_dataset, drop_log=logger, t_start=start_ns, t_end=end_ns,
    ):
        if wanted is not None and rec.host_id not in wanted:
            continue
        cat = rec.edge_category
        if cat not in FLOW_DIRECTION:
            continue
        if FLOW_DIRECTION[cat]:
            src, dst = rec.subject_uuid, rec.object_uuid
        else:
            src, dst = rec.object_uuid, rec.subject_uuid
        b = int((rec.timestamp_ns - start_ns) // bin_width_ns)
        if 0 <= b < n_bins:
            raw[rec.host_id].append((b, src, dst))
            n_total += 1
        if n_total and n_total % 10_000_000 == 0:
            print(f"\t{n_total / 1e6:.0f}M records ingested")

    logger.summary(dataset, sub_dataset)
    return raw, n_bins


def _apply_pipeline(
    events: List[Tuple[int, str, str]],
    n_bins: int,
    pipeline: Sequence[object],
    object_lookup: Optional[ObjectLookup] = None,
) -> Tuple[List[Tuple[int, str, str]], pd.DataFrame, List[Dict[str, object]]]:
    """
    Apply filters sequentially.
    """
    current = events
    initial_stats = NodeStats.from_events(current)
    n0_nodes = len(initial_stats.degree)
    n0_events = len(current)

    rows: List[Dict[str, object]] = [{
        "stage": 0, "filter": "raw",
        "N": n0_nodes, "n_events": n0_events,
        "frac_nodes_kept": 1.0 if n0_nodes else 0.0,
        "frac_events_kept": 1.0 if n0_events else 0.0,
    }]
    transform_extras: List[Dict[str, object]] = []

    for i, step in enumerate(pipeline, start=1):
        if isinstance(step, EventTransform):
            current, info = step.apply(current, n_bins, object_lookup)
            stats_after = NodeStats.from_events(current)
            row: Dict[str, object] = {
                "stage": i, "filter": step.describe(),
                "N": len(stats_after.degree), "n_events": len(current),
                "frac_nodes_kept": (len(stats_after.degree) / n0_nodes) if n0_nodes else 0.0,
                "frac_events_kept": (len(current) / n0_events) if n0_events else 0.0,
            }
            for k, v in info.items():
                if k == "extra":
                    continue
                if isinstance(v, (int, float, str, bool)):
                    row[k] = v
            rows.append(row)
            extras = info.get("extra", {}) if isinstance(info, dict) else {}
            transform_extras.append({"step": i, "name": step.describe(), "extra": extras})
        else:  # NodeFilter
            stats = NodeStats.from_events(current)
            keep = step.keep(stats, n_bins) # type: ignore
            current = [(b, s, d) for (b, s, d) in current if s in keep and d in keep]
            rows.append({
                "stage": i, "filter": step.describe(), # type: ignore
                "N": len(keep), "n_events": len(current),
                "frac_nodes_kept": (len(keep) / n0_nodes) if n0_nodes else 0.0,
                "frac_events_kept": (len(current) / n0_events) if n0_events else 0.0,
            })

    return current, pd.DataFrame(rows), transform_extras


def build_filtered_host_graphs(
    dataset: str,
    sub_dataset: str,
    start_ns: int,
    end_ns: int,
    filters: Sequence[object],
    bin_width_ns: int = DEFAULT_BIN_WIDTH_NS,
    host_ids: Optional[Sequence[str]] = None,
    max_nodes_fallback: Optional[int] = DEFAULT_MAX_NODES_FALLBACK,
    object_lookup: Optional[ObjectLookup] = None,
) -> Dict[str, dict]:
    """
    Build per-host filtered information-flow tensors.

    returns 
    {host_id: {
        "tensor":      SparseTensor3,
        "uuid_to_idx": dict[str,int],
        "idx_to_uuid": dict[int,str],
        "funnel":      pd.DataFrame (stage, filter, N, n_events, ...),
        "meta": {
            "dataset", "sub_dataset", "host_id",
            "N", "N_orig", "S",
            "n_events", "n_events_orig",
            "kept_frac", "bin_width_ns",
            "start_ns", "end_ns",
            "filters": [f.describe() for f in filters],
        },
    }}
    """
    raw_events, n_bins = _collect_events(
        dataset, sub_dataset, start_ns, end_ns, bin_width_ns, host_ids,
    )

    results: Dict[str, dict] = {}
    for hid, events in raw_events.items():
        n_events_orig = len(events)
        n_nodes_orig = len({u for _, s, d in events for u in (s, d)})

        survivors, funnel, transform_extras = _apply_pipeline(
            events, n_bins, filters, object_lookup=object_lookup,
        )

        # hard-cap fallback
        fallback_triggered = False
        if max_nodes_fallback is not None:
            stats = NodeStats.from_events(survivors)
            if len(stats.degree) > max_nodes_fallback:
                fb = TopKFilter(max_nodes_fallback)
                keep = fb.keep(stats, n_bins)
                survivors = [
                    (b, s, d) for (b, s, d) in survivors if s in keep and d in keep
                ]
                fallback_triggered = True
                funnel = pd.concat(
                    [
                        funnel,
                        pd.DataFrame(
                            [
                                {
                                    "stage": int(funnel["stage"].max()) + 1,
                                    "filter": fb.describe() + "  [fallback]",
                                    "N": len(keep),
                                    "n_events": len(survivors),
                                    "frac_nodes_kept": (
                                        (len(keep) / n_nodes_orig) if n_nodes_orig else 0.0
                                    ),
                                    "frac_events_kept": (
                                        (len(survivors) / n_events_orig) if n_events_orig else 0.0
                                    ),
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )

        kept_uuids = sorted({u for _, s, d in survivors for u in (s, d)})
        uuid_to_idx = {u: i for i, u in enumerate(kept_uuids)}
        idx_to_uuid = {i: u for u, i in uuid_to_idx.items()}
        N = len(uuid_to_idx)

        indexed = [(b, uuid_to_idx[s], uuid_to_idx[d]) for (b, s, d) in survivors]
        tensor = build_sparse_tensor(indexed, N, n_bins)

        results[hid] = {
            "tensor": tensor,
            "uuid_to_idx": uuid_to_idx,
            "idx_to_uuid": idx_to_uuid,
            "funnel": funnel,
            "meta": {
                "dataset": dataset,
                "sub_dataset": sub_dataset,
                "host_id": hid,
                "N": N,
                "N_orig": n_nodes_orig,
                "S": n_bins,
                "n_events": len(indexed),
                "n_events_orig": n_events_orig,
                "kept_frac": (len(indexed) / n_events_orig) if n_events_orig else 0.0,
                "bin_width_ns": bin_width_ns,
                "start_ns": start_ns,
                "end_ns": end_ns,
                "filters": [f.describe() for f in filters], # type: ignore
                "max_nodes_fallback": max_nodes_fallback,
                "fallback_triggered": fallback_triggered,
                "transform_extras": transform_extras,
            },
        }
        del events, survivors, indexed
        gc.collect()

    return results

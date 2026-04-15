from __future__ import annotations

import pandas as pd
import numpy as np
from typing import List, Optional

INFOFLOW_EVENTS_CDM = [
    "EVENT_FORK",
    "EVENT_CLONE",
    "EVENT_CREATE_THREAD",
    "EVENT_EXECUTE",
    "EVENT_LOADLIBRARY",
    "EVENT_READ",
    "EVENT_MMAP",
    "EVENT_LSEEK",
    "EVENT_WRITE",
    "EVENT_SENDMSG",
    "EVENT_SENDTO",
    "EVENT_RECVFROM",
    "EVENT_RECVMSG",
]

# _ concatenated tuples 
INFOFLOW_EVENTS_ECAR = [
    "FILE_READ",
    "FILE_WRITE",
    "MODULE_LOAD",
    "PROCESS_CREATE",
    "FLOW_START",
    "FLOW_MESSAGE",
    "REGISTRY_ADD",
    "REGISTRY_EDIT",
]

INFOFLOW_EVENTS_ALL = INFOFLOW_EVENTS_CDM + INFOFLOW_EVENTS_ECAR

def compute_volumetrics(
    event_counts: pd.DataFrame,
    infoflow_event_types: Optional[List[str]] = None,
    time_col: str = "time_bin_ns",
    host_col: str = "host_id",
    event_type_col: str = "event_type",
    count_col: str = "count",
) -> pd.DataFrame:
    """
    event_counts : pd.DataFrame
        Columns: [host_id, time_bin_ns, event_type, count]
    infoflow_event_types : list of str, optional
        Event types considered information flow.

    returns df
        One row per host with columns:
        - host_id
        - avg_events_per_s, std_events_per_s
        - avg_infoflow_per_s, std_infoflow_per_s
    """
    if infoflow_event_types is None:
        infoflow_event_types = INFOFLOW_EVENTS_ALL

    totals = (
        event_counts
        .groupby([host_col, time_col])[count_col]
        .sum()
        .reset_index()
        .rename(columns={count_col: "total_count"})
    )

    infoflow_mask = event_counts[event_type_col].isin(infoflow_event_types)
    infoflow = (
        event_counts[infoflow_mask]
        .groupby([host_col, time_col])[count_col]
        .sum()
        .reset_index()
        .rename(columns={count_col: "infoflow_count"})
    )

    # Merge so every bin has both columns
    merged = totals.merge(infoflow, on=[host_col, time_col], how="left")
    merged["infoflow_count"] = merged["infoflow_count"].fillna(0)

    results = []
    for host, grp in merged.groupby(host_col):

        bins_sorted = grp[time_col].sort_values()
        diffs = bins_sorted.diff().dropna()
        bin_width_ns = int(diffs.mode().iloc[0]) if len(diffs) > 0 else 300_000_000_000
        bin_width_s = bin_width_ns / 1e9

        # exclude gap bins
        active = grp[grp["total_count"] > 0].copy()

        active_eps = active["total_count"] / bin_width_s
        active_ips = active["infoflow_count"] / bin_width_s

        results.append({
            "host_id": host,
            "avg_events_per_s": round(active_eps.mean(), 2),
            "std_events_per_s": round(active_eps.std(), 2),
            "avg_infoflow_per_s": round(active_ips.mean(), 2),
            "std_infoflow_per_s": round(active_ips.std(), 2),
            "n_active_bins": len(active),
        })

    return pd.DataFrame(results)
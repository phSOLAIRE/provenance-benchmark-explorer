"""
1. % gaps per host: % of 5-minute time bins with zero events across all event types.

2. Timing errors per host; from pre-computed timestamp disorder analysis.
    gives: error_rate, n_errors, n_total, mean_error_s, std_error_s, max_error_s.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, Any

# depends on run of  provenance_explorer.analysis.system_scale.event_per_host.EventsPerHostPlot
def compute_gaps_per_host(
    event_counts: pd.DataFrame,
    time_col: str = "time_bin_ns",
    host_col: str = "host_id",
    count_col: str = "count",
) -> pd.DataFrame:

    BIN_WIDTH_NS = 5 * 60 * 1_000_000_000  # 5 minutes
    totals = (
        event_counts
        .groupby([host_col, time_col])[count_col]
        .sum()
        .reset_index()
    )

    results = []

    for host, grp in totals.groupby(host_col):
        t_min = grp[time_col].min()
        t_max = grp[time_col].max()

        # Full expected bins
        full_bins = pd.RangeIndex(start=t_min, stop=t_max + BIN_WIDTH_NS, step=BIN_WIDTH_NS)

        # Map existing bins
        counts = grp.set_index(time_col)[count_col]

        # Align to full range (missing bins become NaN)
        aligned = counts.reindex(full_bins, fill_value=0)

        n_bins_total = len(aligned)
        n_bins_with_events = (aligned > 0).sum()
        n_gaps = (aligned == 0).sum()

        gap_pct = (n_gaps / n_bins_total * 100) if n_bins_total > 0 else 0.0

        results.append({
            "host_id": host,
            "bin_width_s": BIN_WIDTH_NS / 1e9,
            "n_bins_total": n_bins_total,
            "n_bins_with_events": int(n_bins_with_events),
            "n_gaps": int(n_gaps),
            "gap_pct": round(gap_pct, 4),
        })

    return pd.DataFrame(results)

# Timing errors, depends on provenance_explorer.analysis.provenance_capture.timestamp_disorder_plot.TimestampDisorderPlot
def extract_timing_errors(
    timing_errors: Dict[str, Dict[str, Any]],
) -> pd.DataFrame:
    rows = []
    for host_id, stats in timing_errors.items():
        rows.append({
            "host_id": host_id,
            "timing_error_rate": stats["error_rate"],
            "timing_n_errors": stats["n_errors"],
            "timing_n_total": stats["n_total"],
            "timing_mean_error_s": stats["mean_error_s"],
            "timing_std_error_s": stats["std_error_s"],
            "timing_max_error_s": stats["max_error_s"],
            "timing_median_error_s": stats["median_error_s"],
            "timing_p25_error_s": stats["p25_error_s"],
            "timing_p75_error_s": stats["p75_error_s"],
            "timing_iqr_error_s": stats["iqr_error_s"],
        })
    return pd.DataFrame(rows)

def compute_timespan_per_host(
    event_counts: pd.DataFrame,
    time_col: str = "time_bin_ns",
    host_col: str = "host_id",
) -> pd.DataFrame:
    """Timespan in days from first to last bin per host."""
    NS_PER_DAY = 24 * 3600 * 1_000_000_000

    results = []
    for host, grp in event_counts.groupby(host_col):
        t_min = grp[time_col].min()
        t_max = grp[time_col].max()
        results.append({
            "host_id": host,
            "timespan_days": round((t_max - t_min) / NS_PER_DAY, 2),
        })

    return pd.DataFrame(results)
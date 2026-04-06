"""
ActivityEvolutionPlot

For each host, tracks unique (normalised with plug-in 'normalize_fn' function user has to provide) command-line strings in 5-minute bins.

Saves one first-seen ledger as parquet:
    host_id            : str
    normalised_cmdline : str
    first_seen_ns      : int   (timestamp of the first occurrence)
    total_event_count  : int   (how often this cmdline appeared in total)

Example usage in notebook:

    from provenance_explorer.analysis.activity_realism.activity_evolution.evolution_plot import ActivityEvolutionPlot
    from provenance_explorer.plotting import apply_style

    apply_style()

    plot = ActivityEvolutionPlot()
    # default no normalisation:
    fig = plot.run(dataset="e3", sub_dataset="clearscope")
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline, palette
from provenance_explorer.common_record import iterate_common_records, DropLog

BIN_WIDTH_NS = 5 * 60 * 10**9  # 5 minutes in nanoseconds
NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

def _bin_start(timestamp_ns: int) -> int:
    return (timestamp_ns // BIN_WIDTH_NS) * BIN_WIDTH_NS

def _collect_first_seen_ledger(
    dataset: str,
    sub_dataset: str,
    normalize_fn: Callable[[str], str],
) -> pd.DataFrame:
    """
    Returns a df with one row per unique (host_id, normalised_cmdline):
        host_id, normalised_cmdline, first_seen_ns, total_event_count
    """
    logger = DropLog()
    iterator = iterate_common_records(
        dataset, sub_dataset, drop_log=logger,
    )

    # first_seen: host -> cmdline -> timestamp_ns of first occurrence
    first_seen: dict[str, dict[str, int]] = defaultdict(dict)
    # counts: host -> cmdline -> total events
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    n_records = 0
    for record in iterator:
        if record.cmdline is None:
            continue

        cmd = normalize_fn(record.cmdline)
        host = record.host_id
        ts = record.timestamp_ns

        counts[host][cmd] += 1

        if cmd not in first_seen[host]:
            first_seen[host][cmd] = ts

        n_records += 1
        if n_records % 10_000_000 == 0:
            print(f"\t{n_records / 1e6:.0f}M records processed")

    logger.summary(dataset, sub_dataset)
    print(f"\tdone. {n_records:,} records with cmdline")

    rows = []
    for host in sorted(first_seen.keys()):
        for cmd, ts in first_seen[host].items():
            rows.append((host, cmd, ts, counts[host][cmd]))

    return pd.DataFrame(
        rows,
        columns=["host_id", "normalised_cmdline", "first_seen_ns", "total_event_count"],
    )

def _ledger_to_saturation(ledger: pd.DataFrame) -> pd.DataFrame:
    """
    per-host saturation curve from the first-seen ledger.

    Returns a df with columns:
        host_id, bin_start_ns, new_unique_count, cumulative_unique
    """
    if ledger.empty:
        return pd.DataFrame(
            columns=["host_id", "bin_start_ns", "new_unique_count", "cumulative_unique"]
        )

    df = ledger.copy()
    df["bin_start_ns"] = df["first_seen_ns"].apply(_bin_start)

    rows = []
    for host in sorted(df["host_id"].unique()):
        hdf = df[df["host_id"] == host]
        bin_counts = hdf.groupby("bin_start_ns").size().sort_index()
        cumulative = 0
        for bin_ns, new_count in bin_counts.items():
            cumulative += new_count
            rows.append((host, bin_ns, new_count, cumulative))

    return pd.DataFrame(
        rows,
        columns=["host_id", "bin_start_ns", "new_unique_count", "cumulative_unique"],
    )

class ActivityEvolutionPlot(PlotPipeline):
    """Cmdline saturation curves per host for one sub-dataset."""

    @property
    def cache_suffix(self) -> str:
        return "parquet"

    def relative_path(self, dataset: str, sub_dataset: str, **kwargs: Any) -> str:
        return f"{dataset}/{sub_dataset}/activity_evolution"

    # data retrieval
    def retrieve_data(
        self,
        dataset: str,
        sub_dataset: str,
        normalize_fn: Callable[[str], str] = lambda c: c,
        **kwargs: Any,
    ) -> Any:
        print(f"\t[activity evolution] {dataset}/{sub_dataset}")
        return _collect_first_seen_ledger(dataset, sub_dataset, normalize_fn)

    def make_plot(
        self,
        data: pd.DataFrame,
        dataset: str,
        sub_dataset: str,
        **kwargs: Any,
    ) -> Figure:
        if data.empty:
            fig, ax = plt.subplots()
            ax.set_title(f"No data — {dataset}/{sub_dataset}")
            return fig

        saturation = _ledger_to_saturation(data)
        hosts = sorted(saturation["host_id"].unique())
        colors = palette()

        fig, (ax_cum, ax_new) = plt.subplots(
            2, 1,
            figsize=(14, 7),
            sharex=True,
            gridspec_kw={"height_ratios": [2, 1]},
        )

        for host, color in zip(hosts, colors):
            hdf = saturation[saturation["host_id"] == host].copy()
            hdf = hdf[hdf["bin_start_ns"] >= EARLIEST_TOLERATED_NS_TS]
            dts = [
                datetime.fromtimestamp(b / 1e9, tz=timezone.utc)
                for b in hdf["bin_start_ns"]
            ]
            host_label = host[:12] + "…" if len(host) > 14 else host

            ax_cum.plot(
                dts, hdf["cumulative_unique"], linewidth=1.0,
                label=host_label, color=color,
            )

            ax_new.bar(
                dts, hdf["new_unique_count"], width=5 / (24 * 60),
                alpha=0.6, color=color, linewidth=0,
            )

        ax_cum.set_ylabel("Cumulative unique cmdlines")
        ax_cum.set_title(f"Activity Evolution — {dataset}/{sub_dataset}")
        ax_cum.legend(fontsize=8, loc="lower right")

        ax_new.set_ylabel("New unique / bin")
        ax_new.set_xlabel("Time (UTC)")

        ax_new.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax_new.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=30)

        fig.tight_layout()
        return fig

"""
BinnedEventCountsPlot

make_plot() produces a stacked area chart of event rates over time with one panel per host.

NOTE THAT: 
This does a full common-record sweep for one sub-dataset; this takes time. 
Iterates every record, bins by (host_id, 5-minute bin, edge_category) and stores the result as a parquet DataFrame.
This dataframe is used by many secondary plots.
Non-zero bins are stored; gaps need to be inferred.

Columns:
    host_id :str
    bin_start_ns :int
    fork :int
    execute :int
    read :int
    write :int
    send :int
    recv :int
    total :int

Example usage in notebook:

    from provenance_explorer.analysis.system_scale.binned_event_counts_plot import BinnedEventCountsPlot
    from provenance_explorer.plotting import apply_style

    apply_style()

    plot = BinnedEventCountsPlot()
    # plot.invalidate(dataset="e3", sub_dataset="cadets")
    fig  = plot.run(dataset="e3", sub_dataset="cadets")
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline, palette
from provenance_explorer.common_record.schema import EdgeCategory
from provenance_explorer.common_record import iterate_common_records, DropLog

BIN_WIDTH_NS = 5 * 60 * 10**9 
BIN_WIDTH_S = 5 * 60
CATEGORY_COLUMNS = [e.name.lower() for e in EdgeCategory]

NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

def _bin_start(timestamp_ns: int) -> int:
    return (timestamp_ns // BIN_WIDTH_NS) * BIN_WIDTH_NS

def _collect_binned_counts(
    dataset: str,
    sub_dataset: str,
) -> pd.DataFrame:
    """
    Iterate every common record in one sub-dataset and return a DataFrame of per-host, per-bin, per-category event counts.
    """
    logger = DropLog()
    iterator = iterate_common_records(dataset, sub_dataset, drop_log=logger,) # test_run_seconds=10)

    # (host_id, bin_start_ns) -> [fork, execute, read, write, send, recv]
    counts: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0] * len(EdgeCategory))

    category_index = {cat: i for i, cat in enumerate(EdgeCategory)}

    n_records = 0
    for record in iterator:
        key = (record.host_id, _bin_start(record.timestamp_ns))
        idx = category_index[record.edge_category]
        counts[key][idx] += 1
        n_records += 1
        if n_records % 10_000_000 == 0:
            print(f"\t{n_records / 1e6:.0f}M records processed")

    logger.summary(dataset, sub_dataset)

    rows = []
    for (host_id, bin_ns), cat_counts in counts.items():
        rows.append((host_id, bin_ns, *cat_counts, sum(cat_counts)))

    df = pd.DataFrame(
        rows,
        columns=["host_id", "bin_start_ns"] + CATEGORY_COLUMNS + ["total"],
    )
    df.sort_values(["host_id", "bin_start_ns"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


class BinnedEventCountsPlot(PlotPipeline):
    """5-minute binned event counts by host and edge category for one sub-dataset."""

    @property
    def cache_suffix(self) -> str:
        return "parquet"

    def relative_path(self, dataset: str, sub_dataset: str, **kwargs: Any) -> str:
        return f"{dataset}/{sub_dataset}/binned_event_counts"

    def retrieve_data(self, dataset: str, sub_dataset: str, **kwargs: Any) -> Any:
        print(f"\t[binned event counts] {dataset}/{sub_dataset}")
        return _collect_binned_counts(dataset, sub_dataset)

    def make_plot(
        self,
        data: pd.DataFrame,
        dataset: str,
        sub_dataset: str,
        log_scale: bool = False,
        **kwargs: Any
    ) -> Figure:
        if data.empty:
            fig, _ = plt.subplots()
            return fig

        hosts = sorted(data["host_id"].unique()) # TODO make an object lookup helper that only loads in metadata, so a sensible hostname can be retrieved
        n_hosts = len(hosts)

        # sort categories by total frequency, so low frequency appears at bottom to be enhanced by log scale
        category_totals = {
            col: data[col].sum() for col in CATEGORY_COLUMNS
        }
        sorted_categories = sorted(
            CATEGORY_COLUMNS,
            key=lambda c: -category_totals[c],
            reverse=True
        )

        colors = palette()
        cat_colors = dict(zip(sorted_categories, colors))

        fig, axes = plt.subplots(
            n_hosts, 1,
            figsize=(16, 3.5 * n_hosts),
            sharex=True,
            squeeze=False,
        )

        for row_idx, host_id in enumerate(hosts):
            ax = axes[row_idx, 0]
            host_df = data[data["host_id"] == host_id].copy()
            host_df = host_df[host_df["bin_start_ns"] >= EARLIEST_TOLERATED_NS_TS]

            # build dense time axis for this host
            t_min = host_df["bin_start_ns"].min()
            t_max = host_df["bin_start_ns"].max()
            all_bins = np.arange(t_min, t_max + BIN_WIDTH_NS, BIN_WIDTH_NS)

            dense = pd.DataFrame({"bin_start_ns": all_bins})
            dense = dense.merge(host_df, on="bin_start_ns", how="left")
            for col in sorted_categories:
                dense[col] = dense[col].fillna(0).astype(int)

            datetimes = [
                datetime.fromtimestamp(b / 1e9, tz=timezone.utc)
                for b in dense["bin_start_ns"]
            ]

            # convert to 'events/second'
            rates = {
                col: dense[col].values / BIN_WIDTH_S # type: ignore
                for col in sorted_categories
            }

            # stacked area
            bottom = np.zeros(len(datetimes))
            for col in sorted_categories:
                ax.fill_between(
                    datetimes,
                    bottom,
                    bottom + rates[col],
                    label=col,
                    color=cat_colors[col],
                    alpha=0.8,
                    linewidth=0,
                )
                bottom = bottom + rates[col]

            if log_scale:
                ax.set_yscale("log")

            # host_id = host_id[:12] + "..." if len(host_id) > 14 else host_id # truncate host_id
            ax.set_ylabel("ev/s", fontsize=8)
            ax.set_title(f"{host_id}", fontsize=9, loc="left")

        # shared x-axis
        axes[-1, 0].set_xlabel("Time (UTC)")
        axes[-1, 0].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        axes[-1, 0].xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=30)

        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper right")

        fig.suptitle(
            f"Per-Host Information Flow Event Rates - for {dataset}/{sub_dataset}",
        )
        fig.tight_layout()
        return fig
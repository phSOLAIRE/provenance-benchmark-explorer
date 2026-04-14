"""
Example usage in notebook:

    from provenance_explorer.analysis.system_scale.event_per_host import EventsPerHostPlot
    from provenance_explorer.plotting import apply_style

    apply_style()

    plot = EventsPerHostPlot()
    # plot.invalidate(dataset="e3", sub_dataset="cadets")
    fig  = plot.run(dataset="e3", sub_dataset="cadets")
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure
import numpy as np
import pandas as pd
import re

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import TS_EXTRACTORS

from provenance_explorer.registry.registry_all import get_subdataset_registry

NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

CDM_INFOFLOW = {
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
    "EVENT_WRITE",
    "EVENT_RECVFROM",
    "EVENT_RECVMSG",
    "EVENT_READ",
}

ECAR_INFOFLOW = {
    "READ_FILE",
    "WRITE_FILE",
    "LOAD_MODULE",
    "CREATE_PROCESS",
    "START_FLOW",
    "MESSAGE_FLOW",
    "ADD_REGISTRY",
    "EDIT_REGISTRY",
}

_EVENT_RE = re.compile(
    r'"com\.bbn\.tc\.schema\.avro\.cdm\d+\.Event"'
    r'.*?"type":"([^"]+)"'
    r'.*?"hostId":"([^"]+)"'
)

_ECAR_RE = re.compile(
    r'"action":"([^"]+)"'
    r'.*?"hostname":"([^"]+)"'
    r'.*?"object":"([^"]+)"'
)

def _ecar_parser(line: str) -> tuple[str, str] | None:
    m = _ECAR_RE.search(line)
    if m is None:
        return None
    action, hostname, obj = m.group(1), m.group(2), m.group(3)
    return f"{obj}_{action}", hostname

def _cdm_parser(line: str) -> tuple[str, str] | None:
    m = _EVENT_RE.search(line)
    if m is None:
        return None
    return m.group(1), m.group(2)


def _get_parser(ds):
    if ds == "e3" or ds == "e5":
        return _cdm_parser
    elif ds == "optc":
        return _ecar_parser 
    else:
        raise

class EventsPerHostPlot(PlotPipeline):

    @property
    def cache_suffix(self) -> str:
        return "parquet"

    def relative_path(self, dataset: str, sub_dataset: str, **kwargs: Any) -> str:
        return f"{dataset}/{sub_dataset}/events_per_host"

    def retrieve_data(self, dataset: str, sub_dataset: str, **kwargs: Any) -> pd.DataFrame:
        BIN_NS = 5 * 60 * NS_PER_SEC

        iterator = make_dataset_iterator(
            get_subdataset_registry(dataset, sub_dataset),
            ts_extractor=TS_EXTRACTORS[dataset, sub_dataset],
            parse_fn=_get_parser(dataset),
        )

        counts: dict[tuple[str, int, str], int] = defaultdict(int)
        for ts, pair in iterator:
            if not pair:
                continue
            if ts < EARLIEST_TOLERATED_NS_TS:
                continue
            event_type, host_id = pair
            time_bin = (ts // BIN_NS) * BIN_NS
            counts[(host_id, time_bin, event_type)] += 1

        rows = [
            {"host_id": h, "time_bin_ns": t, "event_type": e, "count": c}
            for (h, t, e), c in counts.items()
        ]
        return pd.DataFrame(rows, columns=["host_id", "time_bin_ns", "event_type", "count"])

    def make_plot(
        self, data: pd.DataFrame, dataset: str, infoflow_only: bool = False, log_scale: bool = True, **kwargs: Any
    ) -> Figure:
        BIN_NS = 5 * 60 * NS_PER_SEC
        BIN_SEC = BIN_NS / NS_PER_SEC

        if infoflow_only:
            infoflow_set = CDM_INFOFLOW if dataset in ("e3", "e5") else ECAR_INFOFLOW
            data = data[data["event_type"].isin(infoflow_set)].copy()

        if data.empty:
            fig, ax = plt.subplots()
            ax.set_title("No data")
            return fig

        hosts = sorted(data["host_id"].unique())
        n_hosts = len(hosts)
        all_bins = np.array(sorted(data["time_bin_ns"].unique()))
        bin_datetimes = [datetime.fromtimestamp(b / 1e9, tz=timezone.utc) for b in all_bins]
        bar_width = timedelta(seconds=BIN_SEC * 0.9)

        fig, axes = plt.subplots(n_hosts, 1, sharex=True, squeeze=False,
                                 figsize=(14, n_hosts * 2.5))
        axes = axes.flatten()

        for ax, host in zip(axes, hosts):
            host_data = data[data["host_id"] == host]

            if infoflow_only:
                # Sort event types by total count ascending so least common lands at the bottom of the stack,
                # keeping it visible on a log scale where small values at the base are readable.
                event_totals = host_data.groupby("event_type")["count"].sum().sort_values()
                event_types = event_totals.index.tolist()

                pivot = (
                    host_data
                    .pivot_table(index="time_bin_ns", columns="event_type", values="count", fill_value=0)
                    .reindex(all_bins, fill_value=0)
                )

                bottom = np.zeros(len(bin_datetimes))
                for et in event_types:
                    if et not in pivot.columns:
                        continue
                    values = pivot[et].values / BIN_SEC
                    ax.bar(bin_datetimes, values, bottom=bottom, width=bar_width, label=et)
                    bottom += values
            else:
                totals = (
                    host_data.groupby("time_bin_ns")["count"]
                    .sum()
                    .reindex(all_bins, fill_value=0)
                )
                rates = totals.values / BIN_SEC
                ax.plot(bin_datetimes, rates, linewidth=0.8)
                ax.fill_between(bin_datetimes, rates, alpha=0.3)

            if log_scale:
                ax.set_yscale("log")
            ax.set_ylabel("events/s", fontsize=7)
            ax.set_title(host[:20], fontsize=8, loc="left")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        axes[-1].set_xlabel("Time (UTC)")

        if infoflow_only:
            handles, labels = axes[0].get_legend_handles_labels()
            if handles:
                fig.legend(handles, labels, loc="upper right", fontsize=7, ncol=2)

        fig.autofmt_xdate(rotation=30)
        fig.tight_layout()
        return fig

"""
RawEventDensityPlot

Count raw provenance events in 5-minute bins for a single sub-dataset.
Periods where counts are 0 are marked red, so low density does not mean no density.

Bins are keyed by their left edge as an ISO string; and in UTC.

Example usage in notebook:

    from provenance_explorer.analysis.system_scale.raw_event_density_plot import RawEventDensityPlot
    from provenance_explorer.plotting import apply_style

    apply_style()

    plot = RawEventDensityPlot()
    # plot.invalidate(dataset="e3", sub_dataset="cadets")
    fig  = plot.run(dataset="e3", sub_dataset="cadets")

"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.registry.registry_all import get_big_registry
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import TS_EXTRACTORS

BIN_WIDTH_NS = 5 * 60 * 10**9  # 5 minutes in nanoseconds
NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

def _ns_to_bin_start_ns(timestamp_ns: int) -> int:
    return (timestamp_ns // BIN_WIDTH_NS) * BIN_WIDTH_NS

def _ns_to_iso(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat()

def _iso_to_ns(iso: str) -> int:
    dt = datetime.fromisoformat(iso)
    return int(dt.timestamp() * 1e9)

def _collect_bin_counts(
    dataset: str,
    sub_dataset: str,
) -> dict[str, int]:
    registry = get_big_registry(dataset)[sub_dataset]
    ts_extractor = TS_EXTRACTORS[(dataset, sub_dataset)]
    dumb_parse = lambda _line: None # no event info needed

    iterator = make_dataset_iterator(
        registry=registry,
        parse_fn=dumb_parse,
        ts_extractor=ts_extractor,
        # test_run_seconds=10, # uncomment for test
    )

    counts: dict[int, int] = defaultdict(int)
    for ts_ns, _record in iterator:
        if ts_ns is None or ts_ns < EARLIEST_TOLERATED_NS_TS:
            continue
        counts[_ns_to_bin_start_ns(ts_ns)] += 1

    return {
        _ns_to_iso(k): v
        for k, v in sorted(counts.items())
    }


class RawEventDensityPlot(PlotPipeline):

    @property
    def cache_suffix(self) -> str:
        return "json"

    def relative_path(self, dataset: str, sub_dataset: str, **kwargs: Any) -> str:
        return f"{dataset}/{sub_dataset}/raw_event_density"

    def retrieve_data(self, dataset: str, sub_dataset: str, **kwargs: Any) -> Any:
        return _collect_bin_counts(dataset, sub_dataset)

    def make_plot(self, data: dict[str, int], dataset: str, sub_dataset: str, **kwargs: Any) -> Figure:
        if not data:
            fig, ax = plt.subplots()
            ax.set_title(f"No data — {dataset}/{sub_dataset}")
            return fig

        bin_ns = sorted(_iso_to_ns(k) for k in data.keys())
        t_min, t_max = bin_ns[0], bin_ns[-1]

        all_bins_ns = list(range(t_min, t_max + BIN_WIDTH_NS, BIN_WIDTH_NS))
        counts_by_ns = {_iso_to_ns(k): v for k, v in data.items()}

        datetimes = [
            datetime.fromtimestamp(b / 1e9, tz=timezone.utc)
            for b in all_bins_ns
        ]
        counts = [counts_by_ns.get(b, 0) for b in all_bins_ns] # fill gaps with 0

        # convert counts to 'events / second'
        bin_seconds = BIN_WIDTH_NS / 1e9
        rates = [c / bin_seconds for c in counts]

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.plot(datetimes, rates, linewidth=0.5) # type: ignore
        ax.fill_between(datetimes, rates, alpha=0.3) # type: ignore

        ax.set_xlabel("Time (UTC)")
        ax.set_ylabel("Events / second")
        ax.set_title(f"Raw Event Density — {dataset}/{sub_dataset}")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=30)

        # mark regions where count == 0 for >1 hour
        gap_threshold = int(3600 / (BIN_WIDTH_NS / 1e9))  # bins per hour
        gap_start = None
        for i, c in enumerate(counts):
            if c == 0 and gap_start is None:
                gap_start = i
            elif c > 0 and gap_start is not None:
                if (i - gap_start) >= gap_threshold:
                    ax.axvspan(
                        datetimes[gap_start], datetimes[i - 1], # type: ignore
                        alpha=0.10, color="red", label="gap (>1h)" if gap_start == 0 or i == len(counts) else None,
                    )
                gap_start = None
        # trailing gap
        if gap_start is not None and (len(counts) - gap_start) >= gap_threshold:
            ax.axvspan(
                datetimes[gap_start], datetimes[-1], # type: ignore
                alpha=0.10, color="red",
            )

        fig.tight_layout()
        return fig

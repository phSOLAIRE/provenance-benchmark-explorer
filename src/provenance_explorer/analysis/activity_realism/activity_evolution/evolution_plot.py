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

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline, palette
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import TS_EXTRACTORS
from provenance_explorer.registry.registry_all import get_subdataset_registry

BIN_WIDTH_NS = 5 * 60 * 10**9  # 5 minutes in nanoseconds
NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

# CDM regex: extract hostId + cmdLine from any record type
_CDM_HOST_RE = re.compile(r'"hostId":"([^"]+)"')
# "cmdLine":{"string":"..."} (used by most sub-datasets)
_CDM_CMD_WRAPPED_RE = re.compile(r'"cmdLine":\{"string":"([^"]+)"\}')
# "cmdLine":"..." (form used by e3/cadets Events, e5/cadets Events, and inside Theia properties maps)
_CDM_CMD_DIRECT_RE = re.compile(r'"cmdLine":"([^"]+)"')

# ECAR (OpTC) regex
_ECAR_HOST_RE = re.compile(r'"hostname":"([^"]+)"')
_ECAR_CMD_RE = re.compile(r'"command_line":"([^"]+)"')


def _cdm_cmd_parser(line: str) -> tuple[str, str] | None:
    host_m = _CDM_HOST_RE.search(line)
    if host_m is None:
        return None
    cmd_m = _CDM_CMD_WRAPPED_RE.search(line)
    if cmd_m is None:
        cmd_m = _CDM_CMD_DIRECT_RE.search(line)
    if cmd_m is None:
        return None
    return cmd_m.group(1), host_m.group(1)


def _ecar_cmd_parser(line: str) -> tuple[str, str] | None:
    host_m = _ECAR_HOST_RE.search(line)
    cmd_m = _ECAR_CMD_RE.search(line)
    if host_m is None or cmd_m is None:
        return None
    return cmd_m.group(1), host_m.group(1)


def _get_cmd_parser(ds: str):
    if ds in ("e3", "e5"):
        return _cdm_cmd_parser
    elif ds == "optc":
        return _ecar_cmd_parser
    else:
        raise ValueError(f"Unknown dataset: {ds}")


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
    iterator = make_dataset_iterator(
        get_subdataset_registry(dataset, sub_dataset),
        ts_extractor=TS_EXTRACTORS[dataset, sub_dataset],
        parse_fn=_get_cmd_parser(dataset),
    )

    # first_seen: host -> cmdline -> timestamp_ns of first occurrence
    first_seen: dict[str, dict[str, int]] = defaultdict(dict)
    # counts: host -> cmdline -> total events
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    n_records = 0
    for ts, pair in iterator:
        if pair is None:
            continue
        if ts < EARLIEST_TOLERATED_NS_TS:
            continue

        cmdline, host_id = pair
        cmd = normalize_fn(cmdline)

        counts[host_id][cmd] += 1

        if cmd not in first_seen[host_id]:
            first_seen[host_id][cmd] = ts

        n_records += 1
        if n_records % 10_000_000 == 0:
            print(f"\t{n_records / 1e6:.0f}M records processed")

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
        normalize_fn: Callable[[str], str] | None = None,
        **kwargs: Any,
    ) -> Figure:
        if data.empty:
            fig, ax = plt.subplots()
            ax.set_title(f"No data — {dataset}/{sub_dataset}")
            return fig
 
        if normalize_fn is not None:
            # re-normalise cmdlines and re-aggregate
            df = data.copy()
            df["normalised_cmdline"] = df["normalised_cmdline"].map(normalize_fn)
            df = (
                df.groupby(["host_id", "normalised_cmdline"], as_index=False)
                .agg(first_seen_ns=("first_seen_ns", "min"),
                     total_event_count=("total_event_count", "sum"))
            )
        else:
            df = data
        
        saturation = _ledger_to_saturation(df)
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

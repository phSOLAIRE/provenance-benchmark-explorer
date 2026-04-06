"""
ActivityEvolutionPlot

For each host, tracks unique (normalised with plug-in 'normalize_fn' function user has to provide) command-line strings in 5-minute bins.

Saves two data structures.

Primary; parquet for saturation curve data:
    host_id :str
    bin_start_ns :int
    new_unique_count :int (cmdlines first seen in this bin)
    cumulative_unique :int (running total of unique cmdlines up to this bin)

Secondary: full cmdline inventory:
    { host_id: { normalised_cmdline: total_event_count } }
saved next to parquet as <stem>_cmdline_inventory.json

Example usage in notebook:

    from provenance_explorer.analysis.activity_realism.activity_evolution.evolution_plot import ActivityEvolutionPlot
    from provenance_explorer.plotting import apply_style

    apply_style()

    plot = ActivityEvolutionPlot()
    # default (identity) normalisation:
    fig = plot.run(dataset="e3", sub_dataset="clearscope")
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import re
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline, palette
from provenance_explorer.common_record import iterate_common_records, DropLog
from provenance_explorer.registry.registry_all import CACHE_ROOT

BIN_WIDTH_NS = 5 * 60 * 10**9  # 5 minutes in nanoseconds

BIN_WIDTH_NS = 5 * 60 * 10**9  # 5 minutes in nanoseconds
NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

def _bin_start(timestamp_ns: int) -> int:
    return (timestamp_ns // BIN_WIDTH_NS) * BIN_WIDTH_NS

def _collect_evolution_data(
    dataset: str,
    sub_dataset: str,
    normalize_fn: Callable[[str], str],
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """
    returns: 
        - saturation_df with cols: (host_id, bin_start_ns, new_unique_count, cumulative_unique)
        - inventory dict: {host_id: {normalised_cmdline: total_event_count}}
    """
    logger = DropLog()
    iterator = iterate_common_records(dataset, sub_dataset, drop_log=logger,)# test_run_seconds=600)

    seen_global: dict[str, set[str]] = defaultdict(set)
    bins_new: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    inventory: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    n_records = 0
    for record in iterator:
        if record.cmdline is None:
            continue

        cmd = normalize_fn(record.cmdline)
        host = record.host_id
        bin_ns = _bin_start(record.timestamp_ns)

        inventory[host][cmd] += 1

        if cmd not in seen_global[host]:
            seen_global[host].add(cmd)
            bins_new[host][bin_ns].add(cmd)

        n_records += 1
        if n_records % 10_000_000 == 0:
            print(f"\t{n_records / 1e6:.0f}M records processed")

    logger.summary(dataset, sub_dataset)
    print(f"\tdone. {n_records:,} records with cmdline")

    rows = []
    for host in sorted(bins_new.keys()):
        sorted_bins = sorted(bins_new[host].keys())
        cumulative = 0
        for bin_ns in sorted_bins:
            new_count = len(bins_new[host][bin_ns])
            cumulative += new_count
            rows.append((host, bin_ns, new_count, cumulative))

    saturation_df = pd.DataFrame(
        rows,
        columns=["host_id", "bin_start_ns", "new_unique_count", "cumulative_unique"],
    )

    inventory_plain = {h: dict(v) for h, v in inventory.items()}

    return saturation_df, inventory_plain


class ActivityEvolutionPlot(PlotPipeline):
    """Cmdline saturation curves per host for one sub-dataset."""

    @property
    def cache_suffix(self) -> str:
        return "parquet"

    def relative_path(self, dataset: str, sub_dataset: str, **kwargs: Any) -> str:
        return f"{dataset}/{sub_dataset}/activity_evolution"

    def _inventory_path(self, dataset: str, sub_dataset: str) -> Path:
        """Path for the side-effect cmdline inventory JSON."""
        base = CACHE_ROOT / re.sub(r"(?<!^)(?=[A-Z])", "_", self.__class__.__name__).lower()
        rel = self.relative_path(dataset=dataset, sub_dataset=sub_dataset)
        return base / f"{rel}_cmdline_inventory.json"

    # data retrieval
    def retrieve_data(
        self,
        dataset: str,
        sub_dataset: str,
        normalize_fn: Callable[[str], str] = lambda c: c,
        **kwargs: Any,
    ) -> Any:
        print(f"\t[activity evolution] {dataset}/{sub_dataset}")
        saturation_df, inventory = _collect_evolution_data(dataset, sub_dataset, normalize_fn)

        # write as side-effect; not part of offial plot pipeline
        inv_path = self._inventory_path(dataset, sub_dataset)
        inv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(inv_path, "w") as fh:
            json.dump(inventory, fh)
        print(f"\tinventory written at {inv_path}")

        return saturation_df

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

        hosts = sorted(data["host_id"].unique())
        colors = palette()

        fig, (ax_cum, ax_new) = plt.subplots(
            2, 1,
            figsize=(14, 7),
            sharex=True,
            gridspec_kw={"height_ratios": [2, 1]},
        )

        for host, color in zip(hosts, colors):
            hdf = data[data["host_id"] == host].copy()
            hdf = hdf[hdf["bin_start_ns"] >= EARLIEST_TOLERATED_NS_TS]
            dts = [
                datetime.fromtimestamp(b / 1e9, tz=timezone.utc)
                for b in hdf["bin_start_ns"]
            ]
            host_label = host[:12] + "…" if len(host) > 14 else host

            # cumulative unique cmdlines
            ax_cum.plot(dts, hdf["cumulative_unique"], linewidth=1.0,
                        label=host_label, color=color)

            # new unique per bin
            ax_new.bar(
                dts, hdf["new_unique_count"], width=5 / (24 * 60),
                alpha=0.6, color=color, linewidth=0
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
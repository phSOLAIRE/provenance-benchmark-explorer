"""
TimestampDisorderPlot

Measure timestamp ordering errors across all sub-datasets in a dataset. The plot is a horizontal box-plot-ish chart clamped at 0.

Since Kafka sequence numbers are perfectly ordered, the "true" record order is known.  
Any record whose timestamp is earlier than its predecessor's is a backward jump.  
We characterise these errors with three streaming statistics (no data structures):

    - ()online mean backward-jump magnitude
    - (online) std of backward-jump magnitude (calculated as welford online variance for numerical stability)
    - max backward-jump magnitude

Example usage in notebook:

    from provenance_explorer.analysis.provenance_capture.correctness.timestamp_disorder_plot import TimestampDisorderPlot
    from provenance_explorer.plotting import apply_style

    apply_style()

    plot = TimestampDisorderPlot()
    # plot.invalidate(dataset="e3")
    fig  = plot.run(dataset="e3")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
import numpy as np

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import TS_EXTRACTORS

from provenance_explorer.registry.darpa_e3_registry import E3_ALL
from provenance_explorer.registry.darpa_e5_registry import E5_ALL
from provenance_explorer.registry.darpa_optc_registry import OPTC_ALL

NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

DATASET_REGISTRIES: dict[str, dict] = {
    "e3": E3_ALL,
    "e5": E5_ALL,
    "optc": OPTC_ALL,
}


def _collect_disorder_stats(
    dataset: str,
) -> dict[str, dict[str, Any]]:
    """
    maintain statistic uisng Welford, so we dont save whole sequences and do nto get numeric instability on varaince.

    Returns:
        {sub_dataset: {
            "n_total": int,
            "n_errors": int,
            "error_rate": float,
            "mean_error_s": float,
            "std_error_s": float,
            "max_error_s": float,
        }}
    """
    all_registries = DATASET_REGISTRIES[dataset]
    dumb_parse = lambda _line: None
    results: dict[str, dict[str, Any]] = {}

    for name, registry in all_registries.items():
        key = name.lower().replace("-", "_")
        ts_fn = TS_EXTRACTORS[(dataset, key)]

        iterator = make_dataset_iterator(
            registry=registry,
            parse_fn=dumb_parse,
            ts_extractor=ts_fn,
        )

        last_ts = 0
        n_total = 0
        n_errors = 0
        mean_error_ns = 0.0
        M2 = 0.0
        max_error_ns = 0

        for ts_ns, _ in iterator:
            if ts_ns is None or ts_ns < EARLIEST_TOLERATED_NS_TS:
                continue
            n_total += 1

            if ts_ns < last_ts:
                error = last_ts - ts_ns
                n_errors += 1
                delta = error - mean_error_ns
                mean_error_ns += delta / n_errors
                delta2 = error - mean_error_ns
                M2 += delta * delta2
                if error > max_error_ns:
                    max_error_ns = error

            last_ts = ts_ns

        variance = M2 / n_errors if n_errors > 1 else 0.0

        results[key] = {
            "n_total": n_total,
            "n_errors": n_errors,
            "error_rate": n_errors / n_total if n_total else 0.0,
            "mean_error_s": mean_error_ns / NS_PER_SEC,
            "std_error_s": variance**0.5 / NS_PER_SEC,
            "max_error_s": max_error_ns / NS_PER_SEC,
        }
        print(
            f"{dataset}/{key}:"
            f"errors={n_errors:,} ({results[key]['error_rate']:.4%})\n"
            f"mean={results[key]['mean_error_s']:.4f}s\n"
            f"std={results[key]['std_error_s']:.4f}s\n"
            f"max={results[key]['max_error_s']:.4f}s\n"
        )

    return results


class TimestampDisorderPlot(PlotPipeline):

    @property
    def cache_suffix(self) -> str:
        return "json"

    def relative_path(self, dataset: str, **kwargs: Any) -> str:
        return f"{dataset}/timestamp_disorder"

    def retrieve_data(self, dataset: str, **kwargs: Any) -> Any:
        return _collect_disorder_stats(dataset)

    def make_plot(
        self, data: dict[str, dict], dataset: str, **kwargs: Any
    ) -> Figure:
        if not data:
            fig, ax = plt.subplots()
            ax.set_title(f"No data — {dataset}")
            return fig

        # # sub-datasets with zero errors
        # data = {k: v for k, v in data.items() if v["n_errors"] > 0}
        # if not data:
        #     fig, ax = plt.subplots()
        #     ax.set_title(f"No timestamp errors found — {dataset}")
        #     return fig

        # sort by mean error 
        items = sorted(data.items(), key=lambda kv: kv[1]["mean_error_s"])
        names = [k for k, _ in items]
        means = [v["mean_error_s"] for _, v in items]
        stds = [v["std_error_s"] for _, v in items]
        maxes = [v["max_error_s"] for _, v in items]
        rates = [v["error_rate"] for _, v in items]

        y = np.arange(len(names))
        box_height = 0.4

        fig, ax = plt.subplots(figsize=(12, max(3, len(names) * 0.8)))

        for i in range(len(names)):
            mean = means[i]
            std = stds[i]
            mx = maxes[i]

            lo = max(mean - std, 1e-6)  # clamp
            hi = mean + std

            ax.barh(
                y[i], hi - lo, left=lo, height=box_height,
                color="C0", alpha=0.4, edgecolor="C0", linewidth=0.8,
            )

            ax.plot(
                [hi, mx], [y[i], y[i]],
                color="C0", linewidth=1.0,
            )
            ax.plot(
                [mx, mx], [y[i] - box_height * 0.3, y[i] + box_height * 0.3],
                color="C0", linewidth=1.0,
            )
            ax.plot(
                mean, y[i], "o",
                color="C0", markersize=6, zorder=5,
            )

            # annotation: error rate
            ax.annotate(
                f"{rates[i]:.3%} misordered",
                xy=(mx, y[i]),
                xytext=(8, 0), textcoords="offset points",
                va="center", fontsize=8, color="0.3",
            )

        ax.set_xscale("log")
        ax.set_yticks(y)
        ax.set_yticklabels(names)
        ax.set_xlabel("Backward timestamp jump (seconds, log scale)")
        ax.set_title(f"Timestamp Disorder — {dataset}")

        ax.legend(
            handles=[
                mpatches.Patch(color="C0", alpha=0.4, label="mean ± 1 std"),
                plt.Line2D([0], [0], marker="o", color="C0", linestyle="", # type: ignore
                           markersize=6, label="mean"),
                plt.Line2D([0], [0], color="C0", linewidth=1.0, label="max"), # type: ignore
            ],
            loc="lower right", fontsize=8,
        )

        fig.tight_layout()
        return fig

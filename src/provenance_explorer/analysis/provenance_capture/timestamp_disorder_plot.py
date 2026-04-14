"""
TimestampDisorderPlot

Measure timestamp ordering errors per host within a single sub-dataset.
The plot is a horizontal box-plot-ish chart clamped at 0.

Since Kafka sequence numbers are perfectly ordered, the "true" record order is known.
Any record whose timestamp is earlier than its predecessor's is a backward jump.
We characterise these errors with three streaming statistics per host:

    - (online) mean backward-jump magnitude
    - (online) std of backward-jump magnitude (calculated as welford online variance for numerical stability)
    - max backward-jump magnitude

Example usage in notebook:

    from provenance_explorer.analysis.provenance_capture.timestamp_disorder_plot import TimestampDisorderPlot
    from provenance_explorer.plotting import apply_style

    apply_style()

    plot = TimestampDisorderPlot()
    # plot.invalidate(dataset="e3", sub_dataset="cadets")
    fig  = plot.run(dataset="e3", sub_dataset="cadets")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import re
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
import numpy as np

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import TS_EXTRACTORS

from provenance_explorer.registry.registry_all import get_subdataset_registry

NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(
    datetime.fromisoformat("2015-01-01").timestamp()
) * NS_PER_SEC

_EVENT_RE = re.compile(
    r'"com\.bbn\.tc\.schema\.avro\.cdm\d+\.Event"'
    r'.*?"hostId":"([^"]+)"'
)

_ECAR_RE = re.compile(
    r'"action":"([^"]+)"'
    r'.*?"hostname":"([^"]+)"'
)

def _ecar_parser(line: str) -> tuple[str, str] | None:
    m = _ECAR_RE.search(line)
    if m is None:
        return None
    action, hostname, obj = '', m.group(2), ''
    return '' , hostname

def _cdm_parser(line: str) -> tuple[str, str] | None:
    m = _EVENT_RE.search(line)
    if m is None:
        return None
    try:
        return '', m.group(1)
    except:
        from pprint import pprint
        pprint(line)
        raise

def _get_parser(ds):
    if ds == "e3" or ds == "e5":
        return _cdm_parser
    elif ds == "optc":
        return _ecar_parser
    else:
        raise


def _collect_disorder_stats(
    dataset: str,
    sub_dataset: str,
) -> dict[str, dict[str, Any]]:
    """
    Maintain statistics per host using Welford's algorithm so we don't save
    whole sequences and don't get numeric instability on variance.

    Returns:
        {host_id: {
            "n_total": int,
            "n_errors": int,
            "error_rate": float,
            "mean_error_s": float,
            "std_error_s": float,
            "max_error_s": float,
        }}
    """
    registry = get_subdataset_registry(dataset, sub_dataset)
    ts_fn = TS_EXTRACTORS[(dataset, sub_dataset)]
    parse_fn = _get_parser(dataset)

    iterator = make_dataset_iterator(
        registry=registry,
        parse_fn=parse_fn,
        ts_extractor=ts_fn,
    )

    # Per-host streaming state
    last_ts: dict[str, int] = {}
    n_total: dict[str, int] = {}
    n_errors: dict[str, int] = {}
    mean_error_ns: dict[str, float] = {}
    M2: dict[str, float] = {}
    max_error_ns: dict[str, int] = {}

    for ts_ns, pair in iterator:
        if pair is None:
            continue
        if ts_ns < EARLIEST_TOLERATED_NS_TS:
            continue

        _event_type, host_id = pair

        if host_id not in n_total:
            last_ts[host_id] = 0
            n_total[host_id] = 0
            n_errors[host_id] = 0
            mean_error_ns[host_id] = 0.0
            M2[host_id] = 0.0
            max_error_ns[host_id] = 0

        n_total[host_id] += 1

        if ts_ns < last_ts[host_id]:
            error = last_ts[host_id] - ts_ns
            n_errors[host_id] += 1
            delta = error - mean_error_ns[host_id]
            mean_error_ns[host_id] += delta / n_errors[host_id]
            delta2 = error - mean_error_ns[host_id]
            M2[host_id] += delta * delta2
            if error > max_error_ns[host_id]:
                max_error_ns[host_id] = error

        last_ts[host_id] = ts_ns

    results: dict[str, dict[str, Any]] = {}
    for host_id in n_total:
        ne = n_errors[host_id]
        nt = n_total[host_id]
        variance = M2[host_id] / ne if ne > 1 else 0.0

        results[host_id] = {
            "n_total": nt,
            "n_errors": ne,
            "error_rate": ne / nt if nt else 0.0,
            "mean_error_s": mean_error_ns[host_id] / NS_PER_SEC,
            "std_error_s": variance**0.5 / NS_PER_SEC,
            "max_error_s": max_error_ns[host_id] / NS_PER_SEC,
        }
        print(
            f"{dataset}/{sub_dataset}/{host_id[:16]}:"
            f"  errors={ne:,} ({results[host_id]['error_rate']:.4%})"
            f"  mean={results[host_id]['mean_error_s']:.4f}s"
            f"  std={results[host_id]['std_error_s']:.4f}s"
            f"  max={results[host_id]['max_error_s']:.4f}s"
        )

    return results


class TimestampDisorderPlot(PlotPipeline):

    @property
    def cache_suffix(self) -> str:
        return "json"

    def relative_path(self, dataset: str, sub_dataset: str, **kwargs: Any) -> str:
        return f"{dataset}/{sub_dataset}/timestamp_disorder"

    def retrieve_data(self, dataset: str, sub_dataset: str, **kwargs: Any) -> Any:
        return _collect_disorder_stats(dataset, sub_dataset)

    def make_plot(
        self, data: dict[str, dict], dataset: str, sub_dataset: str, **kwargs: Any
    ) -> Figure:
        if not data:
            fig, ax = plt.subplots()
            ax.set_title(f"No data — {dataset}/{sub_dataset}")
            return fig

        # sort by mean error
        items = sorted(data.items(), key=lambda kv: kv[1]["mean_error_s"])
        names = [k[:20] for k, _ in items]
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
        ax.set_title(f"Timestamp Disorder — {dataset}/{sub_dataset}")

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

"""
RegularityComponentsPlot

For one (dataset, sub_dataset, host, window) combination, build the filtered
information-flow tensor, run the NTF sweep, and render one row per component:

    [ 
        temporal profile C[:,r] | 
        source factor A[:,r] | 
        destination B[:,r] |
        score box (relevance, periodicity, burstiness, regime) 
    ]

Also emits a header summary: regime fractions across nodes and best explained
variance under R=25.

Separate cache from NtfDecompositionPlot to avoid silently mixing filtered and
unfiltered results. The filter pipeline is part of the cache key (as a
description string).
"""
from __future__ import annotations

import gc
import hashlib
from typing import Any, Dict, List, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.analysis.activity_realism.activity_regularity._components_figure import render_components_figure
from provenance_explorer.analysis.activity_realism.activity_regularity.filtered_graph_builder import build_filtered_host_graphs
from provenance_explorer.analysis.activity_realism.activity_regularity.graph_filters import (
    NodeFilter, PersistenceFilter, ActivityFloorFilter,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.mttkrp_helpers import (
    run_sweep,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.component_metrics import (
    analyze_components, best_explained_variance_under,
    CONCENTRATION_COARSENING,
    PERIODICITY_THRESHOLD, BURSTINESS_THRESHOLD, CONCENTRATION_THRESHOLD,
)


NS_PER_SEC = 1_000_000_000
DEFAULT_BIN_WIDTH_NS = 5 * 60 * NS_PER_SEC
DEFAULT_R_RANGE = list(range(1, 26))
DEFAULT_N_INITS = 4
DEFAULT_MAX_ITER = 100
DEFAULT_TOL = 1e-4
DEFAULT_CC_THRESHOLD = 50.0

# tag for which filter was used
def _filters_tag(filters: Sequence[NodeFilter]) -> str:
    if not filters:
        return "raw"
    desc = "|".join(f.describe() for f in filters)
    h = hashlib.md5(desc.encode()).hexdigest()[:8]
    return h


def _select_best(sweep, cc_threshold: float):
    """lowest-error R whose CC is >= 50."""
    viable = [e for e in sweep if e["core_consistency"] >= cc_threshold]
    if viable:
        return min(viable, key=lambda e: e["rel_error"])
    r1 = [e for e in sweep if e["R"] == 1]
    return r1[0] if r1 else sweep[0]


class RegularityComponentsPlot(PlotPipeline):

    @property
    def cache_suffix(self) -> str:
        return "pkl"

    def relative_path(self, **kwargs: Any) -> str:
        dataset = kwargs["dataset"]
        sub_dataset = kwargs["sub_dataset"]
        host_id = kwargs["host_id"]
        start_ns = kwargs["start_ns"]
        end_ns = kwargs["end_ns"]
        filters: Sequence[NodeFilter] = kwargs.get("filters", [])
        tag = _filters_tag(filters) # distinguish plots wrt all configurations
        coars = kwargs.get("concentration_coarsening", CONCENTRATION_COARSENING)
        return (
            f"{dataset}/{sub_dataset}/{host_id}/"
            f"components_{start_ns}-{end_ns}_{tag}_k{coars}"
        )

    def retrieve_data(self, **kwargs: Any) -> Any:
        dataset = kwargs["dataset"]
        sub_dataset = kwargs["sub_dataset"]
        host_id = kwargs["host_id"]
        start_ns = kwargs["start_ns"]
        end_ns = kwargs["end_ns"]
        filters: List[NodeFilter] = list(kwargs.get("filters", []))
        bin_width_ns = kwargs.get("bin_width_ns", DEFAULT_BIN_WIDTH_NS)
        r_range = list(kwargs.get("r_range", DEFAULT_R_RANGE))
        n_inits = kwargs.get("n_inits", DEFAULT_N_INITS)
        max_iter = kwargs.get("max_iter", DEFAULT_MAX_ITER)
        tol = kwargs.get("tol", DEFAULT_TOL)
        cc_threshold = kwargs.get("cc_threshold", DEFAULT_CC_THRESHOLD)
        concentration_coarsening = kwargs.get("concentration_coarsening", CONCENTRATION_COARSENING)

        print(f"\t[regularity] host={host_id}  filters={[f.describe() for f in filters]}")
        graphs = build_filtered_host_graphs(
            dataset=dataset, sub_dataset=sub_dataset,
            start_ns=start_ns, end_ns=end_ns,
            filters=filters, bin_width_ns=bin_width_ns,
            host_ids=[host_id],
        )
        if host_id not in graphs:
            print(f"\t[regularity] host {host_id} produced no events in window")
            return {
                "host_id": host_id,
                "meta": {"N": 0, "n_events": 0, "S": 0},
                "empty": True,
            }

        hd = graphs[host_id]
        tensor = hd["tensor"]
        print(f"\t[regularity] N={hd['meta']['N']}  S={hd['meta']['S']}  nnz={tensor.nnz}")
        if tensor.nnz == 0 or hd["meta"]["N"] == 0:
            return {"host_id": host_id, "meta": hd["meta"],
                    "funnel": hd["funnel"], "empty": True}

        sweep = run_sweep(
            tensor, r_range, n_inits=n_inits, max_iter=max_iter,
            tol=tol, verbose=True,
        )
        sweep_table = pd.DataFrame([{
            "R": e["R"], "rel_error": e["rel_error"],
            "core_consistency": e["core_consistency"],
            "explained_pct": (1 - e["rel_error"] ** 2) * 100,
            "elapsed_s": e["elapsed_s"],
        } for e in sweep])

        best = _select_best(sweep, cc_threshold)
        A, B, C = best["factors"]
        analysis = analyze_components(A, B, C, concentration_coarsening=concentration_coarsening)

        # drop factor copies from the other sweep entries
        for e in sweep:
            if e is not best:
                e.pop("factors", None)

        gc.collect()
        return {
            "host_id": host_id,
            "meta": hd["meta"],
            "funnel": hd["funnel"],
            "tensor": tensor,
            "A": A, "B": B, "C": C,
            "R_best": best["R"],
            "rel_error": best["rel_error"],
            "core_consistency": best["core_consistency"],
            "explained_pct": (1 - best["rel_error"] ** 2) * 100,
            "sweep_table": sweep_table,
            "analysis": analysis,
            "uuid_to_idx": hd["uuid_to_idx"],
            "idx_to_uuid": hd["idx_to_uuid"],
            "empty": False,
        }

    def make_plot(self, data: Any, **kwargs: Any) -> Figure:
        return render_components_figure(
            data,
            dataset=kwargs.get("dataset"),
            sub_dataset=kwargs.get("sub_dataset"),
        )

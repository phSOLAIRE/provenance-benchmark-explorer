"""
RegularityHostSweepPlot

For one
    (dataset, sub_dataset, window, filter-pipeline, coarsening):

    1. builds filtered information-flow tensors for every host in the window
    2. runs the NTF sweep + per-component scoring once per host
    3. frees memory of the tensor and sweep factors after scoring
    4. caches one pickle with per-host {A, B, C, analysis, sweep_table, meta, funnel}, 
        + two tables

            * <rel_path>_condensed.csv
                (% explained, % nodes kept, regime fractions, fallback flag).
            * <rel_path>_lookup.csv
                one row per host with granualr values for sanity checking

    5. on run(), renders a per-host component figure

Does incremental saves incase jobs fail.
"""
from __future__ import annotations

import gc
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.plotting.config import apply_style, palette
from provenance_explorer.registry.registry_all import FIGURES_ROOT

from provenance_explorer.analysis.activity_realism.activity_regularity.regularity_components_plot import(
    _select_best, 
    _filters_tag,
)
from provenance_explorer.analysis.activity_realism.activity_regularity._components_figure import (
    render_components_figure,
    render_empty_figure,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.filtered_graph_builder import (
    build_filtered_host_graphs,
    DEFAULT_MAX_NODES_FALLBACK,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.graph_filters import (
    NodeFilter,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.mttkrp_helpers import (
    run_sweep,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.component_metrics import (
    analyze_components,
    best_explained_variance_under,
    CONCENTRATION_COARSENING,
)


NS_PER_SEC = 1_000_000_000
DEFAULT_BIN_WIDTH_NS = 5 * 60 * NS_PER_SEC
DEFAULT_R_RANGE = list(range(1, 15))
DEFAULT_N_INITS = 5
DEFAULT_MAX_ITER = 100
DEFAULT_TOL = 1e-4
DEFAULT_CC_THRESHOLD = 50.0


def _score_host(
    hd: dict,
    r_range: Sequence[int],
    n_inits: int,
    max_iter: int,
    tol: float,
    cc_threshold: float,
    concentration_coarsening: int,
) -> dict:
    """
    Run NTF sweep + analyze_components for a single host from build_filtered_host_graphs.
    """
    host_id = hd["meta"]["host_id"]
    tensor = hd["tensor"]
    meta = hd["meta"]
    funnel = hd["funnel"]

    if tensor.nnz == 0 or meta["N"] == 0:
        return {
            "host_id": host_id,
            "meta": meta,
            "funnel": funnel,
            "empty": True,
        }

    sweep = run_sweep(
        tensor, list(r_range), n_inits=n_inits, max_iter=max_iter,
        tol=tol, verbose=False,
    )
    sweep_table = pd.DataFrame([{
        "R": e["R"], "rel_error": e["rel_error"],
        "core_consistency": e["core_consistency"],
        "explained_pct": (1 - e["rel_error"] ** 2) * 100,
        "elapsed_s": e["elapsed_s"],
    } for e in sweep])

    best = _select_best(sweep, cc_threshold)
    A, B, C = best["factors"]
    analysis = analyze_components(
        A, B, C, concentration_coarsening=concentration_coarsening,
    )

    for e in sweep:
        if e is not best:
            e.pop("factors", None)

    return {
        "host_id": host_id,
        "meta": meta,
        "funnel": funnel,
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


def _condensed_row(payload: dict) -> dict:
    meta = payload["meta"]
    hid = payload["host_id"]
    if payload.get("empty", False):
        return {
            "host_id": hid,
            "N": meta.get("N", 0),
            "N_orig": meta.get("N_orig", 0),
            "pct_nodes_kept": 0.0,
            "pct_events_kept": 0.0,
            "explained_pct": float("nan"),
            "R_best": 0,
            "pct_periodic": 0.0,
            "pct_bursty": 0.0,
            "pct_aperiodic": 0.0,
            "pct_noise": 0.0,
            "fallback_triggered": bool(meta.get("fallback_triggered", False)),
            "empty": True,
        }
    frac = payload["analysis"].regime_fractions
    N_orig = meta.get("N_orig") or 0
    n_events_orig = meta.get("n_events_orig") or 0
    return {
        "host_id": hid,
        "N": meta.get("N", 0),
        "N_orig": N_orig,
        "pct_nodes_kept": (meta.get("N", 0) / N_orig * 100.0) if N_orig else 0.0,
        "pct_events_kept": meta.get("kept_frac", 0.0) * 100.0,
        "explained_pct": float(payload["explained_pct"]),
        "R_best": int(payload["R_best"]),
        "pct_periodic": 100.0 * frac.get("periodic", 0.0),
        "pct_bursty": 100.0 * frac.get("bursty", 0.0),
        "pct_aperiodic": 100.0 * frac.get("aperiodic", 0.0),
        "pct_noise": 100.0 * frac.get("noise", 0.0),
        "fallback_triggered": bool(meta.get("fallback_triggered", False)),
        "empty": False,
    }


def _lookup_row(payload: dict) -> dict:
    meta = payload["meta"]
    hid = payload["host_id"]
    base = {
        "dataset": meta.get("dataset"),
        "sub_dataset": meta.get("sub_dataset"),
        "host_id": hid,
        "start_ns": meta.get("start_ns"),
        "end_ns": meta.get("end_ns"),
        "bin_width_ns": meta.get("bin_width_ns"),
        "S": meta.get("S"),
        "N": meta.get("N", 0),
        "N_orig": meta.get("N_orig", 0),
        "n_events": meta.get("n_events", 0),
        "n_events_orig": meta.get("n_events_orig", 0),
        "kept_frac": meta.get("kept_frac", 0.0),
        "filters": "|".join(meta.get("filters", [])),
        "max_nodes_fallback": meta.get("max_nodes_fallback"),
        "fallback_triggered": bool(meta.get("fallback_triggered", False)),
        "empty": bool(payload.get("empty", False)),
    }
    if payload.get("empty", False):
        return base

    an = payload["analysis"]
    sweep_table = payload["sweep_table"]
    bev = best_explained_variance_under(sweep_table, max_R=25)

    base.update({
        "R_best": int(payload["R_best"]),
        "rel_error": float(payload["rel_error"]),
        "core_consistency": float(payload["core_consistency"]),
        "explained_pct": float(payload["explained_pct"]),
        "best_explained_pct_under_R25": float(bev) if bev is not None else float("nan"),
        "n_assigned_nodes": int(an.n_assigned),
        "regime_periodic_frac": float(an.regime_fractions.get("periodic", 0.0)),
        "regime_bursty_frac": float(an.regime_fractions.get("bursty", 0.0)),
        "regime_aperiodic_frac": float(an.regime_fractions.get("aperiodic", 0.0)),
        "regime_noise_frac": float(an.regime_fractions.get("noise", 0.0)),
        "regime_periodic_count": int(an.regime_node_counts.get("periodic", 0)),
        "regime_bursty_count": int(an.regime_node_counts.get("bursty", 0)),
        "regime_aperiodic_count": int(an.regime_node_counts.get("aperiodic", 0)),
        "regime_noise_count": int(an.regime_node_counts.get("noise", 0)),
        "max_relevance_component_regime": str(
            an.scores.loc[an.scores["relevance"].idxmax(), "regime"]
        ) if len(an.scores) else None,
    })
    return base


class RegularityHostSweepPlot(PlotPipeline):
    """
    Dataset+sub_dataset scoped regularity sweep over all hosts.
    {
        "scope": {...},
        "hosts": {host_id: payload, ...},  # resume-friendly, possibly partial
        "done":  bool,
    }
    so each payload matches RegularityComponentsPlot.retrieve_data output.
    """

    @property
    def cache_suffix(self) -> str:
        return "pkl"

    def relative_path(self, **kwargs: Any) -> str:
        dataset = kwargs["dataset"]
        sub_dataset = kwargs["sub_dataset"]
        start_ns = kwargs["start_ns"]
        end_ns = kwargs["end_ns"]
        filters: Sequence[NodeFilter] = kwargs.get("filters", [])
        tag = _filters_tag(filters)
        coars = kwargs.get("concentration_coarsening", CONCENTRATION_COARSENING)
        fallback = kwargs.get("max_nodes_fallback", DEFAULT_MAX_NODES_FALLBACK)
        fb_tag = f"fb{fallback}" if fallback else "nofb"
        return (
            f"{dataset}/{sub_dataset}/"
            f"sweep_{start_ns}-{end_ns}_{tag}_k{coars}_{fb_tag}"
        )

    # Resumeable retrieve_data
    def retrieve_data(self, **kwargs: Any) -> Dict[str, Any]:
        dataset = kwargs["dataset"]
        sub_dataset = kwargs["sub_dataset"]
        start_ns = kwargs["start_ns"]
        end_ns = kwargs["end_ns"]
        filters: List[NodeFilter] = list(kwargs.get("filters", []))
        bin_width_ns = kwargs.get("bin_width_ns", DEFAULT_BIN_WIDTH_NS)
        r_range = list(kwargs.get("r_range", DEFAULT_R_RANGE))
        n_inits = kwargs.get("n_inits", DEFAULT_N_INITS)
        max_iter = kwargs.get("max_iter", DEFAULT_MAX_ITER)
        tol = kwargs.get("tol", DEFAULT_TOL)
        cc_threshold = kwargs.get("cc_threshold", DEFAULT_CC_THRESHOLD)
        concentration_coarsening = kwargs.get(
            "concentration_coarsening", CONCENTRATION_COARSENING,
        )
        max_nodes_fallback = kwargs.get(
            "max_nodes_fallback", DEFAULT_MAX_NODES_FALLBACK,
        )
        host_allowlist: Optional[Sequence[str]] = kwargs.get("host_allowlist")

        # resume from partial cache if present
        existing: Dict[str, Any] = {"scope": None, "hosts": {}, "done": False}
        cache_path = self.cache_path(**kwargs)
        if cache_path.is_file():
            try:
                existing = self._load(cache_path)
                if not isinstance(existing, dict) or "hosts" not in existing:
                    existing = {"scope": None, "hosts": {}, "done": False}
            except Exception as e:
                print(f"\t[sweep] could not reuse partial cache: {e!r}")
                existing = {"scope": None, "hosts": {}, "done": False}

        scope = {
            "dataset": dataset, "sub_dataset": sub_dataset,
            "start_ns": start_ns, "end_ns": end_ns,
            "filters": [f.describe() for f in filters],
            "bin_width_ns": bin_width_ns,
            "r_range": r_range, "n_inits": n_inits,
            "max_iter": max_iter, "tol": tol, "cc_threshold": cc_threshold,
            "concentration_coarsening": concentration_coarsening,
            "max_nodes_fallback": max_nodes_fallback,
        }
        existing["scope"] = scope

        print(f"[sweep] {dataset}/{sub_dataset}  window=[{start_ns},{end_ns})  "
              f"filters={scope['filters']}  fallback={max_nodes_fallback}")

        graphs = build_filtered_host_graphs(
            dataset=dataset, sub_dataset=sub_dataset,
            start_ns=start_ns, end_ns=end_ns,
            filters=filters, bin_width_ns=bin_width_ns,
            host_ids=host_allowlist,
            max_nodes_fallback=max_nodes_fallback,
        )

        host_ids = sorted(graphs.keys())
        print(f"[sweep] {len(host_ids)} hosts to process "
              f"(cached already: {len(existing['hosts'])})")

        for idx, hid in enumerate(host_ids, start=1):
            if hid in existing["hosts"] and not existing["hosts"][hid].get("empty", True):
                # host already processed in a previous run and wasnt empty
                print(f"\t[sweep] ({idx}/{len(host_ids)}) host={hid}  [cached]")
                graphs.pop(hid, None)
                continue

            hd = graphs.pop(hid)  # detach from dict so the rest can be freed
            print(f"\t[sweep] ({idx}/{len(host_ids)}) host={hid}  "
                  f"N={hd['meta']['N']}  S={hd['meta']['S']}  nnz={hd['tensor'].nnz}")
            payload = _score_host(
                hd, r_range=r_range, n_inits=n_inits, max_iter=max_iter,
                tol=tol, cc_threshold=cc_threshold,
                concentration_coarsening=concentration_coarsening,
            )
            existing["hosts"][hid] = payload

            # free heavy things tied to this host
            del hd
            gc.collect()

            # incremental save so a crash mid-sweep is not total loss
            self._save(existing, cache_path)

        existing["done"] = True
        self._save(existing, cache_path)
        print(f"[sweep] done — {len(existing['hosts'])} hosts in cache")
        return existing

    # Overview figure + per-host figure fan-out
    def make_plot(self, data: Dict[str, Any], **kwargs: Any) -> Figure:
        apply_style()
        return self._render_overview(data, **kwargs)

    def run(
        self,
        override_plot_size=None,
        render_per_host: bool = True,
        **kwargs: Any,
    ) -> Figure:
        """
        Full pipeline: ensure data exists, write condensed + lookup CSVs, 
        render the overview figure, and render one component figure per host next to it.
        """
        data = self.data_retrieval(**kwargs)

        self._write_tables(data, **kwargs)

        fig = self.make_plot(data, **kwargs)
        self._save_figure(fig, override_plot_size, **kwargs)

        if render_per_host:
            self._render_and_save_host_figures(data, **kwargs)

        return fig

    # tables
    def _tables_paths(self, **kwargs: Any) -> Dict[str, Path]:
        rel = self.relative_path(**kwargs)
        base = self.cache_path(**kwargs).parent
        return {
            "condensed": base / f"{Path(rel).name}_condensed.csv",
            "lookup": base / f"{Path(rel).name}_lookup.csv",
        }

    def _write_tables(self, data: Dict[str, Any], **kwargs: Any) -> None:
        hosts = data.get("hosts", {})
        if not hosts:
            return
        condensed_rows = [_condensed_row(p) for p in hosts.values()]
        lookup_rows = [_lookup_row(p) for p in hosts.values()]
        condensed = pd.DataFrame(condensed_rows).sort_values("host_id").reset_index(drop=True)
        lookup = pd.DataFrame(lookup_rows).sort_values("host_id").reset_index(drop=True)

        paths = self._tables_paths(**kwargs)
        paths["condensed"].parent.mkdir(parents=True, exist_ok=True)
        condensed.to_csv(paths["condensed"], index=False)
        lookup.to_csv(paths["lookup"], index=False)
        print(f"[table] {paths['condensed']}")
        print(f"[table] {paths['lookup']}")

    # Overview plot
    def _render_overview(self, data: Dict[str, Any], **kwargs: Any) -> Figure:
        hosts = data.get("hosts", {})
        scope = data.get("scope", {}) or {}

        if not hosts:
            fig, ax = plt.subplots(figsize=(6, 2))
            ax.text(0.5, 0.5, "no hosts in sweep",
                    ha="center", va="center", transform=ax.transAxes)
            ax.axis("off")
            return fig

        rows = [_condensed_row(p) for p in hosts.values()]
        df = pd.DataFrame(rows).sort_values("host_id").reset_index(drop=True)

        # two panel
        pal = palette()
        regime_order = ["periodic", "bursty", "aperiodic", "noise"]
        regime_colors = {
            "periodic": pal[0], "bursty": pal[2],
            "aperiodic": pal[3], "noise": "#b0b0b0",
        }

        n = len(df)
        fig_h = max(3.2, 0.35 * n + 2.2)
        fig, (ax_top, ax_bot) = plt.subplots(
            2, 1, figsize=(12, fig_h),
            gridspec_kw={"height_ratios": [1.0, 1.6], "hspace": 0.35},
        )

        y = np.arange(n)
        labels = [h[:8] + "…" if len(h) > 10 else h for h in df["host_id"]]

        # top: explained_pct + nodes kept
        ax_top.barh(y - 0.2, df["explained_pct"], height=0.38,
                    color=pal[0], label="explained %")
        ax_top.barh(y + 0.2, df["pct_nodes_kept"], height=0.38,
                    color=pal[4], label="nodes kept %")
        ax_top.set_yticks(y)
        ax_top.set_yticklabels(labels, fontsize=7)
        ax_top.invert_yaxis()
        ax_top.set_xlim(0, 100)
        ax_top.set_xlabel("%")
        ax_top.legend(fontsize=7, loc="lower right")
        ax_top.set_title(
            f"{scope.get('dataset')}/{scope.get('sub_dataset')}   "
            f"hosts={n}   window=[{scope.get('start_ns')}, {scope.get('end_ns')})",
            fontsize=9, loc="left",
        )
        for i, row in df.iterrows():
            if row["fallback_triggered"]:
                ax_top.text(
                    101, i, "⚑ fallback", fontsize=6, va="center", color="#b00020",
                )
        ax_top.set_xlim(0, 115)

        # bottom: stacked regime fractions
        left = np.zeros(n)
        for g in regime_order:
            col = f"pct_{g}"
            vals = df[col].to_numpy()
            ax_bot.barh(y, vals, left=left, color=regime_colors[g],
                        height=0.7, label=g)
            left += vals
        ax_bot.set_yticks(y)
        ax_bot.set_yticklabels(labels, fontsize=7)
        ax_bot.invert_yaxis()
        ax_bot.set_xlim(0, 100)
        ax_bot.set_xlabel("node regime share (%)")
        ax_bot.legend(fontsize=7, loc="lower right", ncol=4)

        return fig

    # Per-host component figures
    def _host_figures_dir(self, **kwargs: Any) -> Path:
        rel = self.relative_path(**kwargs)
        # FIGURES_ROOT / <plot_name> / <rel>.png is the overview;
        # host figures live in a sibling directory named <rel>_hosts/.
        return FIGURES_ROOT / self.plot_name / f"{rel}_hosts"

    def _render_and_save_host_figures(
        self, data: Dict[str, Any], **kwargs: Any,
    ) -> None:
        hosts = data.get("hosts", {})
        if not hosts:
            return
        out_dir = self._host_figures_dir(**kwargs)
        out_dir.mkdir(parents=True, exist_ok=True)
        dataset = kwargs.get("dataset")
        sub_dataset = kwargs.get("sub_dataset")
        for hid in sorted(hosts.keys()):
            payload = hosts[hid]
            try:
                if payload.get("empty", False):
                    fig = render_empty_figure(hid, title_suffix=f"({dataset}/{sub_dataset})")
                else:
                    fig = render_components_figure(
                        payload, dataset=dataset, sub_dataset=sub_dataset,
                    )
                path = out_dir / f"{hid}.png"
                fig.savefig(path)
                plt.close(fig)
                print(f"[host-fig]   {path}")
            except Exception as e:
                print(f"[host-fig]   {hid} FAILED: {e!r}")
                plt.close("all")

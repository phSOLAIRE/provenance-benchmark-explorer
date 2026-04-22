"""
Per-host component figure renderer; shared between 
    * per-host regularity_components_plot
    * per-subdataset: regularity_host_sweep

Input is a dict as such: 
    {
        "host_id", "meta", "A", "B", "C",
        "R_best", "rel_error", "core_consistency", "explained_pct",
        "sweep_table", "analysis",
        ...
    }

needs: meta, A, B, C, analysis.scores, R_best, core_consistency, explained_pct, sweep_table
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec

from provenance_explorer.plotting.config import apply_style, palette
from provenance_explorer.analysis.activity_realism.activity_regularity.component_metrics import (
    best_explained_variance_under,
    PERIODICITY_THRESHOLD, BURSTINESS_THRESHOLD, CONCENTRATION_THRESHOLD,
)


def _regime_colors() -> Dict[str, str]:
    pal = palette()
    return {
        "periodic": pal[0],
        "bursty": pal[2],
        "aperiodic": pal[3],
        "noise": "#b0b0b0", # generic gray
    }


def render_empty_figure(host_id: str, title_suffix: str = "") -> Figure:
    fig, ax = plt.subplots(figsize=(6, 2))
    ax.text(
        0.5, 0.5,
        f"No events {host_id} {title_suffix}, check timespan".strip(),
        ha="center", va="center", transform=ax.transAxes,
    )
    ax.axis("off")
    return fig


def render_components_figure(
    data: Dict[str, Any],
    dataset: Optional[str] = None,
    sub_dataset: Optional[str] = None,
) -> Figure:
    """
    Render one component-per-row figure for a single host's NTF result.
    """
    apply_style()

    if data.get("empty", False):
        return render_empty_figure(data.get("host_id", ""))

    A, B, C = data["A"], data["B"], data["C"]
    analysis = data["analysis"]
    scores = analysis.scores
    regime_fractions = analysis.regime_fractions
    meta = data["meta"]
    sweep_table = data["sweep_table"]

    order = scores.sort_values("relevance", ascending=False)["r"].tolist()
    R = len(order)
    bev = best_explained_variance_under(sweep_table, max_R=25)

    fallback_str = (
        "   [fallback: TopK was applied]" if meta.get("fallback_triggered") else ""
    )
    header_lines = [
        f"{dataset or meta.get('dataset')}/"
        f"{sub_dataset or meta.get('sub_dataset')}  host={data['host_id']}{fallback_str}",
        f"N={meta.get('N')} (orig {meta.get('N_orig')})  S={meta.get('S')}  "
        f"n_events={meta.get('n_events')}  kept_frac={meta.get('kept_frac', 0):.2f}",
        f"R_best={data['R_best']}  CC={data['core_consistency']:.1f}%  "
        f"explained={data['explained_pct']:.1f}%  "
        f"(best under R<=25: {bev:.1f}%)" if bev is not None else "",
        f"regime fractions (nodes) — periodic: {regime_fractions.get('periodic', 0):.2f}   "
        f"bursty: {regime_fractions.get('bursty', 0):.2f}   "
        f"aperiodic: {regime_fractions.get('aperiodic', 0):.2f}   "
        f"noise: {regime_fractions.get('noise', 0):.2f}",
    ]

    fig = plt.figure(figsize=(14, 1.5 + 1.8 * R))
    gs = GridSpec(
        R + 1, 4, figure=fig,
        height_ratios=[0.6] + [1.0] * R,
        width_ratios=[2.4, 1.6, 1.6, 1.4],
        hspace=0.55, wspace=0.28,
    )

    ax_header = fig.add_subplot(gs[0, :])
    ax_header.axis("off")
    ax_header.text(
        0.0, 0.5, "\n".join(l for l in header_lines if l),
        ha="left", va="center", fontsize=9, family="monospace",
    )

    regime_color = _regime_colors()

    def _draw_factor(ax, v, ylabel, color):
        v = np.asarray(v, dtype=np.float64)
        x = np.arange(v.size)
        vmax = v.max() if v.size else 0.0
        floor = max(vmax * 1e-4, 1e-12)
        ax.vlines(
            x, floor, np.maximum(v, floor),
            color=color, linewidth=0.5, alpha=0.9,
        )
        ax.set_yscale("log")
        ax.set_xlim(0, max(1, v.size - 1))
        if vmax > 0:
            ax.set_ylim(bottom=floor, top=vmax * 2.0)
        ax.set_ylabel(ylabel, fontsize=7)
        ax.set_xlabel("node index", fontsize=7)
        ax.tick_params(labelsize=6)

    for row, r in enumerate(order, start=1):
        row_scores = scores.loc[scores["r"] == r].iloc[0]
        rel = float(row_scores["relevance"])
        per = float(row_scores["periodicity"])
        burst = float(row_scores["burstiness"])
        conc = float(row_scores["concentration"])
        regime = str(row_scores["regime"])
        color = regime_color.get(regime, "#444")

        # 1. temporal profile
        ax_c = fig.add_subplot(gs[row, 0])
        ax_c.plot(C[:, r], color=color, linewidth=0.9)
        ax_c.fill_between(np.arange(C.shape[0]), C[:, r], alpha=0.15, color=color)
        ax_c.set_xlim(0, C.shape[0] - 1)
        ax_c.set_ylabel(f"C[:,{r}]", fontsize=7)
        ax_c.tick_params(labelsize=6)
        ax_c.set_title(
            f"component r={r}   relevance={rel:.3f}", loc="left", fontsize=8,
        )

        # 2. A / 3. B — original node index order, log y
        _draw_factor(fig.add_subplot(gs[row, 1]), A[:, r], f"A[:,{r}] (src)", color)
        _draw_factor(fig.add_subplot(gs[row, 2]), B[:, r], f"B[:,{r}] (dst)", color)

        # 4. score box
        ax_s = fig.add_subplot(gs[row, 3])
        ax_s.axis("off")
        lines = [
            f"regime       : {regime}",
            f"relevance    : {rel:.3f}",
            f"periodicity  : {per:.3f}   (>{PERIODICITY_THRESHOLD:.1f} -> periodic)",
            f"burstiness   : {burst:.3f}   (>{BURSTINESS_THRESHOLD:.1f} -> bursty/aperiodic)",
            f"concentration: {conc:.3f}   (>{CONCENTRATION_THRESHOLD:.1f} -> bursty, else aperiodic)",
            f"||a||        : {np.linalg.norm(A[:, r]):.2f}",
            f"||b||        : {np.linalg.norm(B[:, r]):.2f}",
            f"||c||        : {np.linalg.norm(C[:, r]):.2f}",
        ]
        ax_s.text(
            0.0, 1.0, "\n".join(lines),
            ha="left", va="top", fontsize=7.5, family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", fc="white",
                      ec=color, lw=1.2, alpha=0.95),
            transform=ax_s.transAxes,
        )

    return fig

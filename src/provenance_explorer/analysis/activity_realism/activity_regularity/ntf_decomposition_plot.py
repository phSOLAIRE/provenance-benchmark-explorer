"""
NtfDecompositionPlot

Non-negative tensor factorization of the information-flow graph for one dataset/sub_dataset/time-window combination. 
Produces per-host two figures: 
    - (left) original tensor scatter coloured by timestep with density curve,
    - (right) the reconstructed tensor from the best CP decomposition whose CC exceeds 50 %

Caches a lot of things needed for secondary analysis of the temporal factor C (time-series of component activations):

Cached dict (pkl) structure, keyed by host_id:
    {
        host_id: {
            "tensor":       SparseTensor3,
            "A":            np.ndarray (N, R_best),
            "B":            np.ndarray (N, R_best),
            "C":            np.ndarray (S, R_best),
            "R_best":       int,
            "sweep_table":  pd.DataFrame  [R, rel_error, core_consistency, explained_pct, elapsed_s],
            "meta": {
                "N", "N_orig", "S", "n_events", "n_events_orig",
                "kept_frac", "bin_width_ns", "start_ns", "end_ns",
            },
            "idx_to_uuid":  dict[int, str],   # reverse of remap
            "uuid_to_idx":  dict[str, int],   # original remap
        },
        ...
    }

Example usage in notebook:

    from provenance_explorer.analysis.activity_realism.activity_regularity.ntf_decomposition_plot import NtfDecompositionPlot
    from provenance_explorer.plotting import apply_style
    from provenance_explorer.utils.time_conversion import date_string_to_ns_timestamp

    apply_style()

    plot = NtfDecompositionPlot()
    # plot.invalidate(
    #     dataset="e3",
    #     sub_dataset="cadets",
    #     start_ns=date_string_to_ns_timestamp("2018-04-07 00:00:00"),
    #     end_ns=date_string_to_ns_timestamp("2018-04-12 00:00:00"),
    # )
    fig  = plot.run(
        dataset="e3",
        sub_dataset="cadets",
        start_ns=date_string_to_ns_timestamp("2018-04-07 00:00:00"),
        end_ns=date_string_to_ns_timestamp("2018-04-12 00:00:00"),
    )
"""
from __future__ import annotations

import gc
from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from scipy.sparse import lil_matrix, csr_matrix

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.common_record.schema import EdgeCategory
from provenance_explorer.common_record import iterate_common_records, DropLog

from provenance_explorer.analysis.activity_realism.activity_regularity.mttkrp_helpers import (
    SparseTensor3,
    build_sparse_tensor,
    run_sweep,
    select_R,
    sparse_nonneg_cp,
)

# ── flow direction (same convention as your notebook) ────────────────────────
FLOW_DIRECTION = {
    EdgeCategory.FORK:    True,
    EdgeCategory.EXECUTE: False,
    EdgeCategory.READ:    False,
    EdgeCategory.WRITE:   True,
    EdgeCategory.SEND:    True,
    EdgeCategory.RECV:    False,
}

# default parameters (overridable via kwargs)
NS_PER_SEC     = 1_000_000_000
BIN_WIDTH_NS   = 60 * NS_PER_SEC
MAX_NODES      = 3000
R_RANGE        = range(1,26)
N_INITS        = 4
MAX_ITER       = 100
ALS_TOL        = 1e-4
CC_THRESHOLD   = 50.0


# data collection
def _load_provenance_sparse(
    dataset: str,
    sub_dataset: str,
    start_ns: int,
    end_ns: int,
    bin_width_ns: int = BIN_WIDTH_NS,
    max_nodes: int = MAX_NODES,
) -> Dict[str, dict]:
    """
    Single iterator pass: bin every common record into a sparse 3-way tensor per host, 
    pruning to the top-max_nodes most active nodes.
    """
    n_bins = int((end_ns - start_ns) // bin_width_ns) + 1

    host_events_raw: Dict[str, List[tuple]] = defaultdict(list)
    logger = DropLog()
    it = iterate_common_records(
        dataset, sub_dataset, drop_log=logger, t_start=start_ns, t_end=end_ns,
        # test_run_seconds=60,
    )

    n_total = 0
    for rec in it:
        cat = rec.edge_category
        if cat not in FLOW_DIRECTION:
            continue
        if FLOW_DIRECTION[cat]:
            src, dst = rec.subject_uuid, rec.object_uuid
        else:
            src, dst = rec.object_uuid, rec.subject_uuid
        b = int((rec.timestamp_ns - start_ns) // bin_width_ns)
        if 0 <= b < n_bins:
            host_events_raw[rec.host_id].append((b, src, dst))
            n_total += 1
        if n_total % 10_000_000 == 0:
            print(f"\t{n_total / 1e6:.0f}M records ingested")

    logger.summary(dataset, sub_dataset)

    results: Dict[str, dict] = {}
    for hid, raw_events in host_events_raw.items():
        # activity counts for pruning
        act: Dict[str, int] = defaultdict(int)
        for (b, s, d) in raw_events:
            act[s] += 1
            act[d] += 1

        N_orig = len(act)
        if N_orig > max_nodes:
            top = sorted(act, key=act.get, reverse=True)[:max_nodes]  # type: ignore
            keep = set(top)
        else:
            keep = set(act.keys())

        uuid_to_idx = {uuid: idx for idx, uuid in enumerate(sorted(keep))}
        idx_to_uuid = {idx: uuid for uuid, idx in uuid_to_idx.items()}
        N = len(uuid_to_idx)

        events = []
        for (b, s, d) in raw_events:
            if s in uuid_to_idx and d in uuid_to_idx:
                events.append((b, uuid_to_idx[s], uuid_to_idx[d]))

        kept_frac = len(events) / len(raw_events) if raw_events else 0.0
        tensor = build_sparse_tensor(events, N, n_bins)

        results[hid] = {
            "tensor": tensor,
            "meta": {
                "N": N,
                "N_orig": N_orig,
                "S": n_bins,
                "n_events": len(events),
                "n_events_orig": len(raw_events),
                "kept_frac": kept_frac,
                "bin_width_ns": bin_width_ns,
                "start_ns": start_ns,
                "end_ns": end_ns,
            },
            "uuid_to_idx": uuid_to_idx,
            "idx_to_uuid": idx_to_uuid,
        }
        del raw_events, events
        gc.collect()

    return results


def _run_sweep_and_select(
    host_data: dict,
    r_range: List[int],
    n_inits: int,
    max_iter: int,
    tol: float,
    cc_threshold: float,
) -> dict:
    """
    Run the R-sweep for one host tensor and attach the best factors + table.
    Mutates host_data in-place and returns it.
    """
    tensor = host_data["tensor"]
    sweep = run_sweep(
        tensor, r_range, n_inits=n_inits, max_iter=max_iter, tol=tol, verbose=True,
    )

    # build tidy table (without the heavy factor arrays)
    rows = []
    for entry in sweep:
        rows.append({
            "R":                entry["R"],
            "rel_error":        entry["rel_error"],
            "core_consistency": entry["core_consistency"],
            "explained_pct":    (1 - entry["rel_error"] ** 2) * 100,
            "elapsed_s":        entry["elapsed_s"],
        })
    sweep_table = pd.DataFrame(rows)

    # selection: lowest-error R with CC ≥ threshold, fallback to R=1
    viable = [e for e in sweep if e["core_consistency"] >= cc_threshold]
    if viable:
        best = min(viable, key=lambda e: e["rel_error"])
    else:
        # fallback: pick R=1 entry (always first in r_range by convention)
        r1_entries = [e for e in sweep if e["R"] == 1]
        if r1_entries:
            best = r1_entries[0]
        else:
            best = sweep[0]

    A, B, C = best["factors"]

    host_data["A"] = A
    host_data["B"] = B
    host_data["C"] = C
    host_data["R_best"] = best["R"]
    host_data["sweep_table"] = sweep_table

    # free the factor copies sitting inside sweep entries
    for entry in sweep:
        entry.pop("factors", None)

    gc.collect()
    return host_data


# reconstruction helper
def _reconstruct_tensor(
    A: np.ndarray, B: np.ndarray, C: np.ndarray, n_slices: int,
) -> List[csr_matrix]:
    """
    Reconstruct T_hat ~~ [[A, B, C]] as a list of sparse CSR slices.
    Only stores entries above a small threshold to keep memory bounded.
    """
    slices = []
    for k in range(n_slices):
        # T_k = A @ diag(C[k,:]) @ B.T = sum_r c_kr * a_r (x) b_r
        Sk_dense = (A * C[k, :][np.newaxis, :]) @ B.T
        Sk_dense = np.maximum(Sk_dense, 0.0)
        # threshold very small values to maintain sparsity
        Sk_dense[Sk_dense < 1e-6] = 0.0
        slices.append(csr_matrix(Sk_dense.astype(np.float32)))
        del Sk_dense
    return slices


# plotting helpers
def _collect_scatter(tensor: SparseTensor3):
    """Return (rows, cols, timesteps) arrays for every non-zero entry."""
    rows_all, cols_all, t_all = [], [], []
    for t, s in enumerate(tensor.slices):
        r, c = s.nonzero()
        rows_all.append(r)
        cols_all.append(c)
        t_all.append(np.full(len(r), t))
    return np.concatenate(rows_all), np.concatenate(cols_all), np.concatenate(t_all)


def _density_curve(tensor: SparseTensor3, coarsen_factor: int = 2):
    """Return (t_centres, coarsened_density) for the density ribbon."""
    densities = np.array([
        s.nnz / (tensor.n_rows * tensor.n_cols) for s in tensor.slices
    ])
    T = len(densities)
    T_c = T // coarsen_factor
    d_coarse = densities[: T_c * coarsen_factor].reshape(T_c, coarsen_factor).mean(axis=1)
    t_coarse = np.arange(T_c) * coarsen_factor + coarsen_factor / 2
    return t_coarse, d_coarse


def _draw_tensor_panel(
    fig,
    gs_slot,
    tensor: SparseTensor3,
    title: str,
    annotation_lines: Optional[List[str]] = None,
):
    """
    Draw the 3-row panel (density / colour strip / scatter) for one tensor
    into the given GridSpec slot.
    """
    inner = gs_slot.subgridspec(3, 1, height_ratios=[1, 0.25, 5], hspace=0.08)
    ax_d = fig.add_subplot(inner[0])
    ax_c = fig.add_subplot(inner[1])
    ax_m = fig.add_subplot(inner[2])

    T = tensor.n_slices
    n_rows = tensor.n_rows
    n_cols = tensor.n_cols

    # density curve
    t_coarse, d_coarse = _density_curve(tensor)
    ax_d.plot(t_coarse, d_coarse, color="#0d7d87", linewidth=0.8)
    ax_d.fill_between(t_coarse, d_coarse, alpha=0.15, color="#0d7d87")
    ax_d.set_xlim(0, T - 1)
    ax_d.set_xticks([])
    ax_d.set_ylabel("density", fontsize=7)
    ax_d.spines[["right", "top"]].set_visible(False)
    ax_d.tick_params(labelsize=6)

    # colour strip
    ax_c.imshow(
        np.linspace(0, 1, T).reshape(1, -1),
        aspect="auto", cmap="viridis", extent=[0, T - 1, 0, 1],
    )
    ax_c.set_xlim(0, T - 1)
    ax_c.set_ylim(0, 1)
    ax_c.spines[:].set_visible(False)
    ax_c.grid(False)
    n_ticks = 5
    tick_pos = np.linspace(0, T - 1, n_ticks)
    ax_c.set_xticks(tick_pos)
    ax_c.set_xticklabels([f"t={int(round(p))}" for p in tick_pos], fontsize=6)
    ax_c.tick_params(axis="x", direction="out", length=3, pad=1, colors="white")
    ax_c.set_yticks([])
    ax_c.set_title(title, loc="left", fontsize=8, pad=4)

    # scatter
    rows_all, cols_all, t_all = _collect_scatter(tensor)
    if len(rows_all) > 0:
        norm = plt.Normalize(0, T - 1) # type: ignore
        colors = cm.viridis(norm(t_all)) # type: ignore
        ax_m.scatter(
            cols_all, rows_all, c=colors, s=0.4, linewidths=0, rasterized=True,
        )
    ax_m.set_xlim(-0.5, n_cols - 0.5)
    ax_m.set_ylim(n_rows - 0.5, -0.5)
    ax_m.set_xlabel("node", fontsize=7)
    ax_m.set_ylabel("node", fontsize=7)
    ax_m.set_aspect("equal")
    ax_m.tick_params(labelsize=6)

    # annotation block (for reconstruction panel)
    if annotation_lines:
        text = "\n".join(annotation_lines)
        ax_m.text(
            0.98, 0.02, text,
            transform=ax_m.transAxes, fontsize=6,
            verticalalignment="bottom", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.85),
        )

    return ax_d, ax_c, ax_m

# pipeline
class NtfDecompositionPlot(PlotPipeline):
    """
    Per-host non-negative CP decomposition of the information-flow tensor.

    Caches tensors, factors A/B/C, node mappings, and the full R-sweep table
    so that secondary time-series analysis of C can proceed without re-iterating.
    """

    @property
    def cache_suffix(self) -> str:
        return "pkl"

    def relative_path(self, dataset: str, sub_dataset: str, **kwargs: Any) -> str:
        start_ns: int = kwargs["start_ns"]
        end_ns: int = kwargs["end_ns"]
        return f"{dataset}/{sub_dataset}/ntf_decomposition_{start_ns}-{end_ns}"

    def retrieve_data(self, dataset: str, sub_dataset: str, **kwargs: Any) -> Any:
        start_ns: int = kwargs["start_ns"]
        end_ns: int = kwargs["end_ns"]
        bin_width_ns: int = kwargs.get("bin_width_ns", BIN_WIDTH_NS)
        max_nodes: int = kwargs.get("max_nodes", MAX_NODES)
        r_range: List[int] = kwargs.get("r_range", R_RANGE)
        n_inits: int = kwargs.get("n_inits", N_INITS)
        max_iter: int = kwargs.get("max_iter", MAX_ITER)
        tol: float = kwargs.get("tol", ALS_TOL)
        cc_threshold: float = kwargs.get("cc_threshold", CC_THRESHOLD)

        print(f"\t[NTF] iterating {dataset}/{sub_dataset}  "
              f"[{start_ns} – {end_ns}], bin={bin_width_ns/NS_PER_SEC:.0f}s")

        # pass 1: build tensors
        host_data = _load_provenance_sparse(
            dataset, sub_dataset, start_ns, end_ns, bin_width_ns, max_nodes,
        )

        # pass 2: sweep + select per host
        for hid, hd in host_data.items():
            print(f"\t[NTF] sweep host={hid}  "
                  f"N={hd['meta']['N']}  S={hd['meta']['S']}  "
                  f"nnz={hd['tensor'].nnz}")
            _run_sweep_and_select(
                hd, r_range, n_inits, max_iter, tol, cc_threshold,
            )

        return host_data

    def make_plot(self, data: Dict[str, dict], dataset: str, sub_dataset: str, **kwargs: Any) -> Figure:
        """
        For each host: side-by-side original tensor vs reconstruction.
        Returns a single figure with one row per host, two columns.
        """
        hosts = sorted(data.keys())
        n_hosts = len(hosts)

        if n_hosts == 0:
            fig, _ = plt.subplots()
            return fig

        fig = plt.figure(figsize=(12, 7 * n_hosts))
        outer = GridSpec(n_hosts, 2, figure=fig, wspace=0.25, hspace=0.35)

        for row, hid in enumerate(hosts):
            hd = data[hid]
            tensor = hd["tensor"]
            meta = hd["meta"]
            A, B, C = hd["A"], hd["B"], hd["C"]
            R_best = hd["R_best"]
            sweep_table = hd["sweep_table"]

            # find the sweep row for the chosen R
            sel = sweep_table[sweep_table["R"] == R_best].iloc[0]
            rel_err = sel["rel_error"]
            cc = sel["core_consistency"]
            expl = sel["explained_pct"]

            hid_short = hid[:12] + "…" if len(hid) > 14 else hid

            # left: original tensor
            _draw_tensor_panel(
                fig, outer[row, 0], tensor,
                title=f"{dataset}/{sub_dataset}  host={hid_short}  (original)",
            )

            # right: reconstruction
            recon_slices = _reconstruct_tensor(A, B, C, tensor.n_slices)
            recon_tensor = SparseTensor3(
                slices=recon_slices,
                n_rows=tensor.n_rows,
                n_cols=tensor.n_cols,
                n_slices=tensor.n_slices,
            )

            annotation = [
                f"R = {R_best}",
                f"CC = {cc:.1f}%",
                f"rel err = {rel_err:.4f}",
                f"explained = {expl:.1f}%",
                f"events kept = {meta['kept_frac']*100:.1f}%",
                f"N = {meta['N']} / {meta['N_orig']}",
            ]

            _draw_tensor_panel(
                fig, outer[row, 1], recon_tensor,
                title=f"reconstruction  R={R_best}",
                annotation_lines=annotation,
            )

            del recon_slices, recon_tensor
            gc.collect()

        fig.suptitle(
            f"NTF Decomposition — {dataset}/{sub_dataset}",
            fontsize=11, y=1.0,
        )
        return fig

"""
Submit script runner for RegularityHostSweepPlot

python run_regularity_host_sweep.py \\
    --dataset e3 --sub-dataset cadets \\
    --start "2018-04-03 00:00:00" --end "2018-04-04 00:00:00" \\
    --bin-width-s 360 \\
    --persistence 3 \\
    --max-nodes-fallback 10000 \\
    --coarsening 10 \\
    --r-max 20 \\
    --collapse-max-depth 8 \\
    --top-k 3
"""
from __future__ import annotations

import argparse
import gc
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

from provenance_explorer.registry.registry_all import FIGURES_ROOT
from provenance_explorer.common_record.object_lookup import ObjectLookup
from provenance_explorer.analysis.activity_realism.activity_regularity.graph_filters import (
    CollapseEphemeralProcesses, PersistenceFilter,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.regularity_host_sweep_plot import (
    RegularityHostSweepPlot,
)
from provenance_explorer.analysis.activity_realism.activity_regularity._components_figure import (
    render_top_uuid_components_figure, render_empty_figure,
)


def _parse_ts(s: str) -> int:
    """Parse 'YYYY-MM-DD HH:MM:SS' (UTC) or a raw nanosecond integer string."""
    s = s.strip()
    if s.isdigit():
        return int(s)
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", required=True)
    p.add_argument("--sub-dataset", required=True)
    p.add_argument("--start", required=True, help="UTC 'YYYY-MM-DD HH:MM:SS' or ns int")
    p.add_argument("--end", required=True, help="UTC 'YYYY-MM-DD HH:MM:SS' or ns int")
    p.add_argument("--bin-width-s", type=float, default=360.0,
                   help="Time bin width in seconds (default: 360s = 6min).")
    p.add_argument("--persistence", type=int, default=3,
                   help="min_bins for both CollapseEphemeralProcesses and PersistenceFilter.")
    p.add_argument("--collapse-max-depth", type=int, default=8,
                   help="Max parent_uuid hops the collapse transform will walk.")
    p.add_argument("--max-nodes-fallback", type=int, default=10_000,
                   help="Hard TopK cap applied after the pipeline; pass 0 to disable.")
    p.add_argument("--coarsening", type=int, default=10,
                   help="Coarsening factor for component_metrics (kept for cache-key stability).")
    p.add_argument("--r-max", type=int, default=20, help="Sweep R = 1..r_max.")
    p.add_argument("--n-inits", type=int, default=4)
    p.add_argument("--max-iter", type=int, default=100)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--cc-threshold", type=float, default=50.0)
    p.add_argument("--top-k", type=int, default=3,
                   help="How many top src + top dst UUIDs to display per component.")
    p.add_argument("--host", action="append", default=None,
                   help="Restrict to specific host_id(s); may be repeated. "
                        "Default: every host found in the window.")
    p.add_argument("--invalidate", action="store_true",
                   help="Delete any pre-existing sweep pickle before retrieval.")
    p.add_argument("--skip-per-host-figures", action="store_true",
                   help="Skip the per-host PNG fan-out (cache + tables only).")
    p.add_argument("--replot-only", action="store_true",
                   help="Do not iterate the raw dataset or run NTF. Load the existing "
                        "sweep pickle and re-render tables + overview + per-host figures "
                        "from the cached data only. Errors out if no cache exists.")
    return p.parse_args(argv)


def _render_per_host(
    data: dict,
    *,
    sweep: RegularityHostSweepPlot,
    dataset: str,
    sub_dataset: str,
    lookup: Optional[ObjectLookup],
    top_k: int,
    sweep_kwargs: dict,
) -> None:
    """Render and save the top-UUID figure for every host in `data`.

    Output path mirrors the existing convention used by
    ``RegularityHostSweepPlot._render_and_save_host_figures`` so figures land alongside
    the cache pickle: ``FIGURES_ROOT/<plot_name>/<rel>_hosts/<host>.png``.
    """
    rel = sweep.relative_path(**sweep_kwargs)
    out_dir = FIGURES_ROOT / sweep.plot_name / f"{rel}_hosts"
    out_dir.mkdir(parents=True, exist_ok=True)

    hosts = data.get("hosts", {})
    if not hosts:
        print("[host-fig] no hosts to render")
        return

    n_ok = 0
    n_fail = 0
    for hid in sorted(hosts.keys()):
        payload = hosts[hid]
        try:
            if payload.get("empty", False):
                fig = render_empty_figure(hid, title_suffix=f"({dataset}/{sub_dataset})")
            else:
                fig = render_top_uuid_components_figure(
                    payload, dataset=dataset, sub_dataset=sub_dataset,
                    lookup=lookup, top_k=top_k,
                )
            path = out_dir / f"{hid}.png"
            fig.savefig(path)
            plt.close(fig)
            n_ok += 1
            print(f"[host-fig]   {path}")
        except Exception as e:
            n_fail += 1
            print(f"[host-fig]   {hid} FAILED: {e!r}")
            traceback.print_exc()
            plt.close("all")
        gc.collect()
    print(f"[host-fig] done: {n_ok} ok, {n_fail} failed -> {out_dir}")


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    start_ns = _parse_ts(args.start)
    end_ns = _parse_ts(args.end)
    if end_ns <= start_ns:
        print(f"[err] end <= start ({start_ns} >= {end_ns})", file=sys.stderr)
        return 2

    bin_width_ns = int(args.bin_width_s * 1_000_000_000)
    max_nodes_fallback = args.max_nodes_fallback if args.max_nodes_fallback > 0 else None

    print(f"[runner] {args.dataset}/{args.sub_dataset}  window=[{start_ns}, {end_ns})  "
          f"bin_width_ns={bin_width_ns}  persistence={args.persistence}")
    print(f"[runner] pipeline = CollapseEphemeralProcesses(min_bins={args.persistence}, "
          f"max_depth={args.collapse_max_depth}) | "
          f"PersistenceFilter(min_bins={args.persistence})  "
          f"(activity-floor removed; collapse + persistence + TopK only)")

    lookup = ObjectLookup.load(args.dataset, args.sub_dataset)
    if lookup is None:
        print(f"[err] no ObjectLookup cache for {args.dataset}/{args.sub_dataset}; "
              f"build it first.", file=sys.stderr)
        return 3
    print(f"[runner] loaded ObjectLookup ({lookup.mode})")

    filters = [
        CollapseEphemeralProcesses(min_bins=args.persistence, max_depth=args.collapse_max_depth),
        PersistenceFilter(min_bins=args.persistence),
    ]

    sweep = RegularityHostSweepPlot()
    sweep_kwargs = dict(
        dataset=args.dataset, sub_dataset=args.sub_dataset,
        start_ns=start_ns, end_ns=end_ns,
        filters=filters,
        bin_width_ns=bin_width_ns,
        r_range=list(range(1, args.r_max + 1)),
        n_inits=args.n_inits, max_iter=args.max_iter, tol=args.tol,
        cc_threshold=args.cc_threshold,
        concentration_coarsening=args.coarsening,
        max_nodes_fallback=max_nodes_fallback,
        host_allowlist=args.host,
        object_lookup=lookup,
    )

    cache_path = sweep.cache_path(**sweep_kwargs)
    print(f"[runner] cache path = {cache_path}")

    if args.replot_only:
        if args.invalidate:
            print("[err] --replot-only and --invalidate are mutually exclusive", file=sys.stderr)
            return 2
        if not cache_path.is_file():
            print(f"[err] --replot-only requested but no cache at {cache_path}", file=sys.stderr)
            return 4
        # Bypass data_retrieval entirely - load the pickle and re-render. The cache
        # carries A/B/C, meta (with kept_frac/N/N_orig), idx_to_uuid, and analysis,
        # which is all the new overview + per-host figures consume. No raw-data
        # iteration, no NTF refit.
        t0 = time.time()
        data = sweep._load(cache_path)
        print(f"[runner] --replot-only: loaded cache in {time.time() - t0:.1f}s  "
              f"(hosts: {len(data.get('hosts', {}))}, done={data.get('done')})")
    else:
        if args.invalidate and cache_path.is_file():
            print(f"[runner] --invalidate: removing existing cache")
            cache_path.unlink()

        t0 = time.time()
        data = sweep.data_retrieval(**sweep_kwargs)
        print(f"[runner] sweep retrieved in {time.time() - t0:.1f}s  "
              f"(hosts: {len(data.get('hosts', {}))}, done={data.get('done')})")

    sweep._write_tables(data, **sweep_kwargs)

    # Render the sweep overview figure (per-host % events kept / % nodes kept).
    overview = sweep.make_plot(data, **sweep_kwargs)
    sweep._save_figure(overview, None, **sweep_kwargs)
    plt.close(overview)

    if args.skip_per_host_figures:
        print("[runner] --skip-per-host-figures: not rendering top-UUID PNGs")
    else:
        _render_per_host(
            data,
            sweep=sweep,
            dataset=args.dataset, sub_dataset=args.sub_dataset,
            lookup=lookup,
            top_k=args.top_k,
            sweep_kwargs=sweep_kwargs,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

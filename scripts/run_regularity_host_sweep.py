"""
CLI for RegularityHostSweepPlot (dataset, sub_dataset, window)-combination

Example:
    python scripts/run_regularity_host_sweep.py \
        --dataset e3 --sub-dataset cadets \
        --start '2018-04-05 00:00:00' --end '2018-04-06 00:00:00' \
        --persistence 2 --activity-floor 5 \
        --bin-width-s 360 --max-nodes-fallback 10000
"""
from __future__ import annotations

import argparse
import sys

from provenance_explorer.utils.time_conversion import date_string_to_ns_timestamp
from provenance_explorer.plotting import apply_style
from provenance_explorer.analysis.activity_realism.activity_regularity.graph_filters import (
    PersistenceFilter, ActivityFloorFilter, TopKFilter,
)
from provenance_explorer.analysis.activity_realism.activity_regularity.regularity_host_sweep_plot import (
    RegularityHostSweepPlot,
)


def build_filters(args) -> list:
    filters = []
    if args.persistence is not None:
        filters.append(PersistenceFilter(min_bins=args.persistence))
    if args.activity_floor is not None:
        filters.append(ActivityFloorFilter(min_events=args.activity_floor))
    if args.topk is not None:
        filters.append(TopKFilter(max_nodes=args.topk))
    return filters


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run regularity host sweep.")
    p.add_argument("--dataset", required=True)
    p.add_argument("--sub-dataset", required=True)
    p.add_argument("--start", required=True, help='e.g. "2018-04-05 00:00:00"')
    p.add_argument("--end", required=True)

    p.add_argument("--bin-width-s", type=int, default=60)
    p.add_argument("--persistence", type=int, default=2)
    p.add_argument("--activity-floor", type=int, default=5)
    p.add_argument("--lifespan-frac", type=float, default=None)
    p.add_argument("--topk", type=int, default=None,
                   help="optional explicit TopK node cap (not the fallback)")
    p.add_argument("--max-nodes-fallback", type=int, default=10_000,
                   help="hard cap appended if user filters leave more nodes")

    p.add_argument("--r-min", type=int, default=1)
    p.add_argument("--r-max", type=int, default=20)
    p.add_argument("--n-inits", type=int, default=4)
    p.add_argument("--max-iter", type=int, default=100)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--cc-threshold", type=float, default=50.0)
    p.add_argument("--coarsening", type=int, default=5)

    p.add_argument("--invalidate", action="store_true",
                   help="delete cache before running (forces full recomputation)")
    p.add_argument("--no-per-host-figures", action="store_true",
                   help="skip rendering the per-host component figures")

    args = p.parse_args(argv)

    apply_style()

    start_ns = date_string_to_ns_timestamp(args.start)
    end_ns = date_string_to_ns_timestamp(args.end)

    kwargs = dict(
        dataset=args.dataset,
        sub_dataset=args.sub_dataset,
        start_ns=start_ns,
        end_ns=end_ns,
        filters=build_filters(args),
        bin_width_ns=args.bin_width_s * 1_000_000_000,
        r_range=list(range(args.r_min, args.r_max + 1)),
        n_inits=args.n_inits,
        max_iter=args.max_iter,
        tol=args.tol,
        cc_threshold=args.cc_threshold,
        concentration_coarsening=args.coarsening,
        max_nodes_fallback=args.max_nodes_fallback,
    )

    plot = RegularityHostSweepPlot()
    if args.invalidate:
        plot.invalidate(**kwargs)

    plot.run(render_per_host=not args.no_per_host_figures, **kwargs)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

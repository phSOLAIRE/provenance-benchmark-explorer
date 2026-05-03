"""
Build the per-attack-window coverage table

Writes:
    $WORK/threat_coverage/attack_windows.parquet
    $WORK/threat_coverage/attack_windows.csv
"""
from __future__ import annotations

import argparse
import logging

from provenance_explorer.analysis.threat_coverage.attack_window_table import (
    ALL_SOURCES,
    build_attack_window_table,
)
from provenance_explorer.registry.registry_all import WORK


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["e3", "e5", "optc"],)
    parser.add_argument("--sub", default=None,)
    parser.add_argument("--sources", nargs="+", choices=list(ALL_SOURCES), default=list(ALL_SOURCES),)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    df, excl_df = build_attack_window_table(
        sources=tuple(args.sources),
        only_dataset=args.only,
        only_subdataset=args.sub,
    )

    out_dir = WORK / "threat_coverage"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "attack_windows.csv"
    df.to_csv(csv_path, index=False)

    excl_csv = out_dir / "attack_window_exclusions.csv"
    excl_df.to_csv(excl_csv, index=False)

    logging.info("  -> %s", csv_path)
    logging.info("  -> %s", excl_csv)

if __name__ == "__main__":
    main()

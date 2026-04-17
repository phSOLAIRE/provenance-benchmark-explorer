#!/usr/bin/env python3
"""
Build Neo4j graph instances for attack-relevant time slices.

Slices are auto-derived from provenance_explorer.registry.attack_data:

    - each per-subdataset attack window (timestamps recorded in EDT / America/New_York ==> UTC -4
    - the timezone of the DARPA ground-truth reports) is converted to UTC, padded by BUFFER_MIN minutes, and overlapping intervals are merged into one slice
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Tuple
from zoneinfo import ZoneInfo 

from provenance_explorer.neo4j_graph import GraphBuilder, Neo4jInstanceManager
from provenance_explorer.neo4j_graph.instance_manager import instance_dir_name
from provenance_explorer.registry.attack_data import ATTACK_DATA
from provenance_explorer.utils.time_conversion import date_string_to_ns_timestamp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("build_attack_graphs")

EDT = ZoneInfo("America/New_York") # UTC-4 across all benchmark windows 
UTC = timezone.utc
BUFFER_MIN = 30

@dataclass
class AttackSlice:
    dataset: str
    sub_dataset: str
    t_start: str  # UTC datetime string "YYYY-MM-DD HH:MM:SS"
    t_end: str    # UTC datetime string
    description: str

    def instance_name(self) -> str:
        return instance_dir_name(
            self.dataset,
            self.sub_dataset,
            date_string_to_ns_timestamp(self.t_start),
            date_string_to_ns_timestamp(self.t_end),
        )

def _parse_edt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=EDT)

def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

def _merge_intervals(
    intervals: List[Tuple[datetime, datetime, str]],
) -> List[Tuple[datetime, datetime, List[str]]]:
    """
    Sort + merge overlapping/touching (start, end, descrpt) intervals.
    """
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged: List[Tuple[datetime, datetime, List[str]]] = []
    cur_s, cur_e, cur_d = intervals[0][0], intervals[0][1], [intervals[0][2]]
    for s, e, d in intervals[1:]:
        if s <= cur_e:  # overlap or touch
            cur_e = max(cur_e, e)
            cur_d.append(d)
        else:
            merged.append((cur_s, cur_e, cur_d))
            cur_s, cur_e, cur_d = s, e, [d]
    merged.append((cur_s, cur_e, cur_d))
    return merged


def derive_slices(buffer_min: int = BUFFER_MIN) -> List[AttackSlice]:
    """Walk ATTACK_DATA, emit one AttackSlice per merged-padded UTC interval."""
    pad = timedelta(minutes=buffer_min)
    slices: List[AttackSlice] = []

    for (dataset, subdataset), entry in ATTACK_DATA.items():
        windows = entry["windows"]
        if not windows:
            continue

        intervals = []
        for (start_edt_str, end_edt_str), win_entry in windows.items():
            start_utc = _parse_edt(start_edt_str).astimezone(UTC) - pad
            end_utc   = _parse_edt(end_edt_str).astimezone(UTC) + pad
            intervals.append((start_utc, end_utc, win_entry.get("descrpt", "")))

        for s, e, descs in _merge_intervals(intervals):
            slices.append(AttackSlice(
                dataset=dataset,
                sub_dataset=subdataset,
                t_start=_fmt_utc(s),
                t_end=_fmt_utc(e),
                description=" | ".join(descs),
            ))

    return slices


def filter_slices(
    slices: List[AttackSlice],
    only: str | None,
) -> List[AttackSlice]:
    if only is None:
        return slices
    return [s for s in slices if s.dataset == only]


def report_new_vs_existing(
    slices: List[AttackSlice],
    manager: Neo4jInstanceManager,
) -> List[AttackSlice]:
    """return only the new slices; log everything"""
    existing = {p.name for p in manager.instances_root.glob("*") if p.is_dir()}

    logger.info("=" * 80)
    logger.info("new and existing instances under:", len(slices))
    logger.info("  %s", manager.instances_root)
    logger.info("=" * 80)

    new_slices: List[AttackSlice] = []
    for s in slices:
        name = s.instance_name()
        tag = "EXISTS" if name in existing else "NEW   "
        logger.info("[%s] %-12s %-18s %s -> %s",
                    tag, s.dataset, s.sub_dataset, s.t_start, s.t_end)
        if tag.strip() == "NEW":
            new_slices.append(s)

    logger.info("=" * 80)
    logger.info("%d new, %d already present.", len(new_slices), len(slices) - len(new_slices))
    return new_slices


def build(slices: Iterable[AttackSlice]) -> None:
    """Build graph instances sequentially."""
    slices = list(slices)
    for i, s in enumerate(slices, 1):
        t_start_ns = date_string_to_ns_timestamp(s.t_start)
        t_end_ns = date_string_to_ns_timestamp(s.t_end)
        name = instance_dir_name(s.dataset, s.sub_dataset, t_start_ns, t_end_ns)

        logger.info("="*60)
        logger.info("[%d/%d] %s", i, len(slices), name)
        logger.info("  %s", s.description)
        logger.info("  %s -> %s UTC", s.t_start, s.t_end)
        logger.info("="*60)

        builder = None
        try:
            builder = GraphBuilder(
                dataset=s.dataset,
                sub_dataset=s.sub_dataset,
                t_start_ns=t_start_ns,
                t_end_ns=t_end_ns,
            )
            builder.build()
        except Exception:
            logger.exception("FAILED building %s -- continuing to next slice.", name)
        finally:
            if builder is not None:
                try:
                    builder.teardown()
                except Exception:
                    logger.warning("Could not stop Neo4j cleanly, continuing anyway.")
        logger.info("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only", choices=["e3", "optc", "e5"],
        help="Restrict to one benchmark dataset.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only print the derived slices and exit (no Neo4j action).",
    )
    parser.add_argument(
        "--build-existing", action="store_true",
        help="Also (re)build slices whose instance directory already exists.",
    )
    args = parser.parse_args()

    slices = filter_slices(derive_slices(), args.only)
    manager = Neo4jInstanceManager()

    todo = report_new_vs_existing(slices, manager)
    if args.build_existing:
        todo = slices

    if args.dry_run:
        return

    if not todo:
        logger.info("Nothing to build.")
        return

    build(todo)


if __name__ == "__main__":
    main()

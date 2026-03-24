#!/usr/bin/env python3
"""
Build Neo4j graph instances for attack-relevant time slices.
Derived from the ground truth reports; timezone of reports is assumed to be US Eastern.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import List

from provenance_explorer.neo4j_graph import GraphBuilder, Neo4jInstanceManager
from provenance_explorer.neo4j_graph.instance_manager import instance_dir_name
from provenance_explorer.utils.time_conversion import date_string_to_ns_timestamp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("build_attack_graphs")

# Attack time slices
# Each slice is (dataset, sub_dataset, start_utc_string, end_utc_string, description)
# Attacj times from the groundtruth reports (likely UTC-4) are converted to UTC & buffered.
#
# E3 ran 2018-04-05 to 2018-04-13, EDT (UTC-4)
# E5 ran 2019-05-08 to 2019-05-17, EDT (UTC-4)
# OpTC ran 2019-09-23 to 2019-09-25, EDT (UTC-4)
@dataclass
class AttackSlice:
    dataset: str
    sub_dataset: str
    t_start: str # UTC datetime string "YYYY-MM-DD HH:MM:SS"
    t_end: str # UTC datetime string
    description: str

# E3 ATTACK SLICES
E3_SLICES = [
    AttackSlice(
        "e3", "cadets", "2018-04-06 00:00:00", "2018-04-14 00:00:00",
        "All CADETS attacks."
    ),
    AttackSlice(
        "e3", "clearscope", "2018-04-06 00:00:00", "2018-04-14 00:00:00",
        "All ClearScope attacks."
    ),
    AttackSlice(
        "e3", "theia","2018-04-10 00:00:00", "2018-04-14 00:00:00",
        "All THEIA attacks."
    ),
    AttackSlice(
        "e3", "trace", "2018-04-10 06:00:00", "2018-04-10 18:00:00",
        "Firefox-> in memory Drakon -> Elevation -> Persistence -> Crednetials"
    ),
    AttackSlice(
        "e3", "trace", "2018-04-12 10:00:00", "2018-04-13 18:00:00",
        "Firefox I, Firefox II -> Drakon, ->micro APT -> Portscan; phishing, Pine->micro APT"
    ),
    AttackSlice(
        "e3", "fivedirections","2018-04-09 00:00:00", "2018-04-14 00:00:00",
        "All FiveDirections attacks."
    ),
]

# OpTC ATTACK SLICES
OPTC_SLICES = [
    AttackSlice(
        "optc", "aia_51_75", "2019-09-24 00:12:00", "2019-09-25 23:59:00",
        "OpTC Day 3 supply chain on 51 mainly; Syclient0069 over night WMI Agent"
    ),

    AttackSlice(
        "optc", "aia_201_225", "2019-09-23 00:00:00", "2019-09-23 23:59:00",
        "OpTC Day 1: Day 1 primary entry point.."
    ),

    AttackSlice(
        "optc", "aia_501_525","2019-09-23 12:00:00", "2019-09-24 23:59:00",
        "OpTC Day 2; 501 primary target. Custom PS Empire"
    ),

    AttackSlice(
        "optc", "aia_951_975", "2019-09-23 00:00:00", "2019-09-24 00:00:00",
        "Reference Period; small WMI deployment + kill"
    ),
]

# E5 ATTACK SLICES
E5_SLICES = [
    AttackSlice(
        "e5", "cadets","2019-05-16 00:00:00", "2019-05-18 00:00:00",
        "E5 CADETS: Nginx Drakon APT (2 days)"
    ),

    AttackSlice(
        "e5", "clearscope","2019-05-13 00:00:00", "2019-05-18 00:00:00",
        "E5 ClearScope: Metasploit APK, Micro APT, Lockwatch, Tester"
    ),
    AttackSlice(
        "e5", "fivedirections","2019-05-09 07:00:00", "2019-05-09 19:00:00",
        "E5 FiveDirections: Firefox Drakon"
    ),
    AttackSlice(
        "e5", "fivedirections","2019-05-15 09:00:00", "2019-05-16 21:00:00",
        "E5 FiveDirections: BITS Micro"
    ),
    AttackSlice(
        "e5", "fivedirections","2019-05-17 00:00:00", "2019-05-17 23:59:00",
        "E5 FiveDirections: Firefox Drakon, BITS Micro, FileFilter-Elevate"
    ),
    AttackSlice(
        "e5", "marple","2019-05-09 07:00:00", "2019-05-09 19:00:00",
        "E5 Marple: Firefox Drakon APT intial access only"
    ),
    AttackSlice(
        "e5", "theia","2019-05-14 10:00:00", "2019-05-15 22:00:00",
        "E5 THEIA: Firefox Drakon APT, BinFmt-Elevate Inject"
    ),
    AttackSlice(
        "e5", "trace","2019-05-14 07:00:00", "2019-05-14 19:00:00",
        "E5 TRACE: Firefox Drakon"
    ),
    AttackSlice(
        "e5", "trace","2019-05-17 05:00:00", "2019-05-17 17:00:00",
        "E5 TRACE: Azazel rootkit"
    ),
]


ALL_SLICES: List[AttackSlice] = E3_SLICES + E5_SLICES + OPTC_SLICES

def build(slices: List[AttackSlice], skip_existing: bool = True) -> None:
    """build graph instances sequentially."""
    manager = Neo4jInstanceManager()

    for i, s in enumerate(slices, 1):
        t_start_ns = date_string_to_ns_timestamp(s.t_start)
        t_end_ns = date_string_to_ns_timestamp(s.t_end)
        name = instance_dir_name(s.dataset, s.sub_dataset, t_start_ns, t_end_ns)

        logger.info("="*60)
        logger.info("[%d/%d] %s", i, len(slices), name)
        logger.info("  %s", s.description)
        logger.info("  %s → %s", s.t_start, s.t_end)
        logger.info("="*60)

        # Check if instance already exists and has data
        inst_path = manager.instances_root / name
        if skip_existing and inst_path.exists() and (inst_path / "data" / "databases").exists():
            logger.info("  SKIP — instance already exists with data: %s", inst_path)
            continue

        try:
            builder = GraphBuilder(
                dataset=s.dataset,
                sub_dataset=s.sub_dataset,
                t_start_ns=t_start_ns,
                t_end_ns=t_end_ns,
            )
            builder.build()

        except Exception:
            logger.exception("FAILED building %s — continuing to next slice.", name)

        finally:
            # stop Neo4j before moving to the next slice
            try:
                manager.stop()
            except Exception:
                logger.warning("Could not stop Neo4j cleanly, continuing anyway.")

        logger.info("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-skip", action="store_true",
    )
    parser.add_argument(
        "--only", choices=["e3", "optc", "e5"],
    )
    args = parser.parse_args()

    if args.only == "e3":
        slices = E3_SLICES
    elif args.only == "optc":
        slices = OPTC_SLICES
    elif args.only == "e5":
        slices = E5_SLICES
    else:
        slices = ALL_SLICES


    build(slices, skip_existing=not args.no_skip)


if __name__ == "__main__":
    main()
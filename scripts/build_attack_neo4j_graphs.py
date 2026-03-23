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
# E3 attacks span 2018-04-06 through 2018-04-13 local time at Raytheon BBN.
E3_SLICES = [
    # CADETS attacks:
    #   04/06 11:00 - Nginx backdoor (kernel panic)
    #   04/06 15:00 - Email server (common threat phishing relay)
    #   04/11 15:00 - Nginx backdoor retry (kernel panic again)
    #   04/12 14:00 - Nginx backdoor + micro APT portscans
    #   04/13 09:00 - Nginx backdoor + final injection attempts
    #   with buffer: 2018-04-06 00:00 to 2018-04-14 00:00 UTC (!, to match common representation)
    AttackSlice(
        "e3", "cadets", "2018-04-06 00:00:00", "2018-04-14 00:00:00",
        "All CADETS attacks: Nginx backdoor (4x), email relay, micro APT scans"
    ),

    # CLEARSCOPE attacks:
    #   04/06 15:00 - Phishing email link (common threat, ClearScope = Android)
    #   04/11 14:00 - Firefox backdoor + drakon on Android
    #   04/12       - Continued Firefox backdoor (connection from previous day)
    #   04/13       - Metasploit APK (failed)
    #   with buffer: 2018-04-06 00:00 to 2018-04-14 00:00 UTC
    AttackSlice(
        "e3", "clearscope", "2018-04-06 00:00:00", "2018-04-14 00:00:00",
        "All ClearScope attacks: phishing, Firefox on Android, Metasploit APK"
    ),

    # THEIA attacks:
    #   04/10 14:00 - Firefox backdoor + drakon in-memory
    #   04/10 13:00 - Phishing email link (common threat)
    #   04/12 12:00 - Browser extension + drakon dropper + micro APT portscans
    #   04/13 14:00 - Phishing email executable (failed)
    #   with buffer: 2018-04-10 00:00 to 2018-04-14 00:00 UTC 1
    AttackSlice(
        "e3", "theia","2018-04-10 00:00:00", "2018-04-14 00:00:00",
        "All THEIA attacks: Firefox backdoor, phishing, browser ext + micro APT"
    ),

    # TRACE attacks:
    #   04/10 10:00 - Firefox backdoor + drakon in-memory
    #   04/10 12:00 - Phishing email link (common threat)
    #   04/12 13:00 - Browser extension (failed, Firefox hung)
    #   04/13 12:00 - Pine backdoor + micro APT
    #   04/13 14:00 - Phishing email executable
    #   with buffer: 2018-04-10 00:00 to 2018-04-14 00:00 UTC (!)
    AttackSlice(
        "e3", "trace", "2018-04-10 00:00:00", "2018-04-14 00:00:00",
        "All TRACE attacks: Firefox backdoor, phishing, pine backdoor, micro APT"
    ),

    # FIVEDIRECTIONS attacks:
    #   04/09 15:00 - Phishing email Excel macro (common threat)
    #   04/11 10:00 - Firefox backdoor + drakon + file exfil
    #   04/12 11:00 - Browser extension (failed)
    #   04/13 15:00 - Phishing email executable (skipped)
    #   with buffer: 2018-04-09 00:00 to 2018-04-14 00:00 UTC !
    AttackSlice(
        "e3", "fivedirections","2018-04-09 00:00:00", "2018-04-14 00:00:00",
        "All FiveDirections attacks: phishing Excel, Firefox backdoor, browser ext"
    ),
]


# ============================================================================
# OpTC ATTACK SLICES
# ============================================================================
# OpTC attacks span 2019-09-23 through 2019-09-25.
# Machines are grouped into AIA ranges: 51-75, 201-225, 501-525, 951-975.
#
# Day 1 (09/23): Plain PowerShell Empire
#   Sysclient0201 (AIA-201-225): initial access, mimikatz, UAC bypass, persistence
#   Affected AIA ranges: primarily 201-225 (0201,0205), 51-75 (0069), 501-525, 951-975
#
# Day 2 (09/24): Custom PowerShell Empire
#   Sysclient0501 (AIA-501-525): phishing, DeathStar, RDP tunneling, exfil
#   Sysclient0974 (AIA-951-975): RDP pivot
#
# Day 3 (09/25): Malicious Upgrade (Notepad++)
#   Sysclient0051 (AIA-51-75): meterpreter, mimikatz, persistence, RDP
#
# One slice per AIA range covering all 3 days.
# with uffer: 2019-09-23 00:00 to 2019-09-26 00:00 UTC
OPTC_SLICES = [
    AttackSlice(
        "optc", "aia_51_75", "2019-09-23 00:00:00", "2019-09-26 00:00:00",
        "OpTC all days: Sysclient0051 (Day3 meterpreter), potential DC1 spread targets"
    ),

    AttackSlice(
        "optc", "aia_201_225", "2019-09-23 00:00:00", "2019-09-26 00:00:00",
        "OpTC all days: Sysclient0201 (Day1 initial access), DC1 spread targets"
    ),

    AttackSlice(
        "optc", "aia_501_525","2019-09-23 00:00:00", "2019-09-26 00:00:00",
        "OpTC all days: Sysclient0501 (Day2 phishing+exfil), DC1 pivot"
    ),

    AttackSlice(
        "optc", "aia_951_975", "2019-09-23 00:00:00", "2019-09-26 00:00:00",
        "OpTC all days: Sysclient0955/0974 (Day1 spread, Day2 RDP pivot)"
    ),
]


# E5 ATTACK SLICES
# E5 attacks span 2019-05-08 to 2019-05-17
#
# CADETS attacks:
#   05/16 09:32 - Nginx Drakon APT
#   05/17 10:16 - Nginx Drakon APT
#   with buffer: 2019-05-16 00:00 to 2019-05-18 00:00 UTC
#
# CLEARSCOPE attacks:
#   05/13 10:26 - Metasploit APK
#   05/14 16:09 - BarePhone Micro APT (Failed)
#   05/15 10:22 - Screencap APK (Failed), 14:14 Barephone (Failed)
#   05/15 15:39 - Appstarter APK Micro APT Elevate
#   05/17 11:50 - Firefox Drakon APT
#   05/17 14:27 - MyApp/AppStarter (Failed)
#   05/17 15:43 - Lockwatch APK Java APT
#   05/17 16:20 - Tester Micro APT BinFmt-Elevate
#   with buffer: 2019-05-13 00:00 to 2019-05-18 00:00 UTC
#
# FIVEDIRECTIONS attacks:
#   05/09 13:26 - Firefox Drakon APT Elevate Copykatz Sysinfo
#   05/15 13:15 - Firefox BITS Micro APT
#   05/17 12:26 - Firefox DNS Drakon APT FileFilter-Elevate
#   05/17 16:11 - Verifier Drakon APT (Cont)
#   with buffer: 2019-05-09 00:00 to 2019-05-18 00:00 UTC
#
# MARPLE attacks:
#   05/09 13:57 - Firefox Drakon APT
#   05/17 13:01 - Firefox DNS Drakon APT
#   with buffer: 2019-05-09 00:00 to 2019-05-18 00:00 UTC
#
# THEIA attacks:
#   05/14 11:45 - Firefox Drakon APT (Failed)
#   05/14 20:32 - BinFmt-Elevate Setup (benign prep)
#   05/15 14:48 - Firefox Drakon APT BinFmt-Elevate Inject
#   with buffer: 2019-05-14 00:00 to 2019-05-16 00:00 UTC
#
# TRACE attacks:
#   05/14 10:08 - Firefox Drakon APT Elevate Inject
#   05/17 09:05 - Azazel APT (Failed)
#   with buffer: 2019-05-14 00:00 to 2019-05-18 00:00 UTC
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
        "e5", "fivedirections","2019-05-09 00:00:00", "2019-05-18 00:00:00",
        "E5 FiveDirections: Firefox Drakon, BITS Micro, FileFilter-Elevate"
    ),

    AttackSlice(
        "e5", "marple","2019-05-09 00:00:00", "2019-05-18 00:00:00",
        "E5 Marple: Firefox Drakon APT (2 attack days)"
    ),
    AttackSlice(
        "e5", "theia","2019-05-14 00:00:00", "2019-05-16 00:00:00",
        "E5 THEIA: Firefox Drakon APT, BinFmt-Elevate Inject"
    ),
    AttackSlice(
        "e5", "trace","2019-05-14 00:00:00", "2019-05-18 00:00:00",
        "E5 TRACE: Firefox Drakon Elevate Inject, Azazel APT"
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
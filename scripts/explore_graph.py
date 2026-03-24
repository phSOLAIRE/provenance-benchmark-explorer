#!/usr/bin/env python3
"""
command line instance manager for toggling neo4j on GWDG jupyterhub remote desktop.

Lists available graph instances, lets you pick one, starts Neo4j,
optionally loads attack labels, and keeps it running until you
press Enter (or Ctrl+C) to shut down.

Usage:
    python explore_graph.py
"""
from __future__ import annotations

import signal
import sys
from pathlib import Path

from provenance_explorer.neo4j_graph import Neo4jInstanceManager, GraphAnnotator
from provenance_explorer.neo4j_graph.instance_manager import instance_dir_name
from provenance_explorer.neo4j_graph.annotator import PM, FL, WW, RV
from provenance_explorer.registry.registry_all import DATA_NE04J, DARPA_LABEL_PATH
from provenance_explorer.registry.attack_registry import ALL_REGISTRIES

SOURCE_NAMES = {PM: "PIDSMaker/Orthrus", FL: "Flash/ThreatTrace", WW: "WWTAWWTAL", RV: "Revisiting OpTC"}

def check_and_stop_running(manager: Neo4jInstanceManager) -> None:
    """Check if a Neo4j process is already listening on the bolt port and offer to stop it."""
    import socket
    try:
        with socket.create_connection((manager.bolt_host, manager.bolt_port), timeout=2.0):
            pass
    except (ConnectionRefusedError, socket.timeout, OSError):
        return

    print(f"\n\tNeo4j is already running on bolt://{manager.bolt_host}:{manager.bolt_port}.")
    choice = input(f"\tStop the running instance? [y/n]:").strip().lower()
    if choice in ("y", "yes"):
        print(f"\tStopping...")
        manager.stop()
        print(f"\tStopped.\n")
    else:
        print(f"\tAbort.")
        exit()

def select_instance(manager: Neo4jInstanceManager) -> "Path":
    """List available instances and let user pick."""
    instances = manager.list_instances()

    if not instances:
        print(f"\nNo instances found under:")
        print(f"{manager.instances_root}\n")
        exit()

    print(f"\n  Available graph instances ({len(instances)}):\n")
    for i, inst in enumerate(instances, 1):
        print(f"    [{i:2d}]  {inst.name}")

    print()
    while True:
        raw = input(f"\tSelect instance [1-{len(instances)}]: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(instances):
                return instances[idx - 1].path
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(instances)}.")

def _resolve_registry_key(instance_name: str) -> tuple[str,str] | None:
    """
    Try to match an instance directory name to a registry key.
    """
    # Strip the timestamp suffix
    parts = instance_name.split("__")
    if len(parts) >= 1:
        prefix = parts[0]  # e.g. "e3_cadets"
        parts = prefix.split("_")
        dataset_id = (parts[0], parts[1])
        if dataset_id in ALL_REGISTRIES:
            return dataset_id
    return None


def _find_available_sources(registry_entry: dict) -> dict[str, int]:
    """Count how many label files exist per source for this registry entry."""
    sources: dict[str, int] = {}
    for step in registry_entry["attacks"]:
        for source, file_list in step["label_files"].items():
            sources.setdefault(source, 0)
            sources[source] += len(file_list)
    return sources

def prompt_annotation(manager: Neo4jInstanceManager, instance_path: Path) -> None:
    registry_key = _resolve_registry_key(instance_path.name)
    if registry_key is None:
        print(f"\tNo attack registry entry found for this instance. Skipping annotation.\n")
        return

    registry_entry = ALL_REGISTRIES[registry_key]
    available = _find_available_sources(registry_entry)

    if not available:
        print(f"\tNo label files referenced in the attack registry for this instance.\n")
        return

    print(f"\n\tAttack registry: {registry_key}")
    print(f"\t{len(registry_entry['attacks'])} attack steps documented.\n")

    choice = input("  Load attack labels into the graph? [Y/n]: ").strip().lower()
    if choice not in ("y", "yes"):
        return

    # Check if labels are already present
    driver = manager.get_driver()
    try:
        with driver.session(database="neo4j") as session:
            result = session.run("MATCH (n {malicious: true}) RETURN count(n) AS c")
            existing = result.single()["c"] # type: ignore
    except Exception:
        existing = 0

    if existing > 0:
        print(f"\n  Graph already has {existing} annotated nodes.")
        rechoice = input("  Clear existing annotations first? [Y/n]: ").strip().lower()
        if rechoice in ("y", "yes"):
            annotator = GraphAnnotator(driver)
            annotator.clear_annotations()
            print(f"\tCleared.\n")

    # Show available sources
    source_list = sorted(available.keys())
    print(f"\nAvailable label sources:\n")
    for i, src in enumerate(source_list, 1):
        name = SOURCE_NAMES.get(src, src)
        count = available[src]
        print(f"\t[{i}]  {name:25s}  ({count} file references)")

    print()
    raw = input(f"  Select sources [1-{len(source_list)} comma-separated / all]: ").strip().lower()
    if raw == "all" or raw == "":
        selected_sources = source_list
    else:
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            selected_sources = [source_list[i - 1] for i in indices if 1 <= i <= len(source_list)]
        except (ValueError, IndexError):
            print("Invalid selection, loading all.")
            selected_sources = source_list
    print(f"\tAnnotating with: {', '.join(selected_sources)}\n")
    print(f"\tPlease hold the line...")

    annotator = GraphAnnotator(driver)
    annotator.annotate_from_registry(
        registry_entry=registry_entry,
        sources=selected_sources,
    )

    print(f"\n  {annotator.summary()}\n")

    driver.close()

def run(manager: Neo4jInstanceManager, instance_path: Path) -> None:
    """start Neo4j, optionally annotate, wait for user, then stop."""
    print(f"\n  Starting Neo4j for: {instance_path.name}")
    print("  This may take a moment...\n")

    manager.start(instance_path)

    print(f"Neo4j Browser:  http://{manager.bolt_host}:{manager.http_port}")
    print(f"Bolt URI:       bolt://{manager.bolt_host}:{manager.bolt_port}")
    print(f"Auth:           neo4j / {manager.password}")

    # Offer annotation
    prompt_annotation(manager, instance_path)

    def _shutdown(sig, frame):
        print(f"\n\nCaught interrupt, shutting down Neo4j...")
        manager.stop()
        print("Done.")
        exit()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        input(f"\tPress Enter to stop Neo4j and exit.\n")
    except EOFError:
        pass

    print(f"\tStopping Neo4j...")
    manager.stop()
    print("Done.\n")

def main():
    manager = Neo4jInstanceManager()

    check_and_stop_running(manager)
    instance_path = select_instance(manager)
    run(manager, instance_path)


if __name__ == "__main__":
    main()
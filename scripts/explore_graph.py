#!/usr/bin/env python3
"""
command line instance manager for toggling neo4j on GWDG jupyterhub remote desktop.

Lists available graph instances & starts up selected one;
keeps it running until user presses Enter SIGKILL to shut down.

Run as:
    python explore_graph.py
"""

from __future__ import annotations

import signal
import sys

from provenance_explorer.neo4j_graph import Neo4jInstanceManager
from pathlib import Path

def check_and_stop_running(manager: Neo4jInstanceManager) -> None:
    """check if Neo4j is already listening on bolt port."""
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

    print(f"\n\tAvailable graph instances ({len(instances)}):\n")
    for i, inst in enumerate(instances, 1):
        print(f"\t[{i:2d}]: \t{inst.name}")

    print()
    while True:
        raw = input(f"\tSelect instance [1-{len(instances)}]: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(instances):
                return instances[idx - 1].path
        except ValueError:
            pass
        print(f"\tEnter instance number.")

def run(manager: Neo4jInstanceManager, instance_path: "Path") -> None:
    """Start Neo4j, wait for user to finish exploring, then stop."""
    print(f"\n  Starting Neo4j for: {instance_path.name}")
    print("  This may take a moment...\n")

    manager.start(instance_path)

    print(f"---- Success: -----")
    print(f"\tNeo4j Browser: http://{manager.bolt_host}:{manager.http_port} ")
    print(f"\tBolt URI: bolt://{manager.bolt_host}:{manager.bolt_port}")
    print(f"\tAuth: neo4j / {manager.password} ")
    print("Press Enter or Ctrl+C to stop Neo4j and exit.")

    # register signal handler
    def _shutdown(sig, frame):
        print(f"\nshutting down Neo4j...")
        manager.stop()
        print(f"Done.")
        exit()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        input(f"\n(press Enter to stop)\n")
    except EOFError:
        pass

    print("Stopping Neo4j...")
    manager.stop()
    print("Done.\n")

if __name__ == "__main__":
    manager = Neo4jInstanceManager()
    check_and_stop_running(manager)
    instance_path = select_instance(manager)
    run(manager, instance_path)
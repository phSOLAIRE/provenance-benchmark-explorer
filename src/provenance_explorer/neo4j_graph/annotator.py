"""
Graph annotator:
applies attack labels to an existing Neo4j provenance graph.

Annotations set on nodes:
  malicious: true
  attack_sources: ["pidsmaker", "flash", ...]   (list, accumulated)

Annotations set on edges (WWTAWWTAL edges, Revisiting OpTC):
  malicious: true
  attack_sources: ["wwtawwtal", ...]
"""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from neo4j import Driver

from provenance_explorer.registry.registry_all import DARPA_LABEL_PATH

logger = logging.getLogger(__name__)

# source identifiers
PM = "pidsmaker"
FL = "flash"
WW = "wwtawwtal"
RV = "revisiting_optc"

# Label loaders
def load_pidsmaker(path: Path) -> Tuple[Set[str], Set[str]]:
    """node uuids only"""
    node_uuids: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # UUID is everything before the first comma
            uuid = line.split(",", 1)[0].strip()
            if uuid:
                node_uuids.add(uuid)
    logger.debug("PIDSMaker %s: %d node UUIDs", path.name, len(node_uuids))
    return node_uuids, set()


def load_flash_json(path: Path) -> Tuple[Set[str], Set[str]]:
    """node uuid strings"""
    node_uuids: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        # Simple list of UUIDs
        for item in data:
            if isinstance(item, str) and item.strip():
                node_uuids.add(item.strip())
    elif isinstance(data, dict):
        # Dict with lists of UUIDs per attack chain
        for key, val in data.items():
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        node_uuids.add(item.strip())

    logger.debug("Flash JSON %s: %d node UUIDs", path.name, len(node_uuids))
    return node_uuids, set()


def load_flash_txt(path: Path) -> Tuple[Set[str], Set[str]]:
    """node uuids"""
    node_uuids: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            uuid = line.strip()
            if uuid:
                node_uuids.add(uuid)
    logger.debug("Flash TXT %s: %d node UUIDs", path.name, len(node_uuids))
    return node_uuids, set()


def load_wwtawwtal_nodes(path: Path) -> Tuple[Set[str], Set[str]]:
    """node uuids"""
    node_uuids: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        for row in reader:
            # Strip keys in case of residual whitespace
            cleaned = {k.strip(): v.strip() for k, v in row.items()}
            uuid = cleaned.get("uuid", "")
            if uuid:
                node_uuids.add(uuid)
    logger.debug("WWTAWWTAL nodes %s: %d node UUIDs", path.name, len(node_uuids))
    return node_uuids, set()


def load_wwtawwtal_edges(path: Path) -> Tuple[Set[str], Set[str]]:
    """edges for e3"""
    node_uuids: Set[str] = set()
    edge_uuids: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        for row in reader:
            cleaned = {k.strip(): v.strip() for k, v in row.items()}
            v_uuid = cleaned.get("vertex_uuid", "")
            e_uuid = cleaned.get("edge_uuid", "")
            if v_uuid:
                node_uuids.add(v_uuid)
            if e_uuid:
                edge_uuids.add(e_uuid)
    logger.debug("WWTAWWTAL edges %s: %d node UUIDs, %d edge UUIDs",
                 path.name, len(node_uuids), len(edge_uuids))
    return node_uuids, edge_uuids


def load_revisiting_optc(path: Path) -> Tuple[Set[str], Set[str]]:
    """edge+node uuids for optc """
    node_uuids: Set[str] = set()
    edge_uuids: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data if isinstance(data, list) else data.values() if isinstance(data, dict) else []
    flat_records = []
    for item in records:
        if isinstance(item, dict):
            flat_records.append(item)
        elif isinstance(item, list):
            flat_records.extend(item)

    for record in flat_records:
        if not isinstance(record, dict):
            continue
        eid = record.get("id", "").strip()
        if eid:
            edge_uuids.add(eid)

        for key in ("actorID", "objectID"):
            nid = record.get(key, "")
            if isinstance(nid, str) and nid.strip():
                node_uuids.add(nid.strip())

    logger.debug("Revisiting OpTC %s: %d node UUIDs, %d edge UUIDs",
                 path.name, len(node_uuids), len(edge_uuids))
    return node_uuids, edge_uuids

def _detect_flash_format(path: Path) -> str:
    """whether a Flash file is json"""
    if path.suffix == ".json":
        return "json"
    return "txt"


def load_label_file(source: str, path: Path) -> Tuple[Set[str], Set[str]]:
    """give appropriate loader based on source key; return labels"""
    if source == PM:
        return load_pidsmaker(path)
    elif source == FL:
        fmt = _detect_flash_format(path)
        if fmt == "json":
            return load_flash_json(path)
        else:
            return load_flash_txt(path)
    elif source == WW:
        if "edge" in path.stem.lower():
            return load_wwtawwtal_edges(path)
        else:
            return load_wwtawwtal_nodes(path)
    elif source == RV:
        return load_revisiting_optc(path)
    else:
        logger.warning("Unknown label source '%s' for %s ;  moving on.", source, path)
        return set(), set()


_CHUNK = 50_000 # size for UNWIND 

def _chunks(xs: list, size: int):
    for i in range(0, len(xs), size):
        yield xs[i:i + size]

class GraphAnnotator:
    """
    add attack labels to nodes and edges in a running Neo4j instance.

    Usage::

        annotator = GraphAnnotator(driver)
        annotator.annotate_from_registry(
            registry_entry=E3_CADETS, # attack registry
            sources=["pidsmaker", "flash", "wwtawwtal"],
        )
        print(annotator.summary())
    """

    def __init__(self, driver: Driver, database: str = "neo4j"):
        self._driver = driver
        self._database = database

        self._node_matches: Dict[str, int] = defaultdict(int)

    # Public API
    def annotate_from_registry(
        self,
        registry_entry: dict,
        sources: Optional[List[str]] = None,
    ) -> None:
        """
        Walk all attack steps in attack registry, 
        load referenced label files, and apply annotations to the graph.
            - if sources'' is given, only process these label sources (e.g. ["pidsmaker"]); 
            otherwise all.
        """
        seen_files: Set[Path] = set()
        file_source_map: Dict[Path, str] = {}

        for step in registry_entry["attacks"]:
            for source, file_list in step["label_files"].items():
                if sources is not None and source not in sources:
                    continue
                for rel_path in file_list:
                    abs_path = DARPA_LABEL_PATH / rel_path
                    seen_files.add(abs_path)
                    file_source_map[abs_path] = source

        for abs_path in seen_files:
            source = file_source_map[abs_path]

            if not abs_path.exists():
                logger.warning("Label file not found: %s", abs_path)
                raise

            node_uuids, edge_uuids = load_label_file(source, abs_path)

            if node_uuids:
                matched = self._annotate_nodes(node_uuids, source)
                self._node_matches[f"{source}/{abs_path.name}"] = matched

            if edge_uuids:
                self._annotate_edges(edge_uuids, source)

    def clear_annotations(self) -> None:
        """Remove all malicious/attack_* properties from nodes and edges."""
        with self._driver.session(database=self._database) as session:
            session.run("""
                MATCH (n:File|Executable|Socket|Host|User|Process)
                WHERE n.malicious IS NOT NULL
                REMOVE n.malicious, n.attack_sources
            """).consume()

            session.run("""
                MATCH ()-[r:writes|isReadBy|sends|isReceivedBy|forks|isExecutedBy {edge_uuid: row.edge_uuid}]->()
                WHERE r.malicious IS NOT NULL
                REMOVE r.malicious
            """).consume()

        logger.info("Cleared all attack annotations.")

    def summary(self) -> str:
        """human readable summary of results."""
        lines = [
            "Node annotations:"
        ]
        total_nodes = 0
        for key, count in sorted(self._node_matches.items()):
            lines.append(f"  {key}: {count} nodes matched")
            total_nodes += count
        lines.append(f"  Total: {total_nodes}")

        return "\n".join(lines)

    # Cypher
    def _annotate_nodes(
        self,
        uuids: Set[str],
        source: str,
    ) -> int:
        """
        Mark nodes with matching uuids as malicious.

        Returns number of nodes matched.
        """
        query = """
            UNWIND $rows AS row
            MATCH (n:File|Executable|Socket|Host|User|Process {uuid: row.uuid})
            SET n.malicious = true,
                n.attack_sources = CASE
                    WHEN n.attack_sources IS NULL THEN [row.source]
                    WHEN NOT row.source IN n.attack_sources
                        THEN n.attack_sources + row.source 
                    ELSE n.attack_sources
                END
        """

        rows = [{"uuid": u, "source": source} for u in uuids]

        with self._driver.session(database=self._database) as session:
            for chunk in _chunks(rows, _CHUNK):
                session.run(query, rows=chunk).consume()

        with self._driver.session(database=self._database) as session:
            result = session.run(
                "MATCH (n {malicious: true}) WHERE n.uuid IN $uuids RETURN count(n) AS c",
                uuids=list(uuids),
            )
            matched = result.single()["c"] # type: ignore

        return matched

    def _annotate_edges(
        self,
        edge_uuids: Set[str],
        source: str,
    ):
        """
        Mark edges with matching edge_uuid as malicious.
        Must scan across all relationship types.
        """
        # uses indexes on edge_uuid per rel type
        query = """
        UNWIND $rows AS row
            MATCH ()-[r:writes|isReadBy|sends|isReceivedBy|forks|isExecutedBy {edge_uuid: row.edge_uuid}]->()
            SET r.malicious = true
        """

        rows = [{"edge_uuid": eu, "source": source} for eu in edge_uuids]

        with self._driver.session(database=self._database) as session:
            for chunk in _chunks(rows, _CHUNK):
                session.run(query, rows=chunk).consume()

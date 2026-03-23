"""
Graph ingestion engine.

Accumulates CommonRecords into batched Cypher jobs and flushes them to Neo4j
at configurable intervals.  Handles:
  - Node MERGE (deduplicated by uuid / ip)
  - Event edge CREATE (deduplicated by edge_uuid, Python-side set)
  - Structural edge MERGE (deduplicated Python-side to avoid redundant MERGEs)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from neo4j import Driver

from provenance_explorer.common_record.schema import CommonRecord, EdgeCategory

from .schema import (
    EDGE_CATEGORY_MAP,
    EdgeMapping,
    EventRelType,
    NodeLabel,
    StructuralRelType,
)
from . import cypher_templates as ct

logger = logging.getLogger(__name__)


# ingestion details
@dataclass
class IngestionStats:
    """Counters:"""
    records_processed: int = 0
    records_skipped_duplicate: int = 0
    nodes_by_label: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    event_edges_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    structural_edges_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    flushes: int = 0
    flush_time_s: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Records processed: {self.records_processed}",
            f"Duplicates skipped: {self.records_skipped_duplicate}",
            f"Flushes: {self.flushes} (total {self.flush_time_s:.1f}s)",
            "Nodes by label:",
        ]
        for lbl, cnt in sorted(self.nodes_by_label.items()):
            lines.append(f"  {lbl:15s} {cnt:>12,}")
        lines.append("Event edges by type:")
        for rel, cnt in sorted(self.event_edges_by_type.items()):
            lines.append(f"  {rel:15s} {cnt:>12,}")
        lines.append("Structural edges by type:")
        for rel, cnt in sorted(self.structural_edges_by_type.items()):
            lines.append(f"  {rel:15s} {cnt:>12,}")
        return "\n".join(lines)


# GraphIngester
class GraphIngester:
    """
    Convert CommonRecords into Cypher batches.

    Use as: 
        ingester = GraphIngester(driver, ) # or set own chunk_size=xxx
        for record in common_record_iterator(...):
            ingester.ingest(record)
            if ingester.pending_count >= 100_000:
                ingester.flush()
        ingester.flush() # final
        print(ingester.stats.summary())
    """

    def __init__(
        self,
        driver: Driver,
        database: str = "neo4j",
        chunk_size: int = 50_000,
    ):
        self._driver = driver
        self._database = database
        self._chunk_size = chunk_size

        # Accumulators  — keyed by label / rel_type string
        self._pending_nodes: Dict[str, List[Dict]] = defaultdict(list)
        self._pending_event_edges: Dict[str, List[Dict]] = defaultdict(list)
        self._pending_structural_edges: Dict[str, List[Dict]] = defaultdict(list)

        # # dedup sets
        # self._seen_edge_uuids: Set[str] = set() # TODO 
        self._seen_structural: Set[Tuple] = set() # (rel_type, src_key, dst_key)

        # Stats
        self.stats = IngestionStats()

    # API
    @property
    def pending_count(self) -> int:
        """Total items waiting to be flushed."""
        n = sum(len(v) for v in self._pending_nodes.values())
        n += sum(len(v) for v in self._pending_event_edges.values())
        n += sum(len(v) for v in self._pending_structural_edges.values())
        return n

    def ingest(self, record: CommonRecord) -> None:
        """
        Process one CommonRecord: accumulate nodes, event edge, and any derived structural edges.
        """
        # # TODO: Confirm there are no duplicate edge uuids in e.g. E5 with heavy overlap
        # # Dedup by edge_uuid
        # if record.edge_uuid in self._seen_edge_uuids:
        #    self.stats.records_skipped_duplicate += 1
        #    return
        # self._seen_edge_uuids.add(record.edge_uuid)
        # self.stats.records_processed += 1

        mapping: EdgeMapping = EDGE_CATEGORY_MAP[record.edge_category]

        # Subject is always a Process
        self._add_process_node(record.subject_uuid, record.pid, record.cmdline)

        # Object node - label depends on the edge category
        self._add_object_node(mapping.object_label, record)

        # Event edge
        if mapping.src_is_subject:
            src_uuid, dst_uuid = record.subject_uuid, record.object_uuid
        else:
            src_uuid, dst_uuid = record.object_uuid, record.subject_uuid

        self._pending_event_edges[mapping.rel_type.value].append({
            "src_uuid": src_uuid,
            "dst_uuid": dst_uuid,
            "edge_uuid": record.edge_uuid,
            "timestamp_ns": record.timestamp_ns,
            "size_bytes": record.size_bytes,
            "raw_event_type": record.raw_event_type,
        })
        self.stats.event_edges_by_type[mapping.rel_type.value] += 1

        # Structural side-effects::
        # hasExe: EXECUTE means subject (Process) has executable (the object)
        if record.edge_category == EdgeCategory.EXECUTE:
            self._add_structural(
                StructuralRelType.HAS_EXE,
                record.subject_uuid,
                record.object_uuid,
            )

        # hasUser: if user_principal is known
        if record.user_principal is not None:
            self._ensure_user_node(record.user_principal)
            self._add_structural(
                StructuralRelType.HAS_USER,
                record.subject_uuid,
                record.user_principal,
            )

        # originatesFrom: if host_id is known
        if record.host_id:
            self._ensure_host_node(record.host_id)
            self._add_structural(
                StructuralRelType.ORIGINATES_FROM,
                record.subject_uuid,
                record.host_id,
            )

        # hasSocketIP: SEND/RECV with non-null IP
        if record.edge_category in (EdgeCategory.SEND, EdgeCategory.RECV):
            if record.object_ip is not None:
                self._ensure_ip_node(record.object_ip)
                self._add_structural_ip(
                    StructuralRelType.HAS_SOCKET_IP,
                    record.object_uuid,
                    record.object_ip,
                )

    def flush(self) -> None:
        """Execute all pending Cypher jobs in a single transaction, then clear buffers."""
        if self.pending_count == 0:
            return

        jobs: List[ct.CypherJob] = []

        # 1. Nodes first (so edges can MATCH them)
        for label_str, rows in self._pending_nodes.items():
            label = NodeLabel(label_str)
            jobs.extend(ct.node_jobs(label, rows, self._chunk_size))

        # 2. Structural edges (MERGEd, safe to run before event edges)
        for rel_str, rows in self._pending_structural_edges.items():
            rel = StructuralRelType(rel_str)
            jobs.extend(ct.structural_edge_jobs(rel, rows, self._chunk_size))

        # 3. Event edges
        for rel_str, rows in self._pending_event_edges.items():
            rel = EventRelType(rel_str)
            mapping = _rel_type_to_labels(rel)
            jobs.extend(ct.event_edge_jobs(rel, mapping[0], mapping[1], rows, self._chunk_size))

        # Execute
        t0 = time.monotonic()
        self._execute_jobs(jobs)
        elapsed = time.monotonic() - t0

        self.stats.flushes += 1
        self.stats.flush_time_s += elapsed

        pending = self.pending_count
        logger.info("Flushed %d items in %.2fs (%d jobs)", pending, elapsed, len(jobs))

        # Clear buffers (but NOT the seen-sets — those persist for the run)
        self._pending_nodes.clear()
        self._pending_event_edges.clear()
        self._pending_structural_edges.clear()

    def flush_metadata_nodes(
        self,
        host_rows: List[Dict],
        user_rows: List[Dict],
        host_ip_rows: List[Dict],
    ) -> None:
        """
        Pre-populate Host, User, IPAddress nodes and hasHostIP edges from ObjectLookup metadata
        """
        jobs: List[ct.CypherJob] = []

        if host_rows:
            jobs.extend(ct.node_jobs(NodeLabel.HOST, host_rows, self._chunk_size))
        if user_rows:
            jobs.extend(ct.node_jobs(NodeLabel.USER, user_rows, self._chunk_size))

        # IPAddress nodes + hasHostIP edges
        if host_ip_rows:
            # Extract unique IPs for node creation
            seen_ips: set = set()
            ip_rows: List[Dict] = []
            for row in host_ip_rows:
                if row["dst_ip"] not in seen_ips:
                    seen_ips.add(row["dst_ip"])
                    ip_rows.append({"ip": row["dst_ip"]})
            if ip_rows:
                jobs.extend(ct.node_jobs(NodeLabel.IP_ADDRESS, ip_rows, self._chunk_size))
            jobs.extend(ct.structural_edge_jobs(StructuralRelType.HAS_HOST_IP, host_ip_rows, self._chunk_size))

        if jobs:
            self._execute_jobs(jobs)
            logger.info(
                "Pre-populated metadata: %d hosts, %d users, %d host-IP links",
                len(host_rows), len(user_rows), len(host_ip_rows),
            )

    # node accumulation helpers; I trust the uuids here
    def _add_process_node(self, uuid: str, pid: Optional[int], cmdline: Optional[str]) -> None:
        self._pending_nodes[NodeLabel.PROCESS.value].append({
            "uuid": uuid,
            "pid": pid,
            "cmdline": cmdline,
        })
        self.stats.nodes_by_label[NodeLabel.PROCESS.value] += 1

    def _add_object_node(self, label: NodeLabel, record: CommonRecord) -> None:
        if label == NodeLabel.PROCESS:
            # FORK target a child process
            self._pending_nodes[NodeLabel.PROCESS.value].append({
                "uuid": record.object_uuid,
                "pid": None, # COALESCED, so this doesnt overwrite
                "cmdline": None,
            })
        elif label == NodeLabel.FILE:
            self._pending_nodes[NodeLabel.FILE.value].append({
                "uuid": record.object_uuid,
                "path": record.object_path,
            })
        elif label == NodeLabel.SOCKET:
            self._pending_nodes[NodeLabel.SOCKET.value].append({
                "uuid": record.object_uuid,
                "path": record.object_path,
                "ip": record.object_ip,
                "port": record.object_port,
            })
        elif label == NodeLabel.EXECUTABLE:
            self._pending_nodes[NodeLabel.EXECUTABLE.value].append({
                "uuid": record.object_uuid,
                "path": record.object_path,
            })
        else:
            raise ValueError(f"Unexpected object label: {label}")

        self.stats.nodes_by_label[label.value] += 1

    def _ensure_host_node(self, host_id: str) -> None:
        """
        A minimal Host node in case something went wrong.
        """
        key = ("host", host_id)
        if key not in self._seen_structural:
            self._pending_nodes[NodeLabel.HOST.value].append({
                "uuid": host_id,
                "hostname": None,
                "os_details": None,
                "host_type": None,
            })
            self._seen_structural.add(key)

    def _ensure_user_node(self, user_uuid: str) -> None:
        """Similarly, minimal User node"""
        key = ("user", user_uuid)
        if key not in self._seen_structural:
            self._pending_nodes[NodeLabel.USER.value].append({
                "uuid": user_uuid,
                "username": None,
                "user_id": None,
            })
            self._seen_structural.add(key)

    def _ensure_ip_node(self, ip: str) -> None:
        key = ("ip", ip)
        if key not in self._seen_structural:
            self._pending_nodes[NodeLabel.IP_ADDRESS.value].append({"ip": ip})
            self._seen_structural.add(key)

    # structural edge accumulation
    def _add_structural(
        self,
        rel_type: StructuralRelType,
        src_uuid: str,
        dst_uuid: str,
    ) -> None:
        key = (rel_type.value, src_uuid, dst_uuid)
        if key in self._seen_structural:
            return
        self._seen_structural.add(key)

        self._pending_structural_edges[rel_type.value].append({
            "src_uuid": src_uuid,
            "dst_uuid": dst_uuid,
        })
        self.stats.structural_edges_by_type[rel_type.value] += 1

    def _add_structural_ip(
        self,
        rel_type: StructuralRelType,
        socket_uuid: str,
        ip: str,
    ) -> None:
        """Structural edge where the dst key is an IP string, not a uuid."""
        key = (rel_type.value, socket_uuid, ip)
        if key in self._seen_structural:
            return
        self._seen_structural.add(key)

        self._pending_structural_edges[rel_type.value].append({
            "src_uuid": socket_uuid,
            "dst_ip": ip,
        })
        self.stats.structural_edges_by_type[rel_type.value] += 1

    # Cypher execution
    def _execute_jobs(self, jobs: List[ct.CypherJob]) -> None:
        with self._driver.session(database=self._database) as session:
            def _run(tx):
                for query, params in jobs:
                    tx.run(query, **(params or {})).consume()
            session.execute_write(_run)


# YAM
def _rel_type_to_labels(rel: EventRelType) -> Tuple[NodeLabel, NodeLabel]:
    """Reverse-lookup map :/"""
    _MAP = {
        EventRelType.FORKS:          (NodeLabel.PROCESS,    NodeLabel.PROCESS),
        EventRelType.IS_EXECUTED_BY: (NodeLabel.EXECUTABLE, NodeLabel.PROCESS),
        EventRelType.IS_READ_BY:     (NodeLabel.FILE,       NodeLabel.PROCESS),
        EventRelType.WRITES:         (NodeLabel.PROCESS,    NodeLabel.FILE),
        EventRelType.SENDS:          (NodeLabel.PROCESS,    NodeLabel.SOCKET),
        EventRelType.IS_RECEIVED_BY: (NodeLabel.SOCKET,     NodeLabel.PROCESS),
    }
    return _MAP[rel]
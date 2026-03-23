"""
Cypher query templates for graph construction according to KRYSTAL-ish schema.

- queries based on UNWIND to iterate $rows for batch execution
- passed templates are strings with {label} and {rel_type} placeholders filled at call via .format()

Operation details: 
    - Event-edge queries use CREATE (each CommonRecord is a unique event, e.g. isReadBy)
    - Structural-edge queries use MERGE (many records may imply the same link, e.g. hasExe)
    - Node queries use MERGE to deduplicate
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .schema import EventRelType, NodeLabel, StructuralRelType

# alias for a cypher job
CypherJob = Tuple[str, Dict]

# Node MERGE templates; added COALESCE to processes, etc to not overwrite already present metadata with Null
_NODE_TEMPLATES: Dict[NodeLabel, str] = {
    NodeLabel.PROCESS: """
        UNWIND $rows AS row
        MERGE (n:Process {uuid: row.uuid})
        SET n.pid = COALESCE(row.pid, n.pid),
            n.cmdline = COALESCE(row.cmdline, n.cmdline)
    """,
    NodeLabel.FILE: """
        UNWIND $rows AS row
        MERGE (n:File {uuid: row.uuid})
        SET n.path = COALESCE(row.path, n.path)
    """,
    NodeLabel.SOCKET: """
        UNWIND $rows AS row
        MERGE (n:Socket {uuid: row.uuid})
        SET n.path = COALESCE(row.path, n.path),
            n.ip = COALESCE(row.ip, n.ip),
            n.port = COALESCE(row.port, n.port)
    """,
    NodeLabel.EXECUTABLE: """
        UNWIND $rows AS row
        MERGE (n:Executable {uuid: row.uuid})
        SET n.path = COALESCE(row.path, n.path)
    """,
    NodeLabel.HOST: """
        UNWIND $rows AS row
        MERGE (n:Host {uuid: row.uuid})
        SET n.hostname = row.hostname,
            n.os_details = row.os_details,
            n.host_type = row.host_type
    """,
    NodeLabel.IP_ADDRESS: """
        UNWIND $rows AS row
        MERGE (n:IPAddress {ip: row.ip})
    """,
    NodeLabel.USER: """
        UNWIND $rows AS row
        MERGE (n:User {uuid: row.uuid})
        SET n.username = row.username, n.user_id = row.user_id
    """,
}

# Event edge CREATE template  (rel_type inserted via .format())
_EVENT_EDGE_TEMPLATE = """
    UNWIND $rows AS row
    MATCH (src:{src_label} {{uuid: row.src_uuid}})
    MATCH (dst:{dst_label} {{uuid: row.dst_uuid}})
    CREATE (src)-[r:{rel_type} {{
        edge_uuid: row.edge_uuid,
        timestamp_ns: row.timestamp_ns,
        size_bytes: row.size_bytes,
        raw_event_type: row.raw_event_type
    }}]->(dst)
"""

# Structural edge MERGE templates
_STRUCTURAL_TEMPLATES: Dict[StructuralRelType, str] = {
    StructuralRelType.HAS_EXE: """
        UNWIND $rows AS row
        MATCH (src:Process {uuid: row.src_uuid})
        MATCH (dst:Executable {uuid: row.dst_uuid})
        MERGE (src)-[:hasExe]->(dst)
    """,
    StructuralRelType.HAS_USER: """
        UNWIND $rows AS row
        MATCH (src:Process {uuid: row.src_uuid})
        MATCH (dst:User {uuid: row.dst_uuid})
        MERGE (src)-[:hasUser]->(dst)
    """,
    StructuralRelType.ORIGINATES_FROM: """
        UNWIND $rows AS row
        MATCH (src:Process {uuid: row.src_uuid})
        MATCH (dst:Host {uuid: row.dst_uuid})
        MERGE (src)-[:originatesFrom]->(dst)
    """,
    StructuralRelType.HAS_SOCKET_IP: """
        UNWIND $rows AS row
        MATCH (src:Socket {uuid: row.src_uuid})
        MATCH (dst:IPAddress {ip: row.dst_ip})
        MERGE (src)-[:hasSocketIP]->(dst)
    """,
    StructuralRelType.HAS_HOST_IP: """
        UNWIND $rows AS row
        MATCH (src:Host {uuid: row.src_uuid})
        MERGE (dst:IPAddress {ip: row.dst_ip})
        MERGE (src)-[:hasHostIP]->(dst)
    """,
}

# Index & constraint creation
def build_index_statements() -> List[str]:
    """
    Unique constraints on node keys, range indexes on event edge timestamps.
    Returns all CREATE CONSTRAINT / CREATE INDEX statements.
    """
    stmts: List[str] = []

    # unique constraints on node keys
    for label in (
        NodeLabel.PROCESS, NodeLabel.FILE, NodeLabel.SOCKET,
        NodeLabel.EXECUTABLE, NodeLabel.HOST, NodeLabel.USER
    ):
        stmts.append(
            f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label.value}) REQUIRE n.uuid IS UNIQUE"
        )
    # uses ip as key; therefore seperate from uuid
    stmts.append(
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:IPAddress) REQUIRE n.ip IS UNIQUE"
    )

    # range indexes on event edge timestamp_ns
    # range index is the most generic index, 
    # supporting equality, membership, existence, range-, and prefix search
    for rel in EventRelType:
        stmts.append(
            f"CREATE RANGE INDEX IF NOT EXISTS FOR ()-[r:{rel.value}]-() ON (r.timestamp_ns)"
        )

    # range index on event edge edge_uuid (for lookups & later labeling)
    for rel in EventRelType:
        stmts.append(
            f"CREATE RANGE INDEX IF NOT EXISTS FOR ()-[r:{rel.value}]-() ON (r.edge_uuid)"
        )

    return stmts


# helpers:
# build jobs from row batches
def node_jobs(label: NodeLabel, rows: List[Dict], chunk_size: int = 10_000) -> List[CypherJob]:
    """build UNWIND jobs for node MERGE."""
    template = _NODE_TEMPLATES[label].strip()
    return [(template, {"rows": chunk}) for chunk in _chunks(rows, chunk_size)]

def event_edge_jobs(
    rel_type: EventRelType,
    src_label: NodeLabel,
    dst_label: NodeLabel,
    rows: List[Dict],
    chunk_size: int = 10_000,
) -> List[CypherJob]:
    """build UNWIND jobs for event edge CREATE."""
    query = _EVENT_EDGE_TEMPLATE.format(
        src_label=src_label.value,
        dst_label=dst_label.value,
        rel_type=rel_type.value,
    ).strip()
    return [(query, {"rows": chunk}) for chunk in _chunks(rows, chunk_size)]

def structural_edge_jobs(
    rel_type: StructuralRelType,
    rows: List[Dict],
    chunk_size: int = 10_000,
) -> List[CypherJob]:
    """build UNWIND jobs for structural edge MERGE."""
    template = _STRUCTURAL_TEMPLATES[rel_type].strip()
    return [(template, {"rows": chunk}) for chunk in _chunks(rows, chunk_size)]


# helper to yield in chunk sizes
def _chunks(xs: List, size: int):
    for i in range(0, len(xs), size):
        yield xs[i : i + size]
"""
Neo4j graph model definition for provenance graphs.
Roughly based on operating system agnostic KRYSTAL ontology.

Defines node labels, relationship types, and how they map from CommonRecord.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from provenance_explorer.common_record.schema import EdgeCategory

# Node labels
class NodeLabel(Enum):
    """node labels"""
    PROCESS    = "Process"
    FILE       = "File"
    SOCKET     = "Socket"
    EXECUTABLE = "Executable"
    HOST       = "Host"
    IP_ADDRESS = "IPAddress"
    USER       = "User"

# KRYSTALish relationship types
class EventRelType(Enum):
    """event relationship types"""
    FORKS           = "forks"
    IS_EXECUTED_BY  = "isExecutedBy"
    IS_READ_BY      = "isReadBy"
    WRITES          = "writes"
    SENDS           = "sends"
    IS_RECEIVED_BY  = "isReceivedBy"

class StructuralRelType(Enum):
    """Relationship types for structural (metadata) edges."""
    HAS_EXE        = "hasExe"
    HAS_USER       = "hasUser"
    ORIGINATES_FROM = "originatesFrom"
    HAS_SOCKET_IP  = "hasSocketIP"
    HAS_HOST_IP    = "hasHostIP"

# edge mapping: EdgeCategory => topology
@dataclass(frozen=True, slots=True)
class EdgeMapping:
    """
    How a CommonRecord's EdgeCategory maps onto KRYSTALish elements.

    For information flow direction -> src_is_subject:
        True: subject_uuid is the relationship source (FORK, WRITE, SEND)
        False: object_uuid is the relationship source (EXECUTE, READ, RECV)
    """
    src_label: NodeLabel
    dst_label: NodeLabel
    rel_type: EventRelType
    src_is_subject: bool 
    object_label: NodeLabel

EDGE_CATEGORY_MAP: Dict[EdgeCategory, EdgeMapping] = {
    #                     src_label                         dst_label             rel_type                     src_is_subj  object_label
    EdgeCategory.FORK:    EdgeMapping(NodeLabel.PROCESS,    NodeLabel.PROCESS,    EventRelType.FORKS,          True,        NodeLabel.PROCESS),
    EdgeCategory.EXECUTE: EdgeMapping(NodeLabel.EXECUTABLE, NodeLabel.PROCESS,    EventRelType.IS_EXECUTED_BY, False,       NodeLabel.EXECUTABLE),
    EdgeCategory.READ:    EdgeMapping(NodeLabel.FILE,       NodeLabel.PROCESS,    EventRelType.IS_READ_BY,     False,       NodeLabel.FILE),
    EdgeCategory.WRITE:   EdgeMapping(NodeLabel.PROCESS,    NodeLabel.FILE,       EventRelType.WRITES,         True,        NodeLabel.FILE),
    EdgeCategory.SEND:    EdgeMapping(NodeLabel.PROCESS,    NodeLabel.SOCKET,     EventRelType.SENDS,          True,        NodeLabel.SOCKET),
    EdgeCategory.RECV:    EdgeMapping(NodeLabel.SOCKET,     NodeLabel.PROCESS,    EventRelType.IS_RECEIVED_BY, False,       NodeLabel.SOCKET),
}
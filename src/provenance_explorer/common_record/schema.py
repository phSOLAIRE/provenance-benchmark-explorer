"""
Common record schema for cross-dataset provenance graph construction.

Defines the normalized intermediate representation that all dataset-specific parsers produce. 
Every CommonRecord maps to exactly one edge in the target provenance graph model (KRYSTAL-like OS-agnostic schema).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


# Edge categories - these map 1:1 to the target graph edges
class EdgeCategory(Enum):
    """
    The six provenance-relevant edge types, derived from the target graph model.

    Each category absorbs multiple raw event types across datasets.
    The mapping is documented per subdataset in configs/.
    """

    FORK = auto()       # (Process) -[forks]-> (Process)
    EXECUTE = auto()    # (File) -[isExecutedBy]-> (Process)
    READ = auto()       # (File) -[isReadBy]-> (Process)
    WRITE = auto()      # (Process) -[writes]-> (File)
    SEND = auto()       # (Process) -[sends]-> (Socket)
    RECV = auto()       # (Socket) -[isReceivedBy]-> (Process)

# Object roles - what role the object plays in the common graph model
class ObjectRole(Enum):
    """Resolved role of the event's target object in the provenance graph."""

    FILE = auto()       # File node (includes FILE_OBJECT_FILE, BLOCK, PEFILE, DIR, CHAR, RegistryKey)
    SOCKET = auto()     # Socket node (NetFlowObject, FILE_OBJECT_UNIX_SOCKET, FLOW)
    PROCESS = auto()    # Process node (target of FORK/CLONE/CREATE_THREAD)
    EXECUTABLE = auto() # Executable (target of EXECUTE/LOADLIBRARY - also a file, but tagged for hasExe edge)


# Drop reasons - why a record was excluded from the common representation
class DropReason(Enum):
    """
    Enumerated reasons for excluding a record. Each dropped record increments
    a counter keyed by (dataset, sub_dataset, DropReason) in the DropLog.
    """

    SRCSINK_TARGET = auto()          # Object is a SrcSinkObject (Android-specific)
    MEMORY_TARGET = auto()           # Object is a MemoryObject
    IPC_LOCAL_TARGET = auto()        # Object is IpcObject (local IPC, no network info)
    NULL_OBJECT = auto()             # predicateObject is None / missing
    INVERTED_SUBJECT = auto()        # Subject is not a process/thread/unit (e.g. Marple FileObject-as-subject)
    ABSTRACT_FLOW = auto()           # EVENT_FLOWS_TO (Cadets-specific abstract link)
    NON_PROVENANCE_EVENT = auto()    # Event type not in the information-flow set
    OBJECT_TYPE_UNRESOLVABLE = auto()  # uuid not found in object lookup
    AMBIGUOUS_OBJECT_TYPE = auto()   # uuid maps to multiple types, none preferred (logged, not necessarily dropped)
    RECORD_IS_NOT_EVENT = auto()     # cdm record is a Subject/Host/FileObject definition, not an event
    PARSE_ERROR = auto()             # json.loads or field extraction failed


# Common record - the normalized intermediate representation
@dataclass(slots=True, frozen=True)
class CommonRecord:
    """
    One provenance-relevant event, normalized across all datasets.

    Each CommonRecord maps to exactly one edge in the target graph:
        subject_uuid  ->  [edge_category]  ->  object_uuid

    The subject is always a process (threads/units collapsed to parent).
    The object role determines which graph node type to create.
    """

    # temporal
    timestamp_ns: int                   # Unified nanosecond epoch (from iterator)

    # classification
    edge_category: EdgeCategory         # Which graph edge this becomes
    object_role: ObjectRole             # What the target object represents
    edge_uuid: str                      # edge uuid

    # entity identifiers
    subject_uuid: str                   # Process uuid (after thread/unit collapse)
    object_uuid: str                    # Target entity uuid

    # provenance context
    dataset: str                        # "e3", "e5", "optc"
    sub_dataset: str                    # "cadets", "theia", "aia_51_75", ...
    host_id: str                        # Host identifier

    # optional metadata (populated when available from object lookup)
    object_path: Optional[str] = None   # File path, socket path, or None
    object_ip: Optional[str] = None     # IP address (OpTC flows, NetFlowObject)
    object_port: Optional[int] = None   # Port number (OpTC flows, NetFlowObject)
    pid: Optional[int] = None           # Process ID if available
    size_bytes: Optional[int] = None    # Event size field if available
    cmdline: Optional[str] = None       # Process command line if resolvable
    user_principal: Optional[str] = None     # User/principal behind the process. cdm: principal uuid; for OpTC: raw string, likely meant to be uniue (e.g. "NT AUTHORITY\\SYSTEM").

    # raw provenance (for docs / debug)
    raw_event_type: str = ""            # Original event type string before normalization
    raw_object_type: str = ""           # Original object type string before normalization
    raw_subject_type: str = ""          # Original subject type (SUBJECT_PROCESS, SUBJECT_UNIT, ...)
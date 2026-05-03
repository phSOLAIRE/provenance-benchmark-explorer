"""
Shared read/write event grouping used to allow comaprisons to HPC. 

The HPC login-node capture exposes two kinds of information-flow events via /proc/<pid>/io: 
    - read-syscall counts (syscr) 
    - and write-syscall counts (syscw) 
    
Everything else that the CDM or eCAR schemas record 
(FORK/CLONE/EXEC/MMAP/LOADLIBRARY/SEND*/RECV*/...) has no HPC analogue
"""
from __future__ import annotations

import pandas as pd

READ_EVENTS = frozenset({
    "EVENT_READ",       # CDM18 / CDM20
    "FILE_READ",        # eCAR
    "SYSCALL_READ",     # HPC proxy (syscr delta)
})
WRITE_EVENTS = frozenset({
    "EVENT_WRITE",      # CDM18 / CDM20
    "FILE_WRITE",       # eCAR
    "SYSCALL_WRITE",    # HPC proxy (syscw delta)
})

# for clustering, only use r/w to allow comparison to HPC
_RW_CLUSTERING = READ_EVENTS | WRITE_EVENTS

# include all infoflow for this 
ALL_INFOFLOW = {
    "EVENT_FORK",
    "EVENT_CLONE",
    "EVENT_CREATE_THREAD",
    "EVENT_EXECUTE",
    "EVENT_LOADLIBRARY",
    "EVENT_READ",
    "EVENT_MMAP",
    "EVENT_LSEEK",
    "EVENT_WRITE",
    "EVENT_SENDMSG",
    "EVENT_SENDTO",
    "EVENT_WRITE",
    "EVENT_RECVFROM",
    "EVENT_RECVMSG",
    "EVENT_READ",
    "FILE_READ",
    "FILE_WRITE",
    "MODULE_LOAD",
    "PROCESS_CREATE",
    "FLOW_START",
    "FLOW_MESSAGE",
    "REGISTRY_ADD",
    "REGISTRY_EDIT",
}

def collapse_to_rw(
    event_counts: pd.DataFrame,
    event_type_col: str = "event_type",
) -> pd.DataFrame:
    """
    Return a filtered + relabelled copy of event_counts containing only the narrow r/w events.
    The counts for event types that collapse to the same label on the same (host_id, time_bin_ns) are summed
    """
    df = event_counts[event_counts[event_type_col].isin(_RW_CLUSTERING)].copy()
    mapping = {e: "READ" for e in READ_EVENTS}
    mapping.update({e: "WRITE" for e in WRITE_EVENTS})
    df[event_type_col] = df[event_type_col].map(mapping)

    group_cols = [c for c in df.columns if c != "count"]
    df = df.groupby(group_cols, as_index=False)["count"].sum()
    return df # type: ignore

"""
Dispatch: 
classifies raw parsed records into CommonRecord or drops.

Needs the (compacted) ObjectLookup (bytes uuids, CompactInfo NamedTuples).
The dispatch tables map (event_type, role_int) -> (EdgeCategory, ObjectRole enum).
"""

from __future__ import annotations

from typing import Any, Optional

from .schema import CommonRecord, EdgeCategory, ObjectRole, DropReason
from .object_lookup import (
    ObjectLookup, CompactInfo, ObjectRoleCompact,
    uuid_to_bytes, bytes_to_uuid, _extract_string, _extract_int,
)
from .drop_log import DropLog


# cdm dispatch table
# (raw_event_type, compact_role_int) => (EdgeCategory, ObjectRole enum)
_F = ObjectRoleCompact.FILE
_S = ObjectRoleCompact.SOCKET
_P = ObjectRoleCompact.PROCESS

CDM_DISPATCH: dict[tuple[str, int], tuple[EdgeCategory, ObjectRole]] = {
    # FORK-ISH
    ("EVENT_FORK", _P):            (EdgeCategory.FORK, ObjectRole.PROCESS),
    ("EVENT_CLONE", _P):           (EdgeCategory.FORK, ObjectRole.PROCESS),
    ("EVENT_CREATE_THREAD", _P):   (EdgeCategory.FORK, ObjectRole.PROCESS),

    # EXECUTE-ISH
    ("EVENT_EXECUTE", _F):         (EdgeCategory.EXECUTE, ObjectRole.EXECUTABLE),
    ("EVENT_LOADLIBRARY", _F):     (EdgeCategory.EXECUTE, ObjectRole.EXECUTABLE),

    # READ-ISH
    ("EVENT_READ", _F):            (EdgeCategory.READ, ObjectRole.FILE),
    ("EVENT_MMAP", _F):            (EdgeCategory.READ, ObjectRole.FILE),
    ("EVENT_LSEEK", _F):           (EdgeCategory.READ, ObjectRole.FILE),

    # WRITE-ISH
    ("EVENT_WRITE", _F):           (EdgeCategory.WRITE, ObjectRole.FILE),

    # SEND-ISH
    ("EVENT_SENDMSG", _S):         (EdgeCategory.SEND, ObjectRole.SOCKET),
    ("EVENT_SENDTO", _S):          (EdgeCategory.SEND, ObjectRole.SOCKET),
    ("EVENT_WRITE", _S):           (EdgeCategory.SEND, ObjectRole.SOCKET),  # possibly reclassified

    # RECV-ISH
    ("EVENT_RECVFROM", _S):        (EdgeCategory.RECV, ObjectRole.SOCKET),
    ("EVENT_RECVMSG", _S):         (EdgeCategory.RECV, ObjectRole.SOCKET),
    ("EVENT_READ", _S):            (EdgeCategory.RECV, ObjectRole.SOCKET),  # possibly reclassified
}


# OpTC dispatch table
# (action, object_field, compact_role_int) => (EdgeCategory, ObjectRole enum)
OPTC_DISPATCH: dict[tuple[str, str, int], tuple[EdgeCategory, ObjectRole]] = {
    ("READ", "FILE", _F):          (EdgeCategory.READ, ObjectRole.FILE),
    ("WRITE", "FILE", _F):         (EdgeCategory.WRITE, ObjectRole.FILE),
    ("LOAD", "MODULE", _F):        (EdgeCategory.EXECUTE, ObjectRole.EXECUTABLE),
    ("CREATE", "PROCESS", _P):     (EdgeCategory.FORK, ObjectRole.PROCESS),
    ("START", "FLOW", _S):         (EdgeCategory.SEND, ObjectRole.SOCKET),
    ("MESSAGE", "FLOW", _S):       (EdgeCategory.SEND, ObjectRole.SOCKET),
    ("ADD", "REGISTRY", _F):       (EdgeCategory.WRITE, ObjectRole.FILE),
    ("EDIT", "REGISTRY", _F):      (EdgeCategory.WRITE, ObjectRole.FILE),
}

# subject type guards
_PROCESS_LIKE = {"SUBJECT_PROCESS", "SUBJECT_THREAD", "SUBJECT_UNIT"}


# cdm dispatch
def dispatch_cdm_event(
    timestamp_ns: int,
    record_value: dict[str, Any],
    dataset: str,
    sub_dataset: str,
    lookup: ObjectLookup,
    drop_log: DropLog,
    host_id_outer: str = "",
) -> Optional[CommonRecord]:
    """
    returns CommonRecord | None.

    host_id_outer: for cdm20, hostId is a top-level field outside datum.
    Pass it in from the iterator wrapper.
    """
    raw_event_type = record_value.get("type", "")

    if raw_event_type == "EVENT_FLOWS_TO":
        drop_log.record_drop(dataset, sub_dataset, DropReason.ABSTRACT_FLOW,
                             raw_event_type=raw_event_type)
        return None
    
    # Event uuid
    event_ref = record_value.get("uuid")
    event_str = _unwrap_uuid(event_ref)
    if not event_str:
        drop_log.record_drop(dataset, sub_dataset, DropReason.PARSE_ERROR,
                             raw_event_type=raw_event_type)
        return None

    # Subject uuid
    subject_ref = record_value.get("subject")
    subject_str = _unwrap_uuid(subject_ref)
    if not subject_str:
        drop_log.record_drop(dataset, sub_dataset, DropReason.INVERTED_SUBJECT,
                             raw_event_type=raw_event_type)
        return None

    try:
        subject_bytes = uuid_to_bytes(subject_str)
    except ValueError:
        drop_log.record_drop(dataset, sub_dataset, DropReason.PARSE_ERROR,
                             raw_event_type=raw_event_type)
        return None

    # is subject process-like?
    subj_info = lookup.get(subject_bytes)
    if subj_info is None:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.OBJECT_TYPE_UNRESOLVABLE,
            raw_event_type=raw_event_type, raw_object_type="subject_missing"
        )
        return None

    if not any(ps in subj_info.types_raw for ps in _PROCESS_LIKE):
        drop_log.record_drop(dataset, sub_dataset, DropReason.INVERTED_SUBJECT,
                             raw_event_type=raw_event_type, raw_object_type=subj_info.types_raw)
        return None

    # Collapse thread/unit -> process
    resolved_subj_bytes = lookup.resolve_to_process(subject_bytes)

    # Object uuid
    object_ref = record_value.get("predicateObject")
    object_str = _unwrap_uuid(object_ref)
    if not object_str:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.NULL_OBJECT,raw_event_type=raw_event_type
        )
        return None

    try:
        object_bytes = uuid_to_bytes(object_str)
    except ValueError:
        drop_log.record_drop(dataset, sub_dataset, DropReason.PARSE_ERROR,
                             raw_event_type=raw_event_type)
        return None

    # Resolve object type
    obj_info = lookup.get(object_bytes)
    if obj_info is None:
        # uuid not in filtered lookup -> out-of-scope type (SrcSink, Memory, IPC, etc.)
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.OBJECT_TYPE_UNRESOLVABLE,
            raw_event_type=raw_event_type,raw_object_type="not_in_filtered_lookup"
        )
        return None

    # Dispatch
    dispatch_key = (raw_event_type, obj_info.role)
    mapping = CDM_DISPATCH.get(dispatch_key)
    if mapping is None:
        drop_log.record_drop(dataset, sub_dataset, DropReason.NON_PROVENANCE_EVENT,
                             raw_event_type=raw_event_type, raw_object_type=obj_info.types_raw)
        return None

    edge_category, final_role = mapping

    # Host ID: prefer outer (cdm20) then inner (cdm18)
    host_id = host_id_outer or record_value.get("hostId", "")
    if isinstance(host_id, dict):
        host_id = next(iter(host_id.values()), "")

    # Optional fields
    object_path = _extract_string(record_value.get("predicateObjectPath")) or obj_info.path
    size_bytes = _extract_int(record_value.get("size"))

    resolved_info = lookup.get(resolved_subj_bytes)
    pid = resolved_info.pid if resolved_info else None
    cmdline = resolved_info.cmdline if resolved_info else None
    principal_uuid = (
        bytes_to_uuid(resolved_info.principal_uuid)
        if resolved_info and resolved_info.principal_uuid else None
    )

    return CommonRecord(
        timestamp_ns=timestamp_ns,
        edge_category=edge_category,
        object_role=final_role,
        edge_uuid=event_str,
        subject_uuid=bytes_to_uuid(resolved_subj_bytes),
        object_uuid=bytes_to_uuid(object_bytes),
        dataset=dataset,
        sub_dataset=sub_dataset,
        host_id=host_id or "",
        object_path=object_path,
        object_ip=obj_info.ip,
        object_port=obj_info.port,
        pid=pid,
        size_bytes=size_bytes,
        cmdline=cmdline,
        user_principal=principal_uuid,
        raw_event_type=raw_event_type,
        raw_object_type=obj_info.types_raw,
        raw_subject_type=subj_info.types_raw,
    )


# OpTC dispatch
def dispatch_optc_event(
    timestamp_ns: int,
    rec: dict[str, Any],
    dataset: str,
    sub_dataset: str,
    lookup: ObjectLookup,
    drop_log: DropLog,
) -> Optional[CommonRecord]:
    """Classify one OpTC record. Returns CommonRecord or None."""
    action = rec.get("action", "")
    obj_type = rec.get("object", "")
    event_str = (rec.get("id") or "").upper()
    actor_str = (rec.get("actorID") or "").upper()
    object_str = (rec.get("objectID") or "").upper()
    props = rec.get("properties", {}) or {}
    raw_event_type = f"{obj_type}+{action}"

    if not event_str:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.PARSE_ERROR,raw_event_type=raw_event_type
        )
        return None

    if not actor_str:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.INVERTED_SUBJECT,raw_event_type=raw_event_type
        )
        return None
    if not object_str:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.NULL_OBJECT, raw_event_type=raw_event_type
        )
        return None

    try:
        object_bytes = uuid_to_bytes(object_str)
    except ValueError:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.PARSE_ERROR,raw_event_type=raw_event_type
        )
        return None

    obj_info = lookup.get(object_bytes)
    if obj_info is None:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.OBJECT_TYPE_UNRESOLVABLE,
            raw_event_type=raw_event_type, raw_object_type=obj_type
        )
        return None

    dispatch_key = (action, obj_type, obj_info.role)
    mapping = OPTC_DISPATCH.get(dispatch_key)
    if mapping is None:
        drop_log.record_drop(
            dataset, sub_dataset, DropReason.NON_PROVENANCE_EVENT,
            raw_event_type=raw_event_type, raw_object_type=obj_info.types_raw
        )
        return None

    edge_category, final_role = mapping

    # OpTC principal is an inline string (e.g. "NT AUTHORITY\\SYSTEM"), not a uuid.
    # !! Passed through as-is when non-empty !!
    principal_raw = rec.get("principal", "")
    user_principal = principal_raw if principal_raw else None

    return CommonRecord(
        timestamp_ns=timestamp_ns,
        edge_category=edge_category,
        object_role=final_role,
        edge_uuid=event_str,
        subject_uuid=actor_str,
        object_uuid=object_str,
        dataset=dataset,
        sub_dataset=sub_dataset,
        host_id=rec.get("hostname", ""),
        object_path=obj_info.path or props.get("file_path"),
        object_ip=obj_info.ip or props.get("dest_ip") or props.get("src_ip"),
        object_port=obj_info.port or _extract_int(props.get("dest_port")),
        pid=_extract_int(rec.get("pid")),
        size_bytes=_extract_int(props.get("size")),
        cmdline=props.get("image_path"),
        user_principal=user_principal,
        raw_event_type=raw_event_type,
        raw_object_type=obj_info.types_raw,
        raw_subject_type="PROCESS",
    )


# Helpers
def _unwrap_uuid(ref: Any) -> Optional[str]:
    """Extract uuid string from cdm union field (dict or string)."""
    if ref is None:
        return None
    if isinstance(ref, str):
        return ref.upper()
    if isinstance(ref, dict):
        val = next(iter(ref.values()), None)
        return val.upper() if isinstance(val, str) else None
    return None
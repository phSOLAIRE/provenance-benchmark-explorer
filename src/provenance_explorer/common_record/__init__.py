"""
provenance_explorer.common_record
for mormalized provenance event streaming.

Usage: 
first and foremost
    iterate_common_records(dataset, sub_dataset, ...) -> Iterator[CommonRecord]
    (or for convenience handel all sub-datasets): iterate_all_common_records(dataset, ...) -> Iterator[CommonRecord]

for making the lookup tables explicitly: 
    build_object_lookup(dataset, sub_dataset, ...) -> ObjectLookup

Types used in the classes:
    CommonRecord, EdgeCategory, ObjectRole, DropReason, DropLog, ObjectLookup
"""

from .schema import CommonRecord, EdgeCategory, ObjectRole, DropReason
from .drop_log import DropLog
from .object_lookup import (
    ObjectLookup, CompactInfo, ObjectRoleCompact,
    HostInfo, PrincipalInfo,
)
from .common_record_iterator import (
    iterate_common_records,
    iterate_all_common_records,
)

__all__ = [
    "CommonRecord",
    "EdgeCategory",
    "ObjectRole",
    "DropReason",
    "CompactInfo",
    "ObjectRoleCompact",
    "HostInfo",
    "PrincipalInfo",
    "DropLog",
    "ObjectLookup",
    "iterate_common_records",
    "iterate_all_common_records",
]
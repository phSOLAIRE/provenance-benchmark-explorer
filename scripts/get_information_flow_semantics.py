"""
CDM Only
print out what object types are connected by certain event types.
Iterates over records, builds a uuid -> (basic_type, subtype) map for non-Event records,
and for information-flow events, resolves predicate object UUIDs to their types.
"""
from __future__ import annotations

from collections import defaultdict
from pprint import pprint

from provenance_explorer.registry.registry_all import get_big_registry
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import PARSERS, TS_EXTRACTORS

INFORMATION_FLOW_EVENTS = [
    "EVENT_CLONE",
    "EVENT_EXECUTE",
    "EVENT_FLOWS_TO",
    "EVENT_FORK",
    "EVENT_MMAP",
    "EVENT_READ",
    "EVENT_RECVFROM",
    "EVENT_SENDMSG",
    "EVENT_SENDTO",
    "EVENT_WRITE",
    "EVENT_RECVMSG",
]

# types that have a "type" field as subtype
_TYPED_RECORDS = frozenset([
    "Event", "FileObject", "Principal", "SrcSinkObject", "Subject", "IpcObject",
])
# types that have a "hostType" field as subtype
_HOST_RECORDS = frozenset(["Host"])


def _get_uuid(record_value: dict) -> str | None:
    uuid_field = record_value.get("uuid")
    if uuid_field is None:
        return None
    # uuid can be a plain string or a nested dict like {"com.bbn.tc...UUID": "actual-uuid"}
    if isinstance(uuid_field, str):
        return uuid_field
    if isinstance(uuid_field, dict):
        return next(iter(uuid_field.values()), None)
    return None


def _get_subtype(record_type_short: str, record_value: dict) -> str | None:
    if record_type_short in _TYPED_RECORDS:
        return record_value.get("type")
    if record_type_short in _HOST_RECORDS:
        return record_value.get("hostType")
    return None


def _resolve_ref(ref, uuid_map: dict[str, tuple[str, str | None]]) -> tuple[str | None, str | None]:
    """
    Resolve a subject/predicateObject reference to (basic_type, subtype).
    ref can be None, a UUID string, or a nested dict.
    """
    if ref is None:
        return (None, None)
    if isinstance(ref, dict):
        ref = next(iter(ref.values()), None)
    if ref is None:
        return (None, None)
    return uuid_map.get(ref, ("Unresolved", "Unresolved"))


def search_loop(dataset: str, search_seconds: int = 60) -> dict[str, dict[tuple, int]]:
    """
    uuid -> (basic_type, subtype_or_None)
    populated from all non-Event records; Events are not stored, only queried
    
    returns dict of
      {"sub_dataset":
          {
              (subject_type, subject_subtype, EVENT_TYPE, predObj1_basic, predObj1_subtype, predObj2_basic, predObj2_subtype)
              : <int count>
          }
      }
    """
    registry_all = get_big_registry(dataset)
    out: dict[str, dict[tuple, int]] = {}

    for sub_dataset, registry in registry_all.items():
        print(f"[processing] {sub_dataset}")

        ts_extr = TS_EXTRACTORS[(dataset, sub_dataset)]
        parse_fn = PARSERS[(dataset, sub_dataset)]

        iterator = make_dataset_iterator(
            registry=registry,
            parse_fn=parse_fn,
            ts_extractor=ts_extr,
            test_run_seconds=search_seconds,
        )

        uuid_map: dict[str, tuple[str, str | None]] = {}
        # buffer events whose predicate objects we haven't seen yet for second pass, as datasets appear unordered
        deferred_events: list[tuple[str | None, str, str | None, str | None]] = []
        counts: dict[tuple, int] = defaultdict(int)

        for _, rec in iterator:
            rec = rec["datum"]
            record_type = next(iter(rec.keys()))
            record_type_short = record_type.rsplit('.', 1)[-1]
            record_value = rec[record_type]

            if record_type_short == "Event":
                event_type = record_value.get("type")
                if event_type not in INFORMATION_FLOW_EVENTS:
                    continue

                subject_ref = record_value.get("subject")
                pred1_ref = record_value.get("predicateObject")
                pred2_ref = record_value.get("predicateObject2")

                subj_basic, subj_sub = _resolve_ref(subject_ref, uuid_map)
                p1_basic, p1_sub = _resolve_ref(pred1_ref, uuid_map)
                p2_basic, p2_sub = _resolve_ref(pred2_ref, uuid_map)

                # if any reference is unresolved, defer for a second pass
                if "Unresolved" in (subj_basic, p1_basic, p2_basic):
                    deferred_events.append((subject_ref, event_type, pred1_ref, pred2_ref))
                else:
                    key = (subj_basic, subj_sub, event_type, p1_basic, p1_sub, p2_basic, p2_sub)
                    counts[key] += 1
            else:
                # non-Event: register in uuid_map
                uuid = _get_uuid(record_value)
                if uuid is not None:
                    subtype = _get_subtype(record_type_short, record_value)
                    uuid_map[uuid] = (record_type_short, subtype)

        # second pass; try to resolve deferred events again
        for subject_ref, event_type, pred1_ref, pred2_ref in deferred_events:
            subj_basic, subj_sub = _resolve_ref(subject_ref, uuid_map)
            p1_basic, p1_sub = _resolve_ref(pred1_ref, uuid_map)
            p2_basic, p2_sub = _resolve_ref(pred2_ref, uuid_map)
            key = (subj_basic, subj_sub, event_type, p1_basic, p1_sub, p2_basic, p2_sub)
            counts[key] += 1

        out[sub_dataset] = dict(counts)

    return out


def print_results(results: dict[str, dict[tuple, int]]) -> None:
    for sub_dataset, counts in sorted(results.items()):
        print(f"\n{'='*80}")
        print(f"  {sub_dataset}")
        print(f"{'='*80}")
        for key, count in sorted(counts.items(), key=lambda x: x[0][2]):
            subj_basic, subj_sub, event_type, p1_basic, p1_sub, p2_basic, p2_sub = key

            # skip fully uninformative lines where all three slots aer unresolved 
            resolved_slots = [v for v in (subj_basic, p1_basic, p2_basic) if v is not None]
            if all(v == "Unresolved" for v in resolved_slots):
                continue

            subj_str = f"{subj_basic}({subj_sub})" if subj_sub else str(subj_basic)
            p1_str = f"{p1_basic}({p1_sub})" if p1_sub else str(p1_basic)
            p2_str = f"{p2_basic}({p2_sub})" if p2_sub else str(p2_basic)
            print(f"  {count:>8}x  {subj_str}  --{event_type}-->  {p1_str}  |  {p2_str}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Explore information flow event semantics in CDM datasets")
    parser.add_argument("dataset", choices=["e3", "e5"], help="Which dataset family to process")
    parser.add_argument("--seconds", type=int, default=60, help="Test run duration per sub-dataset in seconds")
    args = parser.parse_args()

    results = search_loop(dataset=args.dataset, search_seconds=args.seconds)
    print_results(results)
"""
ECAR Only
print out what object types are connected via certain (Object, Action) tuples.
"""
from __future__ import annotations

from collections import defaultdict
from pprint import pprint

from provenance_explorer.registry.darpa_optc_registry import OPTC_ALL
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import PARSERS, TS_EXTRACTORS

INFORMATION_FLOW_TUPLES = [
    ("FILE","READ"),
    ("FILE","WRITE"),
    ("FLOW","MESSAGE"),
    ("FLOW","START"),
    ("MODULE","LOAD"),
    ("PROCESS","CREATE"),
    ("REGISTRY","ADD"),
    ("REGISTRY","EDIT"),
    ("SHELL","COMMAND"),
    ("THREAD","CREATE"),
    ("THREAD","REMOTE_CREATE"),
]


def search_loop(search_seconds: int = 60) -> dict[str, dict[tuple, int]]:
    """
    For eCAR, every record is an event with object/action fields
    
    returns dict of
      {"sub_dataset":
          {
              (actor_type, "OBJECT+ACTION", target_object_type)
              : <int count>
          }
      }
    """
    out: dict[str, dict[tuple, int]] = {}

    for sub_dataset, registry in OPTC_ALL.items():
        print(f"[processing] {sub_dataset}")

        ts_extr = TS_EXTRACTORS[("optc", sub_dataset)]
        parse_fn = PARSERS[("optc", sub_dataset)]

        iterator = make_dataset_iterator(
            registry=registry,
            parse_fn=parse_fn,
            ts_extractor=ts_extr,
            test_run_seconds=search_seconds,
        )

        # id -> set of object types seen for that UUID
        # (same object can appear as e.g. FILE and MODULE)
        id_map: dict[str, set[str]] = defaultdict(set)
        deferred: list[tuple[str | None, str, str | None]] = []  # (actorID, event_str, objectID)

        for _, rec in iterator:
            obj_type = rec.get("object")
            action = rec.get("action")
            object_id = rec.get("objectID")
            actor_id = rec.get("actorID")

            if obj_type is None or action is None:
                continue

            # register objectID type whenever we see it
            if object_id and object_id != "00000000-0000-0000-0000-000000000000":
                id_map[object_id].add(obj_type)

            event_tuple = (obj_type, action)
            if event_tuple not in INFORMATION_FLOW_TUPLES:
                continue

            event_str = f"{obj_type}+{action}"
            deferred.append((actor_id, event_str, object_id))

        # resolve again in second apss
        counts: dict[tuple, int] = defaultdict(int)
        for actor_id, event_str, object_id in deferred:
            actor_types = id_map.get(actor_id) # type: ignore
            actor_label = "+".join(sorted(actor_types)) if actor_types else "Unresolved"

            target_types = id_map.get(object_id) # type: ignore
            target_label = "+".join(sorted(target_types)) if target_types else "Unresolved"

            key = (actor_label, event_str, target_label)
            counts[key] += 1

        out[sub_dataset] = dict(counts)

    return out


def print_results(results: dict[str, dict[tuple, int]]) -> None:
    for sub_dataset, counts in sorted(results.items()):
        print(f"\n{'='*80}")
        print(f"  {sub_dataset}")
        print(f"{'='*80}")
        for key, count in sorted(counts.items(), key=lambda x: x[0][1]):
            actor_type, event_str, target_type = key

            # skip fully unresolved lines
            if actor_type == "Unresolved":
                continue

            print(f"  {count:>8}x  {actor_type}  --{event_str}-->  {target_type}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Explore information flow event semantics in CDM datasets")
    parser.add_argument("--seconds", type=int, default=60, help="Test run duration per sub-dataset in seconds")
    args = parser.parse_args()

    results = search_loop(search_seconds=args.seconds)
    print_results(results)
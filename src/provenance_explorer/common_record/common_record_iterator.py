"""
Common record iterator:
The core interface for normalized provenance event streaming.

Usage:
    from provenance_explorer.common_record import iterate_common_records, DropLog

    drop_log = DropLog()
    for rec in iterate_common_records("e3", "cadets", drop_log=drop_log):
        do_something(rec.edge_category, rec.subject_uuid, rec.object_uuid)

    print(drop_log.summary("e3", "cadets"))
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterator, Optional

from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import TS_EXTRACTORS, PARSERS
from provenance_explorer.registry.registry_all import get_subdataset_registry

from .schema import CommonRecord, DropReason
from .object_lookup import ObjectLookup
from .dispatch import dispatch_cdm_event, dispatch_optc_event
from .drop_log import DropLog

logger = logging.getLogger(__name__)


def _default_cache_root() -> Path:
    import os
    work = Path(os.getenv("WORK", ""))
    return work / "provenance-explorer-cache"


def _ensure_lookup(
    dataset: str,
    sub_dataset: str,
    cache_root: Path,
    force_rebuild: bool = False,
    test_run_seconds: Optional[int] = None,
) -> ObjectLookup:
    """Build or load the ObjectLookup for a subdataset."""
    if not force_rebuild:
        cached = ObjectLookup.load(dataset, sub_dataset, cache_root)
        if cached is not None:
            return cached

    logger.info(f"Building object lookup for {dataset}/{sub_dataset}...")
    registry = get_subdataset_registry(dataset, sub_dataset)
    ts_extr = TS_EXTRACTORS[(dataset, sub_dataset)]
    parse_fn = PARSERS[(dataset, sub_dataset)]

    iterator = make_dataset_iterator(
        registry=registry,
        parse_fn=parse_fn,
        ts_extractor=ts_extr,
        test_run_seconds=test_run_seconds,
    )

    lookup = ObjectLookup.build_from_iterator(
        dataset=dataset,
        sub_dataset=sub_dataset,
        iterator=iterator,
        cache_root=cache_root,
        is_optc=(dataset == "optc"),
    )
    lookup.save(cache_root)
    return lookup


def iterate_common_records(
    dataset: str,
    sub_dataset: str,
    drop_log: Optional[DropLog] = None,
    cache_root: Optional[Path] = None,
    force_rebuild_lookup: bool = False,
    t_start: Optional[int] = None,
    t_end: Optional[int] = None,
    test_run_seconds: Optional[int] = None,
) -> Iterator[CommonRecord]:
    """
    Iterate a subdataset, yielding CommonRecords.

    Pass 1 (object lookup) is built or loaded from cache.
    Pass 2 iterates events and dispatches.

    Dropped records are logged to drop_log.
    """

    if cache_root is None:
        cache_root = _default_cache_root()
    if drop_log is None:
        drop_log = DropLog()

    # Pass 1
    lookup = _ensure_lookup(
        dataset, sub_dataset, cache_root,
        force_rebuild=force_rebuild_lookup,
        test_run_seconds=test_run_seconds,
    )

    # pass 2
    logger.info(f"Pass 2: iterating {dataset}/{sub_dataset}...")
    t0 = time.time()

    registry = get_subdataset_registry(dataset, sub_dataset)
    ts_extr = TS_EXTRACTORS[(dataset, sub_dataset)]
    parse_fn = PARSERS[(dataset, sub_dataset)]

    iterator = make_dataset_iterator(
        registry=registry,
        parse_fn=parse_fn,
        ts_extractor=ts_extr,
        t_start=t_start,
        t_end=t_end,
        test_run_seconds=test_run_seconds,
    )

    is_optc = dataset == "optc"
    kept = 0
    seen = 0

    for timestamp_ns, rec in iterator:
        seen += 1
        drop_log.record_seen(dataset, sub_dataset)

        if is_optc:
            result = dispatch_optc_event(
                timestamp_ns, rec, dataset, sub_dataset, lookup, drop_log
            )
        else:
            datum = rec.get("datum", {})
            record_type = next(iter(datum), "")
            record_type_short = record_type.rsplit(".", 1)[-1]

            if record_type_short != "Event":
                drop_log.record_drop(
                    dataset, sub_dataset, DropReason.RECORD_IS_NOT_EVENT, # since we have the lookup tables
                    raw_event_type=record_type_short,
                )
                continue

            record_value = datum[record_type]

            # cdm20 has hostId as a top-level field outside datum
            host_id_outer = rec.get("hostId", "")

            result = dispatch_cdm_event(
                timestamp_ns, record_value, dataset, sub_dataset,
                lookup, drop_log, host_id_outer=host_id_outer,
            )

        if result is not None:
            drop_log.record_kept(dataset, sub_dataset)
            kept += 1
            yield result

    elapsed = time.time() - t0
    pct = f"{100*kept/seen:.1f}%" if seen > 0 else "n/a"
    logger.info(f"Pass 2 done: {kept}/{seen} kept ({pct}) in {elapsed:.1f}s")


def iterate_all_common_records(
    dataset: str,
    drop_log: Optional[DropLog] = None,
    cache_root: Optional[Path] = None,
    test_run_seconds: Optional[int] = None,
) -> Iterator[CommonRecord]:
    """Iterate all subdatasets in a dataset sequentially."""
    from provenance_explorer.registry.registry_all import get_big_registry

    if drop_log is None:
        drop_log = DropLog()

    big_registry = get_big_registry(dataset)
    for sub_dataset in big_registry:
        logger.info(f"Processing {dataset}/{sub_dataset}...")
        yield from iterate_common_records(
            dataset, sub_dataset,
            drop_log=drop_log,
            cache_root=cache_root,
            test_run_seconds=test_run_seconds,
        )
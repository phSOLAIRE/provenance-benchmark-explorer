"""
Per-attack-window coverage table.

One row per AttackWindow from provenance_explorer.registry.attack_data 

Per source the table reports a funnel as : 

L0  labelset_size        uuids considered for this (window, source)
L1  l1_in_lookup         L0 interestected with object_lookup (dataset, sub_dataset)
L2  l2_in_graph          L0  interestected with nodes present in the instance (any host/time)
L3a l3a_on_host_ever     L0 interestected with uuids ever on host
L3b l3b_on_host_in_inst  L0 interestected with uuids on host within padded instance range
L4  matched_<src>        L0 interestected with uuids on host within unpadded window

And saves excluded uuids with reasons to a parquet attack_window_exclusions.parquet
"""
from __future__ import annotations

import csv
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from provenance_explorer.common_record.object_lookup import ObjectLookup
from provenance_explorer.neo4j_graph import Neo4jInstanceManager
from provenance_explorer.neo4j_graph.annotator import (
    PM, FL, WW, RV,
    fetch_existing_uuids,
    fetch_host_anytime_uuids,
    fetch_window_active_uuids,
    load_label_file,
)
from provenance_explorer.neo4j_graph.instance_manager import parse_instance_name
from provenance_explorer.registry.attack_data import ATTACK_WINDOWS, AttackWindow
from provenance_explorer.registry.registry_all import DARPA_LABEL_PATH
from provenance_explorer.utils.time_conversion import date_string_to_ns_timestamp

logger = logging.getLogger(__name__)

ALL_SOURCES: Tuple[str, ...] = (PM, FL, WW, RV)

_EDT_OFFSET = timezone(timedelta(hours=-4))

_SEC_KEY_RE = re.compile(r"(\d+(?:\.\d+)*)")
_WW_SEC_RE = re.compile(r"_(\d+(?:\.\d+)*)(?=_|$|\s|;)")

_EXCLUSION_SAMPLE_CAP = 500

_ROLE_NAMES = {1: "FILE", 2: "SOCKET", 3: "PROCESS", 4: "EXECUTABLE"}


def _window_ns_range(w: AttackWindow) -> Tuple[int, int]:
    t_start = date_string_to_ns_timestamp(w.start_edt, tz=_EDT_OFFSET)
    t_end = date_string_to_ns_timestamp(w.end_edt, tz=_EDT_OFFSET)
    return t_start, t_end


def _section_key(report_sec: str) -> Optional[str]:
    m = _SEC_KEY_RE.match(report_sec.strip())
    return m.group(1) if m else None


def _load_wwtawwtal_by_section(path: Path) -> Dict[str, Set[str]]:
    """Parse a WWTAWWTAL labels CSV, grouping uuids by attack_chain section."""
    by_sec: Dict[str, Set[str]] = defaultdict(set)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        for row in reader:
            cleaned = {k.strip(): v.strip() for k, v in row.items()}
            uuid = cleaned.get("uuid", "").upper()
            chain = cleaned.get("attack_chain", "")
            if not uuid or not chain:
                continue
            for sec in _WW_SEC_RE.findall(chain):
                by_sec[sec].add(uuid)
    return by_sec


def _resolve_instance_path(
    manager: Neo4jInstanceManager,
    w: AttackWindow,
) -> Optional[Path]:
    """Return the instance whose UTC time range contains the unpadded window."""
    t_start_ns, t_end_ns = _window_ns_range(w)
    for inst in manager.list_instances():
        parsed = parse_instance_name(inst.name)
        if parsed is None:
            continue
        if (parsed.dataset == w.dataset
                and parsed.sub_dataset == w.subdataset
                and parsed.t_start_ns <= t_start_ns
                and parsed.t_end_ns >= t_end_ns):
            return inst.path
    return None


def _subdataset_source_files(
    windows: List[AttackWindow],
) -> Dict[str, Tuple[str, ...]]:
    """Union of label files referenced by any window in the subdataset, by source."""
    order: Dict[str, List[str]] = defaultdict(list)
    seen: Dict[str, Set[str]] = defaultdict(set)
    for w in windows:
        for src, paths in w.labels.items():
            for p in paths:
                if p not in seen[src]:
                    seen[src].add(p)
                    order[src].append(p)
    return {s: tuple(v) for s, v in order.items()}


def _load_label_sets(
    subdataset_sources: Dict[str, Tuple[str, ...]],
) -> Tuple[Dict[str, Set[str]], Dict[str, Dict[str, Set[str]]]]:
    """Load every referenced label file once (shared across windows of a subdataset)."""
    loaded_nodes: Dict[str, Set[str]] = {}
    loaded_ww_by_sec: Dict[str, Dict[str, Set[str]]] = {}
    for source, files in subdataset_sources.items():
        for rel in files:
            abs_path = DARPA_LABEL_PATH / rel
            if not abs_path.exists():
                logger.warning("label file missing: %s", abs_path)
                if source == WW:
                    loaded_ww_by_sec[rel] = {}
                else:
                    loaded_nodes[rel] = set()
                continue
            if source == WW:
                loaded_ww_by_sec[rel] = _load_wwtawwtal_by_section(abs_path)
            else:
                nodes, _edges = load_label_file(source, abs_path)
                loaded_nodes[rel] = nodes
    return loaded_nodes, loaded_ww_by_sec


@dataclass(frozen=True)
class _SourceSpec:
    source: str
    files: Tuple[str, ...]
    label_set: Set[str]
    authors_intended: bool


def _source_specs_for_window(
    w: AttackWindow,
    sources_filter: Tuple[str, ...],
    loaded_nodes: Dict[str, Set[str]],
    loaded_ww_by_sec: Dict[str, Dict[str, Set[str]]],
) -> List[_SourceSpec]:
    """
    Per-window label sets drawn from w.labels[source] only.
    """
    window_sec = _section_key(w.report_sec)
    specs: List[_SourceSpec] = []
    for source in sources_filter:
        files = tuple(w.labels.get(source, ()))
        if source == WW:
            uuids: Set[str] = set()
            if window_sec is not None:
                for rel in files:
                    uuids |= loaded_ww_by_sec.get(rel, {}).get(window_sec, set())
        else:
            uuids = set()
            for rel in files:
                uuids |= loaded_nodes.get(rel, set())
        specs.append(_SourceSpec(
            source=source,
            files=files,
            label_set=uuids,
            authors_intended=source in w.labels,
        ))
    return specs


def _empty_row(w: AttackWindow, reason: str) -> dict:
    t_start_ns, t_end_ns = _window_ns_range(w)
    return {
        "dataset": w.dataset,
        "subdataset": w.subdataset,
        "host": w.host,
        "host_uuid": w.host_uuid,
        "start_edt": w.start_edt,
        "end_edt": w.end_edt,
        "t_start_ns": t_start_ns,
        "t_end_ns": t_end_ns,
        "report_sec": w.report_sec,
        "descrpt": w.descrpt,
        "tactics": ",".join(w.tactics),
        "total_nodes": None,
        "local_base_rate": None,
        "instance": None,
        "skip_reason": reason,
    }


def _load_object_lookups(
    datasets_subs: Set[Tuple[str, str]],
) -> Dict[Tuple[str, str], Optional[ObjectLookup]]:
    cache: Dict[Tuple[str, str], Optional[ObjectLookup]] = {}
    for ds, sub in datasets_subs:
        try:
            cache[(ds, sub)] = ObjectLookup.load(ds, sub)
            if cache[(ds, sub)] is None:
                logger.warning("no object_lookup cached for %s/%s", ds, sub)
        except Exception as e:
            logger.warning("failed to load object_lookup for %s/%s: %s", ds, sub, e)
            cache[(ds, sub)] = None
    return cache


def build_attack_window_table(
    sources: Tuple[str, ...] = ALL_SOURCES,
    only_dataset: Optional[str] = None,
    only_subdataset: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build the per-attack-window coverage table and its exclusions.

    only_dataset    restricts to one benchmark ("e3", "e5", "optc").
    only_subdataset further restricts to a single sub-dataset name (e.g. "theia"); matched on AttackWindow.subdataset.

    Returns (windows_df, exclusions_df).
    """
    manager = Neo4jInstanceManager()

    windows = [
        w for w in ATTACK_WINDOWS
        if (only_dataset is None or w.dataset == only_dataset)
        and (only_subdataset is None or w.subdataset == only_subdataset)
    ]

    skipped_rows: List[dict] = []
    resolvable: List[AttackWindow] = []
    for w in windows:
        if not w.host_uuid:
            logger.warning("no host_uuid in registry: %s %s %s %s-%s",
                           w.dataset, w.subdataset, w.host, w.start_edt, w.end_edt)
            skipped_rows.append(_empty_row(w, "missing_host_uuid"))
        else:
            resolvable.append(w)

    by_instance: Dict[Path, List[AttackWindow]] = defaultdict(list)
    for w in resolvable:
        path = _resolve_instance_path(manager, w)
        if path is None:
            logger.warning("no matching instance: %s %s %s %s-%s",
                           w.dataset, w.subdataset, w.host, w.start_edt, w.end_edt)
            skipped_rows.append(_empty_row(w, "no_matching_instance"))
        else:
            by_instance[path].append(w)

    sub_groups: Dict[Tuple[str, str], List[AttackWindow]] = defaultdict(list)
    for w in resolvable:
        sub_groups[(w.dataset, w.subdataset)].append(w)

    source_files_by_sub = {
        key: {s: f for s, f in _subdataset_source_files(ws).items() if s in sources}
        for key, ws in sub_groups.items()
    }
    loaded_by_sub: Dict[Tuple[str, str], Tuple[Dict[str, Set[str]], Dict[str, Dict[str, Set[str]]]]] = {}
    for key, src_files in source_files_by_sub.items():
        loaded_by_sub[key] = _load_label_sets(src_files)

    obj_lookups = _load_object_lookups(set(sub_groups.keys()))

    rows: List[dict] = []
    exclusion_rows: List[dict] = []
    try:
        for inst_path, inst_windows in by_instance.items():
            parsed = parse_instance_name(inst_path.name)
            inst_t_start = parsed.t_start_ns if parsed else None
            inst_t_end = parsed.t_end_ns if parsed else None

            ds_sub = (inst_windows[0].dataset, inst_windows[0].subdataset)
            loaded_nodes, loaded_ww = loaded_by_sub[ds_sub]
            ol = obj_lookups.get(ds_sub)

            window_specs: Dict[int, List[_SourceSpec]] = {}
            instance_label_union: Set[str] = set()
            for w in inst_windows:
                specs = _source_specs_for_window(w, sources, loaded_nodes, loaded_ww)
                window_specs[id(w)] = specs
                for s in specs:
                    instance_label_union |= s.label_set

            logger.info("starting instance %s (%d window(s), %d label uuids)",
                        inst_path.name, len(inst_windows), len(instance_label_union))
            manager.start(inst_path)
            driver = manager.get_driver()
            try:
                existing_uuids = fetch_existing_uuids(driver, instance_label_union)
                logger.info("  L2 (in graph): %d / %d",
                            len(existing_uuids), len(instance_label_union))

                hosts_needed = {w.host_uuid for w in inst_windows if w.host_uuid}
                host_anytime: Dict[str, Set[str]] = {}
                host_instance: Dict[str, Set[str]] = {}
                for h in hosts_needed:
                    host_anytime[h] = fetch_host_anytime_uuids(driver, h)  # type: ignore
                    if inst_t_start is not None and inst_t_end is not None:
                        host_instance[h] = fetch_window_active_uuids(
                            driver, h, inst_t_start, inst_t_end)  # type: ignore
                    else:
                        host_instance[h] = set()

                for w in inst_windows:
                    t_start_ns, t_end_ns = _window_ns_range(w)
                    window_uuids = fetch_window_active_uuids(
                        driver, w.host_uuid, t_start_ns, t_end_ns,  # type: ignore
                    )
                    total = len(window_uuids)

                    specs = window_specs[id(w)]

                    matched_union: Set[str] = set()
                    row: dict = {
                        "dataset": w.dataset,
                        "subdataset": w.subdataset,
                        "host": w.host,
                        "host_uuid": w.host_uuid,
                        "start_edt": w.start_edt,
                        "end_edt": w.end_edt,
                        "t_start_ns": t_start_ns,
                        "t_end_ns": t_end_ns,
                        "inst_t_start_ns": inst_t_start,
                        "inst_t_end_ns": inst_t_end,
                        "report_sec": w.report_sec,
                        "descrpt": w.descrpt,
                        "tactics": ",".join(w.tactics),
                        "total_nodes": total,
                        "instance": inst_path.name,
                        "skip_reason": None,
                    }

                    for spec in specs:
                        L0 = spec.label_set
                        size_L0 = len(L0)
                        L1 = ol.filter_present(L0) if ol is not None else set()
                        L2 = L0 & existing_uuids
                        ha = host_anytime.get(w.host_uuid or "", set())
                        hi = host_instance.get(w.host_uuid or "", set())
                        L3a = L0 & ha
                        L3b = L0 & hi
                        L4 = L0 & window_uuids
                        matched_union |= L4

                        row[f"label_files_{spec.source}"] = ";".join(spec.files)
                        row[f"labelset_size_{spec.source}"] = size_L0
                        row[f"l1_{spec.source}"] = len(L1) if ol is not None else None
                        row[f"l2_{spec.source}"] = len(L2)
                        row[f"l3a_{spec.source}"] = len(L3a)
                        row[f"l3b_{spec.source}"] = len(L3b)
                        row[f"matched_{spec.source}"] = len(L4)
                        row[f"pct_of_labelset_{spec.source}"] = (
                            len(L4) / size_L0 if size_L0 else None
                        )
                        row[f"base_rate_{spec.source}"] = (
                            len(L4) / total if total else None
                        )
                        row[f"authors_intended_{spec.source}"] = spec.authors_intended

                        # Exclusions sidecar: L1 \ L2 = passes type filter but
                        # no node in graph (all its events were filtered out).
                        if ol is not None:
                            h3b_candidates = sorted(L1 - L2)[:_EXCLUSION_SAMPLE_CAP]
                            for u in h3b_candidates:
                                info = ol.get_str(u)
                                exclusion_rows.append({
                                    "dataset": w.dataset,
                                    "subdataset": w.subdataset,
                                    "host": w.host,
                                    "host_uuid": w.host_uuid,
                                    "report_sec": w.report_sec,
                                    "start_edt": w.start_edt,
                                    "source": spec.source,
                                    "bucket": "l1_not_in_graph",
                                    "uuid": u,
                                    "role": _ROLE_NAMES.get(info.role) if info else None,
                                    "types_raw": info.types_raw if info else None,
                                    "path": info.path if info else None,
                                    "cmdline": info.cmdline if info else None,
                                })

                    row["local_base_rate"] = (
                        len(matched_union) / total if total else None
                    )
                    rows.append(row)
                    logger.info(
                        "  %s %s | total=%d base_rate=%s",
                        w.start_edt, w.report_sec, total,
                        f"{row['local_base_rate']:.4f}" if row["local_base_rate"] is not None else "n/a",
                    )
            finally:
                try:
                    driver.close()
                finally:
                    manager.stop()
    except Exception:
        try:
            manager.stop()
        except Exception:
            pass
        raise
    finally:
        for ol in obj_lookups.values():
            if ol is not None:
                try:
                    ol.close()
                except Exception:
                    pass

    rows.extend(skipped_rows)
    return pd.DataFrame(rows), pd.DataFrame(exclusion_rows)

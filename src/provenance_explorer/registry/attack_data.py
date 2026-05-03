"""
- per-subdataset attack data
- flat ATTACK_WINDOWS list for per-window metrics

Each window carries its own labels dict {source: [rel_path, ...]} and here
ATTACK_DATA derives its subdataset-level label_files union from those per-window assignments

Usage::
    from provenance_explorer.registry.attack_data import ATTACK_DATA, ATTACK_WINDOWS
    entry = ATTACK_DATA[("e5", "cadets")]
    windows    = entry["windows"]      # {(start_edt_str, end_edt_str): {...}}
    label_set  = entry["label_files"]  # {PM: [...], FL: [...], ...}

    for w in ATTACK_WINDOWS:
        # w.dataset, w.subdataset, w.host, w.start_edt, w.end_edt, w.labels
        ...
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from provenance_explorer.registry.attack_registry_e3 import (
    e3_cadets_host,
    e3_clearscope_host,
    e3_fivedirections_host,
    e3_theia_host,
    e3_trace_host,
)
from provenance_explorer.registry.attack_registry_e5 import (
    e5_cadets_1,
    e5_cadets_2,
    e5_clearscope_1,
    e5_clearscope_2,
    e5_fivedirections_1,
    e5_fivedirections_2,
    e5_fivedirections_3,
    e5_marple_1,
    e5_theia_1,
    e5_trace_1,
    e5_trace_2,
)
from provenance_explorer.registry.attack_registry_optc import (
    optc_sysclient0051,
    optc_sysclient0201,
    optc_sysclient0501,
    optc_sysclient0974,
)

# Source identifiers (mirror neo4j_graph.annotator constants).
PM = "pidsmaker"
FL = "flash"
WW = "wwtawwtal"
RV = "revisiting_optc"


@dataclass(frozen=True)
class AttackWindow:
    """One attacker-active time window on one host."""
    dataset: str          # "e3" | "e5" | "optc"
    subdataset: str       # "cadets" | "trace" | ... | "aia_201_225" | ...
    host: str             # "cadets", "cadets_1", "sysclient0201", ...
    start_edt: str        # "YYYY-MM-DD HH:MM:SS" (EDT, UTC-4)
    end_edt: str
    report_sec: str
    descrpt: str
    tactics: Tuple[str, ...]
    # Host node uuid in the Neo4j graph; OpTC stores hostname strings here.
    # None = registry gap; downstream host-scoped queries will skip such windows.
    host_uuid: Optional[str] = None
    labels: Dict[str, Tuple[str, ...]] = field(default_factory=dict)


def _merge(*host_dicts: dict) -> dict:
    """Union per-host window dicts; keys are unique (start, end) tuples."""
    merged: dict = {}
    for d in host_dicts:
        merged.update(d)
    return merged

# for addressing hsots directly use (dataset, subdataset, host) -> per-host window dict
# Used to build ATTACK_WINDOWS and to derive subdataset-level label_files.
_HOST_REGISTRIES: List[Tuple[str, str, str, dict]] = [
    ("e3", "cadets", "cadets", e3_cadets_host),
    ("e3", "trace", "trace", e3_trace_host),
    ("e3", "theia", "theia", e3_theia_host),
    ("e3", "fivedirections", "fivedirections", e3_fivedirections_host),
    ("e3", "clearscope", "clearscope", e3_clearscope_host),
    ("e5", "cadets", "cadets_1", e5_cadets_1),
    ("e5", "cadets", "cadets_2", e5_cadets_2),
    ("e5", "trace", "trace_1", e5_trace_1),
    ("e5", "trace", "trace_2", e5_trace_2),
    ("e5", "theia", "theia_1", e5_theia_1),
    ("e5", "fivedirections", "fivedirections_1", e5_fivedirections_1),
    ("e5", "fivedirections", "fivedirections_2", e5_fivedirections_2),
    ("e5", "fivedirections", "fivedirections_3", e5_fivedirections_3),
    ("e5", "marple", "marple_1", e5_marple_1),
    ("e5", "clearscope", "clearscope_1", e5_clearscope_1),
    ("e5", "clearscope", "clearscope_2", e5_clearscope_2),
    ("optc", "aia_201_225", "sysclient0201", optc_sysclient0201),
    ("optc", "aia_501_525", "sysclient0501", optc_sysclient0501),
    ("optc", "aia_951_975", "sysclient0974", optc_sysclient0974),
    ("optc", "aia_51_75", "sysclient0051", optc_sysclient0051),
]


def _build_attack_windows() -> List[AttackWindow]:
    out: List[AttackWindow] = []
    for dataset, subdataset, host, reg in _HOST_REGISTRIES:
        for (start_edt, end_edt), entry in reg.items():
            labels = {
                src: tuple(paths)
                for src, paths in entry.get("labels", {}).items()
            }
            out.append(AttackWindow(
                dataset=dataset,
                subdataset=subdataset,
                host=host,
                start_edt=start_edt,
                end_edt=end_edt,
                report_sec=entry.get("report_sec", ""),
                descrpt=entry.get("descrpt", ""),
                tactics=tuple(entry.get("tactics", [])),
                host_uuid=entry.get("host_uuid"),
                labels=labels,
            ))
    return out


ATTACK_WINDOWS: List[AttackWindow] = _build_attack_windows()

def _label_files_union(*regs: dict) -> Dict[str, List[str]]:
    """Union per-window labels (across any number of per-host regs) into {source: [rel_path]}."""
    out: Dict[str, List[str]] = {}
    for reg in regs:
        for entry in reg.values():
            for src, paths in entry.get("labels", {}).items():
                bucket = out.setdefault(src, [])
                for p in paths:
                    if p not in bucket:
                        bucket.append(p)
    return out

# (dataset, subdataset) -> {"windows": {...}, "label_files": {...}}
ATTACK_DATA: Dict[Tuple[str, str], dict] = {
    ("e3", "cadets"): {
        "windows": _merge(e3_cadets_host),
        "label_files": _label_files_union(e3_cadets_host),
    },
    ("e3", "trace"): {
        "windows": _merge(e3_trace_host),
        "label_files": _label_files_union(e3_trace_host),
    },
    ("e3", "theia"): {
        "windows": _merge(e3_theia_host),
        "label_files": _label_files_union(e3_theia_host),
    },
    ("e3", "fivedirections"): {
        "windows": _merge(e3_fivedirections_host),
        "label_files": _label_files_union(e3_fivedirections_host),
    },
    ("e3", "clearscope"): {
        "windows": _merge(e3_clearscope_host),
        "label_files": _label_files_union(e3_clearscope_host),
    },
    ("e5", "cadets"): {
        "windows": _merge(e5_cadets_1, e5_cadets_2),
        "label_files": _label_files_union(e5_cadets_1, e5_cadets_2),
    },
    ("e5", "trace"): {
        "windows": _merge(e5_trace_1, e5_trace_2),
        "label_files": _label_files_union(e5_trace_1, e5_trace_2),
    },
    ("e5", "theia"): {
        "windows": _merge(e5_theia_1),
        "label_files": _label_files_union(e5_theia_1),
    },
    ("e5", "fivedirections"): {
        "windows": _merge(e5_fivedirections_1, e5_fivedirections_2, e5_fivedirections_3),
        "label_files": _label_files_union(e5_fivedirections_1, e5_fivedirections_2, e5_fivedirections_3),
    },
    ("e5", "clearscope"): {
        "windows": _merge(e5_clearscope_1, e5_clearscope_2),
        "label_files": _label_files_union(e5_clearscope_1, e5_clearscope_2),
    },
    ("e5", "marple"): {
        "windows": _merge(e5_marple_1),
        "label_files": _label_files_union(e5_marple_1),
    },
    ("optc", "aia_201_225"): {
        "windows": _merge(optc_sysclient0201),
        "label_files": _label_files_union(optc_sysclient0201),
    },
    ("optc", "aia_501_525"): {
        "windows": _merge(optc_sysclient0501),
        "label_files": _label_files_union(optc_sysclient0501),
    },
    ("optc", "aia_951_975"): {
        "windows": _merge(optc_sysclient0974),
        "label_files": _label_files_union(optc_sysclient0974),
    },
    ("optc", "aia_51_75"): {
        "windows": _merge(optc_sysclient0051),
        "label_files": _label_files_union(optc_sysclient0051),
    },
}


def get_attack_data(dataset: str, subdataset: str) -> dict | None:
    """Lookup helper; returns None if the subdataset is unknown."""
    return ATTACK_DATA.get((dataset, subdataset))

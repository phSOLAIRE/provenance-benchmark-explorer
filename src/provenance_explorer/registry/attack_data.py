"""
Per-subdataset attack data: merged time windows and label-file sets (including any label set taht might be plausible).

Time windows come from the per-host registries (attack_registry_{e3,e5,optc}.py) 
    - Window keys are (start_edt_str, end_edt_str) tuples; 
    - values inherit the per-host entry shape (descrpt, report_sec, tactics, ...).
    - Label files are attached at subdataset level

Usage::
    from provenance_explorer.registry.attack_data import ATTACK_DATA
    entry = ATTACK_DATA[("e5", "cadets")]
    windows    = entry["windows"]      # {(start_edt_str, end_edt_str): {...}}
    label_set  = entry["label_files"]  # {PM: [...], FL: [...], ...}
"""
from __future__ import annotations

from typing import Dict, Tuple

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


def _merge(*host_dicts: dict) -> dict:
    """Union per-host window dicts; keys are unique (start, end) tuples."""
    merged: dict = {}
    for d in host_dicts:
        merged.update(d)
    return merged


# Per-subdataset bullish label-file sets. Paths are relative to DARPA_LABEL_PATH.
# Annotator UNWIND-MATCHes by UUID, so unrelated files are no-ops.
_E3_LABELS: Dict[str, Dict[str, list[str]]] = {
    "cadets": {
        PM: [
            "pidsmaker/node_Nginx_Backdoor_06.csv",
            "pidsmaker/node_Nginx_Backdoor_11.csv",
            "pidsmaker/node_Nginx_Backdoor_12.csv",
            "pidsmaker/node_Nginx_Backdoor_13.csv",
        ],
        FL: ["flash/cadets.json"],
        WW: ["wwtawwtal/cadets_labels.csv",] # "wwtawwtal/cadets_edge_labels.csv"],
    },
    "trace": {
        PM: [
            "pidsmaker/node_trace_e3_firefox_0410.csv",
            "pidsmaker/node_trace_e3_phishing_executable_0413.csv",
            "pidsmaker/node_trace_e3_pine_0413.csv",
        ],
        FL: ["flash/trace.json"],
        WW: ["wwtawwtal/trace_labels.csv"],
    },
    "theia": {
        PM: [
            "pidsmaker/node_Firefox_Backdoor_Drakon_In_Memory.csv",
            "pidsmaker/node_Browser_Extension_Drakon_Dropper.csv",
        ],
        FL: ["flash/theia.json"],
        WW: ["wwtawwtal/theia_labels.csv", ] # "wwtawwtal/theia_edge_labels.csv"],
    },
    "fivedirections": {
        PM: [
            "pidsmaker/node_fivedirections_e3_browser_0412.csv",
            "pidsmaker/node_fivedirections_e3_excel_0409.csv",
            "pidsmaker/node_fivedirections_e3_firefox_0411.csv",
        ],
        FL: ["flash/fivedirections.json"],
        WW: [
            "wwtawwtal/fivedirections_labels.csv",
            # "wwtawwtal/fivedirections_edge_labels.csv",
        ],
    },
    "clearscope": {
        PM: [
            "pidsmaker/node_clearscope_e3_firefox_0411.csv",
            "pidsmaker/node_clearscope_e3_firefox_0412.csv",
        ],
    },
}

_E5_LABELS: Dict[str, Dict[str, list[str]]] = {
    "cadets": {
        PM: [
            "pidsmaker/node_Nginx_Drakon_APT.csv",
            "pidsmaker/node_Nginx_Drakon_APT_17.csv",
        ],
    },
    "trace": {
        PM: ["pidsmaker/node_Trace_Firefox_Drakon.csv"],
    },
    "theia": {
        PM: ["pidsmaker/node_THEIA_1_Firefox_Drakon_APT_BinFmt_Elevate_Inject.csv"],
    },
    "fivedirections": {
        PM: [
            "pidsmaker/node_fivedirections_e5_bits_0515.csv",
            "pidsmaker/node_fivedirections_e5_copykatz_0509.csv",
            "pidsmaker/node_fivedirections_e5_dns_0517.csv",
            "pidsmaker/node_fivedirections_e5_drakon_0517.csv",
        ],
    },
    "clearscope": {
        PM: [
            "pidsmaker/node_clearscope_e5_appstarter_0515.csv",
            "pidsmaker/node_clearscope_e5_firefox_0517.csv",
            "pidsmaker/node_clearscope_e5_lockwatch_0517.csv",
            "pidsmaker/node_clearscope_e5_tester_0517.csv",
        ],
    },
    "marple": {},  # no published labels
}

# OpTC subdatasets get bullish set: per-host PIDSMaker files plus Flash and Revisiting OpTC label sets
_OPTC_LABELS_ALL: Dict[str, list[str]] = {
    PM: [
        "pidsmaker/node_h051_0925.csv",
        "pidsmaker/node_h201_0923.csv",
        "pidsmaker/node_h501_0924.csv",
    ],
    FL: ["flash/optc.txt"],
    RV: ["revisiting_optc/malicious.json"],
}

# (dataset, subdataset) -> {"windows": {...}, "label_files": {...}}
ATTACK_DATA: Dict[Tuple[str, str], dict] = {
    ("e3", "cadets"): {
        "windows": _merge(e3_cadets_host),
        "label_files": _E3_LABELS["cadets"],
    },
    ("e3", "trace"): {
        "windows": _merge(e3_trace_host),
        "label_files": _E3_LABELS["trace"],
    },
    ("e3", "theia"): {
        "windows": _merge(e3_theia_host),
        "label_files": _E3_LABELS["theia"],
    },
    ("e3", "fivedirections"): {
        "windows": _merge(e3_fivedirections_host),
        "label_files": _E3_LABELS["fivedirections"],
    },
    ("e3", "clearscope"): {
        "windows": _merge(e3_clearscope_host),
        "label_files": _E3_LABELS["clearscope"],
    },
    ("e5", "cadets"): {
        "windows": _merge(e5_cadets_1, e5_cadets_2),
        "label_files": _E5_LABELS["cadets"],
    },
    ("e5", "trace"): {
        "windows": _merge(e5_trace_1, e5_trace_2),
        "label_files": _E5_LABELS["trace"],
    },
    ("e5", "theia"): {
        "windows": _merge(e5_theia_1),
        "label_files": _E5_LABELS["theia"],
    },
    ("e5", "fivedirections"): {
        "windows": _merge(e5_fivedirections_1, e5_fivedirections_2, e5_fivedirections_3),
        "label_files": _E5_LABELS["fivedirections"],
    },
    ("e5", "clearscope"): {
        "windows": _merge(e5_clearscope_1, e5_clearscope_2),
        "label_files": _E5_LABELS["clearscope"],
    },
    ("e5", "marple"): {
        "windows": _merge(e5_marple_1),
        "label_files": _E5_LABELS["marple"],
    },
    ("optc", "aia_201_225"): {
        "windows": _merge(optc_sysclient0201),
        "label_files": _OPTC_LABELS_ALL,
    },
    ("optc", "aia_501_525"): {
        "windows": _merge(optc_sysclient0501),
        "label_files": _OPTC_LABELS_ALL,
    },
    ("optc", "aia_951_975"): {
        "windows": _merge(optc_sysclient0974),
        "label_files": _OPTC_LABELS_ALL,
    },
    ("optc", "aia_51_75"): {
        "windows": _merge(optc_sysclient0051),
        "label_files": _OPTC_LABELS_ALL,
    },
}


def get_attack_data(dataset: str, subdataset: str) -> dict | None:
    """Lookup helper; returns None if the subdataset is unknown."""
    return ATTACK_DATA.get((dataset, subdataset))

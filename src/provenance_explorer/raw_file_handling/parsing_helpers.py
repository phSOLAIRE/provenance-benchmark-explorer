"""
Per-dataset functions for:
- timestamp extraction returns nanoseconds (int) or None.
    ts_<engagement>_<subdataset>(line) -> int | None
- record parsing are only wrappers around json.loads, supposed to be adjustible in future
    parse_<engagement>_<subdataset>(line) -> dict | None

for easier loop access contains
PARSERS and TS_EXTRACTORS: dict[tuple[str, str], FunctionType]
with
(<engagement>,<sub dataset>): <function>
"""
from __future__ import annotations

import re
import json
import logging
from datetime import datetime, timezone
from types import FunctionType
from typing import Optional

logger = logging.getLogger(__name__)

# Internal helpers — timestamp extraction (string-search based)
# CDM Event records contain "timestampNanos":<integer>.
_CDM_TS_KEY = '"timestampNanos":'
_CDM_TS_KEY_LEN = len(_CDM_TS_KEY)
_TS_RE = re.compile(r"\d+")

def _ts_from_cdm_line_fast(line: str) -> Optional[int]:
    idx = line.find(_CDM_TS_KEY)
    if idx < 0:
        return None

    start = idx + _CDM_TS_KEY_LEN
    if start >= len(line):
        return None

    ch = line[start]

    if ch.isdigit():
        m = _TS_RE.match(line, start)
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                return None
        return None

    elif ch == "n":
        return None

    return None

# OpTC records e..g "timestamp":"2019-09-16T19:32:05.999-04:00"
_OPTC_TS_KEY = '"timestamp":"'
_OPTC_TS_KEY_LEN = len(_OPTC_TS_KEY)

def _ts_from_optc_line_fast(line: str) -> Optional[int]:
    """
    Extract timestamp from an OpTC JSON line using string search.
    Finds the ISO 8601 string and converts to nanoseconds since epoch.
    called fast, because no json is loaded, speedup is ~10x over json load.
    """
    idx = line.find(_OPTC_TS_KEY)
    if idx < 0:
        return None
    start = idx + _OPTC_TS_KEY_LEN
    end = line.find('"', start)
    if end < 0:
        return None
    iso_str = line[start:end]
    try:
        return _iso_to_ns(iso_str)
    except (ValueError, TypeError, OverflowError) as exc:
        logger.debug("OpTC timestamp parse failed for %r: %s", iso_str, exc)
        return None

def _iso_to_ns(iso_str: str) -> int:
    """
    Convert an ISO 8601 timestamp string to nanoseconds since epoch.
    Uses integer arithmetic to avoid float precision loss.
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = dt - epoch
    return (
        (delta.days * 86400 + delta.seconds) * 1_000_000_000
        + delta.microseconds * 1_000
    )


# Internal helpers
def _parse_cdm_line(line: str) -> Optional[dict]:
    """Parse a CDM JSON line into a dict, robust to trailing comma"""
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.endswith(","):
        stripped = stripped[:-1]
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

def _parse_optc_line(line: str) -> Optional[dict]:
    """Parse an OpTC JSON line into a dict."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

# E3 — Cadets  (CDM v18, FreeBSD/DTrace)
def ts_e3_cadets(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e3_cadets(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)


# E3 — Clearscope  (CDM v18, Android/Java)
def ts_e3_clearscope(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e3_clearscope(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)


# E3 — FiveDirections  (CDM v18, Windows)
def ts_e3_fivedirections(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e3_fivedirections(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E3 — Theia  (CDM v18, Linux)
def ts_e3_theia(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e3_theia(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E3 — Trace  (CDM v18, Linux trace)
def ts_e3_trace(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e3_trace(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E5 — Cadets  (CDM v20, FreeBSD/DTrace)
def ts_e5_cadets(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e5_cadets(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E5 — Clearscope  (CDM v20, Android/Java)
def ts_e5_clearscope(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e5_clearscope(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E5 — FiveDirections  (CDM v20, Windows)
def ts_e5_fivedirections(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e5_fivedirections(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E5 — Marple  (CDM v20, Windows)
def ts_e5_marple(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e5_marple(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E5 — Theia  (CDM v20, Linux)
def ts_e5_theia(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e5_theia(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# E5 — Trace  (CDM v20, Linux syscall)
def ts_e5_trace(line: str) -> Optional[int]:
    return _ts_from_cdm_line_fast(line)

def parse_e5_trace(line: str) -> Optional[dict]:
    return _parse_cdm_line(line)

# OpTC — All sub-datasets  (flat JSON, ISO 8601 timestamps)
def ts_optc(line: str) -> Optional[int]:
    """Extract nanosecond timestamp from an OpTC line (ISO 8601 string)."""
    return _ts_from_optc_line_fast(line)

def parse_optc(line: str) -> Optional[dict]:
    """Parse an OpTC line into a dict."""
    return _parse_optc_line(line)

# only aliases; E3 and E5 have more quirks than OpTC 
ts_optc_aia_51_75 = ts_optc
parse_optc_aia_51_75 = parse_optc

ts_optc_aia_201_225 = ts_optc
parse_optc_aia_201_225 = parse_optc

ts_optc_aia_501_525 = ts_optc
parse_optc_aia_501_525 = parse_optc

ts_optc_aia_951_975 = ts_optc
parse_optc_aia_951_975 = parse_optc


# tables for loop access
TS_EXTRACTORS: dict[tuple[str, str], FunctionType] = {
    ("e3", "cadets"):          ts_e3_cadets,
    ("e3", "clearscope"):      ts_e3_clearscope,
    ("e3", "fivedirections"):  ts_e3_fivedirections,
    ("e3", "theia"):           ts_e3_theia,
    ("e3", "trace"):           ts_e3_trace,
    ("e5", "cadets"):          ts_e5_cadets,
    ("e5", "clearscope"):      ts_e5_clearscope,
    ("e5", "fivedirections"):  ts_e5_fivedirections,
    ("e5", "marple"):          ts_e5_marple,
    ("e5", "theia"):           ts_e5_theia,
    ("e5", "trace"):           ts_e5_trace,
    ("optc", "aia_51_75"):     ts_optc_aia_51_75,
    ("optc", "aia_201_225"):   ts_optc_aia_201_225,
    ("optc", "aia_501_525"):   ts_optc_aia_501_525,
    ("optc", "aia_951_975"):   ts_optc_aia_951_975,
}

PARSERS: dict[tuple[str, str], FunctionType] = {
    ("e3", "cadets"):          parse_e3_cadets,
    ("e3", "clearscope"):      parse_e3_clearscope,
    ("e3", "fivedirections"):  parse_e3_fivedirections,
    ("e3", "theia"):           parse_e3_theia,
    ("e3", "trace"):           parse_e3_trace,
    ("e5", "cadets"):          parse_e5_cadets,
    ("e5", "clearscope"):      parse_e5_clearscope,
    ("e5", "fivedirections"):  parse_e5_fivedirections,
    ("e5", "marple"):          parse_e5_marple,
    ("e5", "theia"):           parse_e5_theia,
    ("e5", "trace"):           parse_e5_trace,
    ("optc", "aia_51_75"):     parse_optc_aia_51_75,
    ("optc", "aia_201_225"):   parse_optc_aia_201_225,
    ("optc", "aia_501_525"):   parse_optc_aia_501_525,
    ("optc", "aia_951_975"):   parse_optc_aia_951_975,
}

# other helpers 
def get_ts_extractor(dataset: str, sub_dataset: str):
    """Look up the timestamp extractor for a dataset+sub_dataset pair."""
    key = (dataset.lower(), sub_dataset.lower())
    if key not in TS_EXTRACTORS:
        raise KeyError(
            f"No timestamp extractor registered for {key}. "
            f"Known: {sorted(TS_EXTRACTORS.keys())}"
        )
    return TS_EXTRACTORS[key]

def get_parser(dataset: str, sub_dataset: str):
    """Look up the record parser for a dataset+sub_dataset pair."""
    key = (dataset.lower(), sub_dataset.lower())
    if key not in PARSERS:
        raise KeyError(
            f"No parser registered for {key}. "
            f"Known: {sorted(PARSERS.keys())}"
        )
    return PARSERS[key]
"""
FILE ANNOTATIONS
These functions are used to extract start / end timestamps, size of files and other useful metadata.
Mainly these functions are helpful for building the registry data structures for the individual datasets.

function for specific file: extract_file_metadata(<path>)
function for list of all files in dataset: build_file_registry(<dataset>, <sub dataset>)
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta

from provenance_explorer.registry.repo_paths import DATA_RAW

# -- Constants --
# Known CDM event keys (fully qualified).
# FiveDirections E3 file 1 uses short keys like "Event" handled separately; otherwise these apply
CDM18_EVENT_KEY = "com.bbn.tc.schema.avro.cdm18.Event"
CDM20_EVENT_KEY = "com.bbn.tc.schema.avro.cdm20.Event"
FULLY_QUALIFIED_EVENT_KEYS = [CDM18_EVENT_KEY, CDM20_EVENT_KEY]
SHORT_EVENT_KEY = "Event"

NS_PER_SEC = 1_000_000_000
EARLIEST_TOLERATED_NS_TS = int(datetime.fromisoformat("2015-01-01").timestamp()) * NS_PER_SEC

N_SAMPLE_LINES = 100
N_EXTENDED_SEARCH_LINES = 1_000_000  # for finding first/last timestamp when head/tail have none; happens every now and then
TAIL_CHUNK_SIZE = 1024 * 1024


# -- Timestamp representation types --
# The raw timestampNanos field can appear as:
#   - int   (correct):   1523586247675522567
#   - float (lossy):     1.52358624767e+18  (json parsed large number)
#   - None  (missing)
#
# OpTC uses ISO 8601 strings at a different lcoation, always correct.
#
# 1. detect the representation from the first few samples, 
# 2. then normalize all timestamps to int nanoseconds using the detected representation
# (for metadata, raw files are not changed in this repo)
def _classify_ts_representation(raw_value) -> str:
    """
    Classify a single raw timestampNanos value. 
    Returns 'int_nanos', 'float_nanos', or 'unknown'.
    """
    if isinstance(raw_value, int):
        return "int_nanos"
    elif isinstance(raw_value, float):
        return "float_nanos"
    else:
        return "unknown"

def _normalize_ts_to_nanos(raw_value, representation: str) -> Optional[int]:
    """
    Convert a raw timestamp value to integer nanoseconds.
    """
    if raw_value is None:
        return None
    if representation in ("int_nanos", "float_nanos"):
        return int(raw_value)
    else:
        return int(raw_value)
        #except (TypeError, ValueError):
        #    return None


# -- helpers --
def _try_parse_line(raw: str):
    """
    Try to parse a JSONL line, with trailing-comma fallback.
    Returns (parsed_dict, needed_comma_strip): tuple[dict|None, bool].
    """
    line = raw.strip()
    if not line:
        return None, False
    try:
        return json.loads(line), False
    except json.JSONDecodeError:
        pass
    # trailing comma fallback
    if line.endswith(","):
        try:
            return json.loads(line[:-1]), True
        except json.JSONDecodeError:
            pass
    return None, False

def _extract_raw_event_timestamp(record: dict, dataset_kind: str):
    """
    Extract the raw timestamp value from an event record.
    For E3/E5: returns the raw value of timestampNanos (may be int or float).
    For OpTC: returns the ISO 8601 string.
    Returns None if the record has no event timestamp.
    """
    if record is None:
        return None
    if dataset_kind == "optc":
        return record.get("timestamp")
    else:
        datum = record.get("datum", {})
        # Try fully-qualified keys first
        for key in FULLY_QUALIFIED_EVENT_KEYS:
            evt = datum.get(key)
            if evt is not None and "timestampNanos" in evt:
                return evt["timestampNanos"]
        # Try short key; see FiveDirections fuckup
        evt = datum.get(SHORT_EVENT_KEY)
        if evt is not None and "timestampNanos" in evt:
            return evt["timestampNanos"]
        return None

def _raw_ts_to_nanos(raw_value, dataset_kind: str, ts_representation: str) -> Optional[int]:
    """
    Convert a raw timestamp to integer nanoseconds.
    acts accordingly, based on dataset kind and detected representation.
    """
    if raw_value is None:
        return None
    if dataset_kind == "optc":
        if isinstance(raw_value, str):
            return _iso8601_to_nanos(raw_value)
        return None
    else:
        return _normalize_ts_to_nanos(raw_value, ts_representation)


def _iso8601_to_nanos(ts_str: str) -> int:
    """
    Parse ISO 8601 timestamp string to epoch nanoseconds.
    Handles formats like '2019-09-18T20:19:41.611-04:00'.
    Uses integer arithmetic to avoid float precision loss.
    """
    import re

    # Split off timezone offset
    m = re.match(r"(.+?)([+-]\d{2}:\d{2})$", ts_str)
    if not m:
        raise ValueError(f"Cannot parse timezone from: {ts_str}")

    dt_part, tz_part = m.group(1), m.group(2)

    # Parse timezone offset
    tz_sign = 1 if tz_part[0] == "+" else -1
    tz_hours, tz_minutes = int(tz_part[1:3]), int(tz_part[4:6])
    tz = timezone(timedelta(hours=tz_sign * tz_hours, minutes=tz_sign * tz_minutes))

    # Split fractional seconds and parse base datetime
    if "." in dt_part:
        main, frac = dt_part.split(".")
        frac_ns = int(frac.ljust(9, "0")[:9])
    else:
        main = dt_part
        frac_ns = 0

    dt = datetime.strptime(main, "%Y-%m-%dT%H:%M:%S")
    dt = dt.replace(tzinfo=tz)

    epoch_s = int(dt.replace(microsecond=0).timestamp())
    return epoch_s * NS_PER_SEC + frac_ns


def _detect_dataset_kind(rel_path: str) -> str:
    """Determine dataset kind from relative path. Returns 'e3', 'e5', or 'optc'."""
    if rel_path.startswith("Engagement3"):
        return "e3"
    elif rel_path.startswith("Engagement5"):
        return "e5"
    elif rel_path.startswith("OpTC"):
        return "optc"
    else:
        raise ValueError(f"Unknown dataset kind for path: {rel_path}")

def _detect_source_tag(rel_path: str) -> str:
    """Extract the sub-dataset name from relative path."""
    parts = Path(rel_path).parts
    if parts[0] in ("Engagement3", "Engagement5"):
        return parts[1]
    elif parts[0] == "OpTC":
        for p in parts:
            if p.startswith("AIA-"):
                return p
        return parts[2] if len(parts) > 2 else parts[1] # type: ignore
    return parts[1] if len(parts) > 1 else parts[0] # type: ignore

def _read_head_lines(file_path: Path, n: int) -> list[str]:
    """Read first n non-empty lines from file."""
    lines = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)
                if len(lines) >= n:
                    break
    return lines

def _read_tail_lines(file_path: Path, n: int) -> list[str]:
    """Read last n non-empty lines from file by reading from the end in chunks."""
    lines = []
    with open(file_path, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        buffer = b""

        while pos > 0 and len(lines) < n:
            read_size = min(TAIL_CHUNK_SIZE, pos)
            pos -= read_size
            f.seek(pos)
            buffer = f.read(read_size) + buffer

            split = buffer.split(b"\n")
            buffer = split[0]
            complete = split[1:]

            for raw in reversed(complete):
                raw = raw.strip()
                if raw:
                    lines.append(raw.decode("utf-8", errors="replace"))
                    if len(lines) >= n:
                        break

        if len(lines) < n and buffer.strip():
            lines.append(buffer.strip().decode("utf-8", errors="replace"))

    lines.reverse()
    return lines

def _check_uuid_case(records: list[dict], dataset_kind: str) -> str:
    """Check UUID casing across sampled records. Returns 'lower', 'upper', or 'mixed'."""
    import re
    uuid_pattern = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

    has_lower = False
    has_upper = False

    def scan_value(v):
        nonlocal has_lower, has_upper
        if isinstance(v, str):
            for m in uuid_pattern.finditer(v):
                uid = m.group()
                hex_chars = uid.replace("-", "")
                alpha_chars = [c for c in hex_chars if c.isalpha()]
                if alpha_chars:
                    if all(c.islower() for c in alpha_chars):
                        has_lower = True
                    elif all(c.isupper() for c in alpha_chars):
                        has_upper = True
                    else:
                        has_lower = True
                        has_upper = True
        elif isinstance(v, dict):
            for val in v.values():
                scan_value(val)
                if has_lower and has_upper:
                    return
        elif isinstance(v, list):
            for val in v:
                scan_value(val)
                if has_lower and has_upper:
                    return

    for rec in records:
        scan_value(rec)
        if has_lower and has_upper:
            return "mixed"

    if has_lower and has_upper:
        return "mixed"
    elif has_lower:
        return "lower"
    elif has_upper:
        return "upper"
    else:
        return "no_alpha_hex"

def _extract_wrapper_style(record: dict, dataset_kind: str) -> str:
    """Characterize the top-level JSON wrapper structure."""
    keys = sorted(record.keys())
    return "+".join(keys)

def _extract_cdm_version(record: dict) -> Optional[str]:
    """Extract CDM version string from a record, or None for OpTC."""
    return record.get("CDMVersion")

def _extract_source_field(records: list[dict], dataset_kind: str) -> Optional[str]:
    """Extract the source field value. Returns the value if consistent across samples, else 'mixed:<values>'."""
    sources = set()
    for rec in records:
        if dataset_kind == "optc":
            return None
        src = rec.get("source")
        if src:
            sources.add(src)
    if len(sources) == 0:
        return None
    elif len(sources) == 1:
        return sources.pop()
    else:
        return "mixed:" + ",".join(sorted(sources))

def _check_ordering(timestamps: list[int]) -> tuple[bool, int]:
    """
    Check if timestamps are approximately ordered.
    Returns (is_ordered, max_backward_jump_ns).
    is_ordered is True if no backward jump exceeds 10 seconds.
    """
    if len(timestamps) < 2:
        return True, 0
    max_backward = 0
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i - 1]
        if diff < 0:
            max_backward = max(max_backward, -diff)
    return max_backward <= 10 * NS_PER_SEC, max_backward

def _infer_timestamp_resolution(timestamps_ns: list[int], dataset_kind: str) -> str:
    """
    Infer the effective timestamp resolution from normalized nanosecond timestamps.
    Returns 'nanoseconds', 'microseconds', 'milliseconds', or 'seconds'.
    """
    if not timestamps_ns:
        return "unknown"

    remainders_us = [t % 1000 for t in timestamps_ns]
    remainders_ms = [t % 1_000_000 for t in timestamps_ns]
    remainders_s = [t % NS_PER_SEC for t in timestamps_ns]

    if any(r != 0 for r in remainders_us):
        return "nanoseconds"
    elif any(r != 0 for r in remainders_ms):
        return "microseconds"
    elif any(r != 0 for r in remainders_s):
        return "milliseconds"
    else:
        return "seconds"

def _extract_sequence_range(records: list[dict], dataset_kind: str) -> Optional[tuple[int, int]]:
    """Extract min/max sequence numbers from sampled records."""
    if dataset_kind == "optc":
        return None

    seqs = []
    for rec in records:
        datum = rec.get("datum", {})
        for key in FULLY_QUALIFIED_EVENT_KEYS + [SHORT_EVENT_KEY]:
            evt = datum.get(key)
            if evt and "sequence" in evt:
                seq_val = evt["sequence"]
                if isinstance(seq_val, dict):
                    seq_val = seq_val.get("long", seq_val.get("int"))
                if seq_val is not None:
                    seqs.append(int(seq_val))
    if not seqs:
        return None
    return min(seqs), max(seqs)


def _detect_ts_representation(records: list[dict], dataset_kind: str) -> str:
    """
    Detect the timestamp representation used in a set of records.
    Scans records for the first event with a timestampNanos value and
    classifies it. Returns 'int_nanos', 'float_nanos', 'iso8601', or 'none'.
    """
    if dataset_kind == "optc":
        return "iso8601"
    
    for rec in records:
        raw = _extract_raw_event_timestamp(rec, dataset_kind)
        if raw is not None:
            return _classify_ts_representation(raw)
    return "none"


def _search_first_event_ts(file_path: Path, dataset_kind: str, ts_repr: str, n_lines: int) -> Optional[int]:
    """
    Scan forward from file start for the first event timestamp.
    Reads up to n_lines. Returns normalized nanoseconds or None.
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        count = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            count += 1
            if count > n_lines:
                break
            rec, _ = _try_parse_line(line)
            if rec is None:
                continue
            raw = _extract_raw_event_timestamp(rec, dataset_kind)
            ts = _raw_ts_to_nanos(raw, dataset_kind, ts_repr)
            if ts is not None:
                return ts
    return None

def _search_last_event_ts(file_path: Path, dataset_kind: str, ts_repr: str,n_lines: int) -> Optional[int]:
    """Scan backward from file end for the last event timestamp.
    Reads up to n_lines from the tail. Returns normalized nanoseconds or None.
    """
    tail = _read_tail_lines(file_path, n_lines)
    for raw_line in reversed(tail):
        rec, _ = _try_parse_line(raw_line)
        if rec is None:
            continue
        raw = _extract_raw_event_timestamp(rec, dataset_kind)
        ts = _raw_ts_to_nanos(raw, dataset_kind, ts_repr)
        if ts is not None:
            return ts
    return None

def _search_first_realistic_ts(file_path: Path, dataset_kind: str, ts_repr: str) -> Optional[int]:
    """Scan forward for the first event timestamp >= EARLIEST_TOLERATED_NS_TS."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        count = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            count += 1
            if count > N_EXTENDED_SEARCH_LINES:
                break
            rec, _ = _try_parse_line(line)
            if rec is None:
                continue
            raw = _extract_raw_event_timestamp(rec, dataset_kind)
            ts = _raw_ts_to_nanos(raw, dataset_kind, ts_repr)
            if ts is not None and ts >= EARLIEST_TOLERATED_NS_TS:
                return ts
    return None

# -- Main extraction function --
def extract_file_metadata(file_path: Path) -> dict:
    """
    Extract metadata from a single dataset json/jsonl file.

    Reads only head and tail samples (N_SAMPLE_LINES each), with extended
    search (N_EXTENDED_SEARCH_LINES) if no event timestamp is found in the
    initial samples.
    
    All timestamps in the returned dict are normalized to integer nanoseconds, regardless of whether the source file stores them as int, float, or ISO string.
    args: 
        file_path : Absolute path to the JSONL file as Path object.

    Returns dict with keys:
        path, file_size_bytes,
        dataset_kind, source_tag,
        first_timestamp_ns, last_timestamp_ns,
        first_realistic_ts_ns,
        first_timestamp_iso, last_timestamp_iso, 
        first_realistic_ts_iso,
        timestamp_format, timestamp_resolution, ts_raw_representation,
        cdm_version, wrapper_style, source_field,
        uuid_case, likely_ordered, max_backward_jump_ns,
        seq_min, seq_max,
        trailing_comma_observed,
    """
    rel_path = str(file_path.relative_to(DATA_RAW))
    dataset_kind = _detect_dataset_kind(rel_path)
    source_tag = _detect_source_tag(rel_path)
    file_size = file_path.stat().st_size

    # - 1: Read head/tail samples, parse records -
    head_raw = _read_head_lines(file_path, N_SAMPLE_LINES)
    tail_raw = _read_tail_lines(file_path, N_SAMPLE_LINES)

    head_records = []
    tail_records = []
    trailing_comma_observed = False

    for line in head_raw:
        rec, needed_strip = _try_parse_line(line)
        if needed_strip:
            trailing_comma_observed = True
        if rec is not None:
            head_records.append(rec)

    for line in tail_raw:
        rec, needed_strip = _try_parse_line(line)
        if needed_strip:
            trailing_comma_observed = True
        if rec is not None:
            tail_records.append(rec)

    all_records = head_records + tail_records

    # - 2: Detect timestamp representation -
    ts_repr = _detect_ts_representation(all_records, dataset_kind)

    # If no events in head+tail samples, try extended search just for representation
    if ts_repr == "none":
        print(f"  No events in head/tail samples, extending search for: {rel_path}", file=sys.stderr)
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            count = 0
            for line in f:
                line = line.strip()
                if not line:
                    continue
                count += 1
                if count > N_EXTENDED_SEARCH_LINES:
                    break
                rec, _ = _try_parse_line(line)
                if rec is None:
                    continue
                raw = _extract_raw_event_timestamp(rec, dataset_kind)
                if raw is not None:
                    ts_repr = _classify_ts_representation(raw) if dataset_kind != "optc" else "iso8601"
                    break

    # - 3: Extract timestamps -
    # First timestamp: scan head records, then extended if needed
    first_ts = None
    for rec in head_records:
        raw = _extract_raw_event_timestamp(rec, dataset_kind)
        ts = _raw_ts_to_nanos(raw, dataset_kind, ts_repr)
        if ts is not None:
            first_ts = ts
            break

    if first_ts is None:
        print(f"  No event ts in first {N_SAMPLE_LINES} lines, extending for: {rel_path}", file=sys.stderr)
        first_ts = _search_first_event_ts(file_path, dataset_kind, ts_repr, N_EXTENDED_SEARCH_LINES)
        if first_ts is None:
            print(f"  No event ts found in first {N_EXTENDED_SEARCH_LINES} lines.", file=sys.stderr)

    # Last timestamp: scan tail records, then extended if needed
    last_ts = None
    for rec in reversed(tail_records):
        raw = _extract_raw_event_timestamp(rec, dataset_kind)
        ts = _raw_ts_to_nanos(raw, dataset_kind, ts_repr)
        if ts is not None:
            last_ts = ts
            break

    if last_ts is None:
        last_ts = _search_last_event_ts(file_path, dataset_kind, ts_repr, N_EXTENDED_SEARCH_LINES)

    # First realistic timestamp: skip bogus early timestamps
    first_realistic_ts = None
    if first_ts is not None and first_ts < EARLIEST_TOLERATED_NS_TS:
        print(f"  First ts {first_ts} is pre-2015, searching for realistic start: {rel_path}", file=sys.stderr)
        first_realistic_ts = _search_first_realistic_ts(file_path, dataset_kind, ts_repr)
        if first_realistic_ts is None:
            print(f"  Could not find realistic ts within {N_EXTENDED_SEARCH_LINES} lines.", file=sys.stderr)
    else:
        first_realistic_ts = first_ts

    # - 4: Collect sample timestamps for ordering+resolution 
    head_timestamps = []
    for rec in head_records:
        raw = _extract_raw_event_timestamp(rec, dataset_kind)
        ts = _raw_ts_to_nanos(raw, dataset_kind, ts_repr)
        if ts is not None:
            head_timestamps.append(ts)

    tail_timestamps = []
    for rec in reversed(tail_records):
        raw = _extract_raw_event_timestamp(rec, dataset_kind)
        ts = _raw_ts_to_nanos(raw, dataset_kind, ts_repr)
        if ts is not None:
            tail_timestamps.append(ts)
    tail_timestamps.reverse()

    # Deduplicate if head and tail overlap (small files)
    if len(head_raw) < N_SAMPLE_LINES:
        all_timestamps = head_timestamps
        tail_timestamps = []
    else:
        all_timestamps = head_timestamps + tail_timestamps

    # Ordering check
    head_ordered, head_max_bw = _check_ordering(head_timestamps)
    tail_ordered, tail_max_bw = _check_ordering(tail_timestamps)
    global_ordered = True
    global_bw = 0
    if head_timestamps and tail_timestamps:
        gap = tail_timestamps[0] - head_timestamps[-1]
        if gap < -10 * NS_PER_SEC:
            global_ordered = False
            global_bw = -gap

    likely_ordered = head_ordered and tail_ordered and global_ordered
    max_backward_jump = max(head_max_bw, tail_max_bw, global_bw)

    # Timestamp resolution (on normalized nanos)
    ts_resolution = _infer_timestamp_resolution(all_timestamps, dataset_kind)
    # For float_nanos, resolution cannot be better than microseconds
    if ts_repr == "float_nanos" and ts_resolution == "nanoseconds":
        ts_resolution = "microseconds_or_worse"

    # Timestamp format
    if dataset_kind == "optc":
        ts_format = "iso8601"
    else:
        ts_format = "epoch_nanos"

    # ISO representations for readability
    def nanos_to_iso(ns):
        if ns is None:
            return None
        dt = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
        return dt.isoformat()

    # - 5: Schema / structure -
    cdm_version = None
    wrapper_style = None
    if all_records:
        cdm_version = _extract_cdm_version(all_records[0])
        wrapper_style = _extract_wrapper_style(all_records[0], dataset_kind)

    source_field = _extract_source_field(all_records, dataset_kind)
    uuid_case = _check_uuid_case(all_records, dataset_kind)
    seq_range = _extract_sequence_range(all_records, dataset_kind)

    return {
        "path": rel_path,
        "file_size_bytes": file_size,
        "dataset_kind": dataset_kind,
        "source_tag": source_tag,
        "first_timestamp_ns": first_ts,
        "last_timestamp_ns": last_ts,
        "first_realistic_ts_ns": first_realistic_ts,
        "first_timestamp_iso": nanos_to_iso(first_ts),
        "last_timestamp_iso": nanos_to_iso(last_ts),
        "first_realistic_ts_iso": nanos_to_iso(first_realistic_ts),
        "timestamp_format": ts_format,
        "timestamp_resolution": ts_resolution,
        "ts_raw_representation": ts_repr,
        "cdm_version": cdm_version,
        "wrapper_style": wrapper_style,
        "source_field": source_field,
        "uuid_case": uuid_case,
        "likely_ordered": likely_ordered,
        "max_backward_jump_ns": max_backward_jump,
        "seq_min": seq_range[0] if seq_range else None,
        "seq_max": seq_range[1] if seq_range else None,
        "trailing_comma_observed": trailing_comma_observed,
    }


# -- Loop / batch extraction --
def list_dataset_files(dataset: str, sub: str) -> list[Path]:
    """List all JSONL files for a dataset+sub combination.

    dataset: One of 'e3', 'e5', 'optc'.
    sub: e.g. for e3/e5: 'cadets', 'clearscope', 'fivedirections', 'theia', 'trace', 'marple'.
         e.g. for optc: 'AIA-51-75', 'AIA-201-225', etc.

    Returns list[Path]: sorted list of absolute file paths.
    """
    if dataset == "e3":
        root = DATA_RAW / "Engagement3" / sub
    elif dataset == "e5":
        root = DATA_RAW / "Engagement5" / sub
    elif dataset == "optc":
        root = DATA_RAW / "OpTC"
    else:
        raise ValueError(f"Unknown dataset: {dataset}")

    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if not ("json" in name or "jsonl" in name):
            continue
        if ".tar" in name or ".gz" in name:
            continue
        if dataset == "optc":
            if sub not in str(path):
                continue
        files.append(path)

    return sorted(files)

def build_file_registry(dataset: str, sub: str) -> list[dict]:
    """Build metadata registry for all files in a dataset+sub combination.

    Returns list[dict]: one per file, ordered by first_realistic_ts_ns.
    """
    files = list_dataset_files(dataset, sub)
    print(f"Found {len(files)} files for {dataset}/{sub}", file=sys.stderr)

    registry = []
    for i, fpath in enumerate(files):
        t0 = time.time()
        try:
            meta = extract_file_metadata(fpath)
            registry.append(meta)
            elapsed = time.time() - t0
            ts_info = meta["first_realistic_ts_iso"] or meta["first_timestamp_iso"] or "no_timestamp"
            print(f"  [{i+1}/{len(files)}] {fpath.name} -> {ts_info} ({elapsed:.1f}s)", file=sys.stderr)
        except Exception as e:
            print(f"  [{i+1}/{len(files)}] {fpath.name} -> ERROR: {e}", file=sys.stderr)
            registry.append({
                "path": str(fpath.relative_to(DATA_RAW)),
                "error": str(e),
            })

    registry.sort(key=lambda m: (m.get("first_realistic_ts_ns") is None, m.get("first_realistic_ts_ns", 0)))
    return registry


# print for copy-paste into registry module
def print_registry_for_copypaste(dataset: str, sub: str):
    """Run metadata extraction and print as a Python dict literal ready for copy-paste."""
    registry = build_file_registry(dataset, sub)
    var_name = f"REGISTRY_{dataset.upper()}_{sub.upper().replace('-', '_')}"

    print(f"\n{var_name} = [")
    for entry in registry:
        print("    {")
        for k, v in entry.items():
            print(f"        {k!r}: {v!r},")
        print("    },")
    print("]")
    print(f"\n# {len(registry)} files total")
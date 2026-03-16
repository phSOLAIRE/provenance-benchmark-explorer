"""
FILE ANNOTATIONS
These functions are used to extract start / end timestamps, size of files and other useful metadata.
Mainly these functions are helpful for building the registry data structures for the individual datasets.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from provenance_explorer.registry.repo_paths import DATA_RAW

# Event keys across CDM versions
CDM18_EVENT_KEY = "com.bbn.tc.schema.avro.cdm18.Event"
CDM20_EVENT_KEY = "com.bbn.tc.schema.avro.cdm20.Event"
EVENT_KEYS = [CDM18_EVENT_KEY, CDM20_EVENT_KEY]

N_SAMPLE_LINES = 100 
TAIL_CHUNK_SIZE = 1024 * 1024


# helpers
def _try_parse_line(raw: str) -> Optional[dict]:
    """Try to parse a JSONL line, with trailing-comma fallback.
    Returns (parsed_dict, needed_comma_strip) or (None, False)."""
    line = raw.strip()
    if not line:
        return None, False # type: ignore
    try:
        return json.loads(line), False # type: ignore
    except json.JSONDecodeError:
        pass
    # trailing comma fallback
    if line.endswith(","):
        try:
            return json.loads(line[:-1]), True # type: ignore
        except json.JSONDecodeError:
            pass
    return None, False # type: ignore

def _extract_event_timestamp(record: dict, dataset_kind: str) -> Optional[int]:
    """Extract event timestamp as epoch nanos from a parsed record.
    For E3/E5: looks inside datum for CDM Event timestampNanos.
    For OpTC: converts ISO 8601 timestamp string to epoch nanos.
    Returns None if this record has no usable event timestamp.
    """
    if dataset_kind == "optc":
        # OpTC: top-level timestamp on action records (these are the "events")
        ts_str = record.get("timestamp")
        if ts_str is not None:
            return _iso8601_to_nanos(ts_str)
        return None
    else:
        # E3 / E5: datum -> Event key -> timestampNanos
        datum = record.get("datum", {})
        for key in EVENT_KEYS:
            evt = datum.get(key)
            if evt and "timestampNanos" in evt:
                return evt["timestampNanos"]
        return None

def _iso8601_to_nanos(ts_str: str) -> int:
    """Parse ISO 8601 timestamp string to epoch nanoseconds.
    Handles formats like '2019-09-18T20:19:41.611-04:00' and '2019-09-25T09:04:43.06-04:00'.
    Uses integer arithmetic to avoid float precision loss.
    """
    from datetime import datetime, timezone, timedelta
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
        # Pad fractional part to 9 digits (nanoseconds)
        frac_ns = int(frac.ljust(9, "0")[:9])
    else:
        main = dt_part
        frac_ns = 0

    dt = datetime.strptime(main, "%Y-%m-%dT%H:%M:%S")
    dt = dt.replace(tzinfo=tz)

    # Use integer arithmetic: epoch seconds * 1B + fractional nanos
    # calendar.timegm avoids float issues; we compute from the aware datetime
    epoch_s = int(dt.replace(microsecond=0).timestamp())
    return epoch_s * 1_000_000_000 + frac_ns

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
    """
    Extract the sub-dataset name from relative path.
    ie.. 'Engagement3/cadets/bla' -> 'cadets', 'OpTC/benign/17-18Sep19/AIA-51-75/blabla' -> 'AIA-51-75'
    """
    parts = Path(rel_path).parts
    if parts[0] in ("Engagement3", "Engagement5"):
        return parts[1]  # cadets, clearscope, fivedirections, theia, trace, marple
    elif parts[0] == "OpTC":
        # e.g. OpTC/benign/17-18Sep19/AIA-51-75/file.json -> AIA-51-75
        # Find the AIA-xxx-xxx part
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
            buffer = split[0]  # possibly partial first line
            complete = split[1:]

            for raw in reversed(complete):
                raw = raw.strip()
                if raw:
                    lines.append(raw.decode("utf-8", errors="replace"))
                    if len(lines) >= n:
                        break

        # Handle remaining buffer (file with no leading newline or single-line file)
        if len(lines) < n and buffer.strip():
            lines.append(buffer.strip().decode("utf-8", errors="replace"))

    lines.reverse()
    return lines

# def _estimate_line_count(file_path: Path, sample_lines: list[str], file_size: int) -> int:
#     """Estimate line count from average line length of sample lines."""
#     if not sample_lines:
#         return 0
#     # +1 for newline character per line
#     avg_bytes = sum(len(line.encode("utf-8")) + 1 for line in sample_lines) / len(sample_lines)
#     if avg_bytes == 0:
#         return 0
#     return int(file_size / avg_bytes)

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
    """Characterize the top-level JSON wrapper structure.
    Returns a string descriptor like 'datum+CDMVersion+source' or 'flat_optc'.
    """
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
            # OpTC has no source field in the same sense
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
    """Check if timestamps are approximately ordered.
    Returns (is_ordered, max_backward_jump_ns).
    is_ordered is True if no backward jump exceeds 1 second.
    """
    if len(timestamps) < 2:
        return True, 0
    max_backward = 0
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i - 1]
        if diff < 0:
            max_backward = max(max_backward, -diff)
    # 1 second tolerance
    return max_backward <= 1_000_000_000, max_backward

def _infer_timestamp_resolution(timestamps: list[int], dataset_kind: str) -> str:
    """Infer the effective timestamp resolution from a set of timestamps.
    Returns a string like 'nanoseconds', 'microseconds', 'milliseconds', 'seconds'.
    """
    if dataset_kind == "optc":
        # OpTC uses ISO 8601 with variable fractional seconds - check the raw string instead
        # But we only have parsed nanos here, so infer from the values
        pass

    if not timestamps:
        return "unknown"

    # Check what the smallest nonzero unit is
    remainders_us = [t % 1000 for t in timestamps]  # nanos mod 1000
    remainders_ms = [t % 1_000_000 for t in timestamps]  # nanos mod 1M
    remainders_s = [t % 1_000_000_000 for t in timestamps]  # nanos mod 1B

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
        return None  # OpTC doesn't have sequence numbers

    seqs = []
    for rec in records:
        datum = rec.get("datum", {})
        for key in EVENT_KEYS:
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



# Main extraction function
def extract_file_metadata(file_path: Path) -> dict:
    """
    Extract metadata from a single dataset json/jsonl file.

    Reads only head and tail samples (N_SAMPLE_LINES each) 
    Returns a dict of primitive-typed metadata fields.

    file_path : Absolute path to the JSONL file as ÜPath object

    Returns
    dict with keys:
        path, file_size_bytes,  (--est_line_count,--)
        dataset_kind, source_tag,
        first_timestamp_ns, last_timestamp_ns,
        first_timestamp_iso, last_timestamp_iso,
        timestamp_format, timestamp_resolution,
        cdm_version, wrapper_style, source_field,
        uuid_case, likely_ordered, max_backward_jump_ns,
        seq_min, seq_max,
        trailing_comma_observed,
    """
    from datetime import datetime, timezone

    rel_path = str(file_path.relative_to(DATA_RAW))
    dataset_kind = _detect_dataset_kind(rel_path)
    source_tag = _detect_source_tag(rel_path)
    file_size = file_path.stat().st_size

    # Read head and tail samples
    head_raw = _read_head_lines(file_path, N_SAMPLE_LINES)
    tail_raw = _read_tail_lines(file_path, N_SAMPLE_LINES)

    # Parse all sampled lines
    head_records = []
    tail_records = []
    trailing_comma_observed = False

    for line in head_raw:
        rec, needed_strip = _try_parse_line(line) # type: ignore
        if needed_strip:
            trailing_comma_observed = True
        if rec is not None:
            head_records.append(rec)

    for line in tail_raw:
        rec, needed_strip = _try_parse_line(line) # type: ignore
        if needed_strip:
            trailing_comma_observed = True
        if rec is not None:
            tail_records.append(rec)

    all_records = head_records + tail_records

    # --- Timestamps ---
    # Scan head forward for first event timestamp
    first_ts = None
    for rec in head_records:
        ts = _extract_event_timestamp(rec, dataset_kind)
        if ts is not None:
            first_ts = ts
            break

    # Scan tail backward for last event timestamp
    last_ts = None
    for rec in reversed(tail_records):
        ts = _extract_event_timestamp(rec, dataset_kind)
        if ts is not None:
            last_ts = ts
            break

    # Collect all timestamps from samples for ordering check and resolution
    head_timestamps = []
    for rec in head_records:
        ts = _extract_event_timestamp(rec, dataset_kind)
        if ts is not None:
            head_timestamps.append(ts)

    tail_timestamps = []
    for rec in reversed(tail_records):
        ts = _extract_event_timestamp(rec, dataset_kind)
        if ts is not None:
            tail_timestamps.append(ts)
    tail_timestamps.reverse()

    # Deduplicate if head and tail overlap (small files)
    # Detect overlap: if file has fewer lines than 2*N_SAMPLE_LINES, head and tail share lines.
    # Use raw line content to deduplicate.
    if len(head_raw) < N_SAMPLE_LINES:
        # File has fewer lines than one sample — tail is a subset of head, just use head
        all_timestamps = head_timestamps
        tail_timestamps = []
    else:
        all_timestamps = head_timestamps + tail_timestamps

    # Ordering check on head and tail separately
    head_ordered, head_max_bw = _check_ordering(head_timestamps)
    tail_ordered, tail_max_bw = _check_ordering(tail_timestamps)
    # Also check that tail starts after head ends (global ordering)
    global_ordered = True
    global_bw = 0
    if head_timestamps and tail_timestamps:
        gap = tail_timestamps[0] - head_timestamps[-1]
        if gap < -1_000_000_000:
            global_ordered = False
            global_bw = -gap

    likely_ordered = head_ordered and tail_ordered and global_ordered
    max_backward_jump = max(head_max_bw, tail_max_bw, global_bw)

    # Timestamp resolution
    ts_resolution = _infer_timestamp_resolution(all_timestamps, dataset_kind)

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

    # --- Schema / structure ---
    cdm_version = None
    wrapper_style = None
    if all_records:
        cdm_version = _extract_cdm_version(all_records[0])
        wrapper_style = _extract_wrapper_style(all_records[0], dataset_kind)

    # Source field
    source_field = _extract_source_field(all_records, dataset_kind)

    # UUID case
    uuid_case = _check_uuid_case(all_records, dataset_kind)

    # Sequence range
    seq_range = _extract_sequence_range(all_records, dataset_kind)

    # Estimated line count
    all_raw = head_raw + tail_raw
    # est_lines = _estimate_line_count(file_path, all_raw, file_size)

    return {
        "path": rel_path,
        "file_size_bytes": file_size,
        # "est_line_count": est_lines,
        "dataset_kind": dataset_kind,
        "source_tag": source_tag,
        "first_timestamp_ns": first_ts,
        "last_timestamp_ns": last_ts,
        "first_timestamp_iso": nanos_to_iso(first_ts),
        "last_timestamp_iso": nanos_to_iso(last_ts),
        "timestamp_format": ts_format,
        "timestamp_resolution": ts_resolution,
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



# Loop / batch extraction
def list_dataset_files(dataset: str, sub: str) -> list[Path]:
    """List all JSONL files for a dataset+sub combination.

    Parameters
    ----------
    dataset : str
        One of 'e3', 'e5', 'optc'.
    sub : str
        For e3/e5: one of 'cadets', 'clearscope', 'fivedirections', 'theia', 'trace', 'marple'.
        For optc: one of the AIA group names like 'AIA-51-75', 'AIA-201-225', etc.

    Returns
    -------
    list[Path] : sorted list of absolute file paths.
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
        # For OpTC, filter to the requested AIA group
        if dataset == "optc":
            if sub not in str(path):
                continue
        files.append(path)

    return sorted(files)

def build_file_registry(dataset: str, sub: str) -> list[dict]:
    """Build metadata registry for all files in a dataset+sub combination.
    dataset: One of 'e3', 'e5', 'optc'.
    sub: Sub-dataset identifier 

    Returns
    list[dict] : list of metadata dicts, one per file, ordered by first_timestamp_ns.
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
            ts_info = meta["first_timestamp_iso"] or "no_timestamp"
            print(f"  [{i+1}/{len(files)}] {fpath.name} -> {ts_info} ({elapsed:.1f}s)", file=sys.stderr)
        except Exception as e:
            print(f"  [{i+1}/{len(files)}] {fpath.name} -> ERROR: {e}", file=sys.stderr)
            registry.append({
                "path": str(fpath.relative_to(DATA_RAW)),
                "error": str(e),
            })

    # Sort by first timestamp
    registry.sort(key=lambda m: (m.get("first_timestamp_ns") is None, m.get("first_timestamp_ns", 0)))

    return registry



# print for copy-paste into registry module
def print_registry_for_copypaste(dataset: str, sub: str):
    """
    Run metadata extraction and print as a Python dict literal ready for copy-paste.
    """
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
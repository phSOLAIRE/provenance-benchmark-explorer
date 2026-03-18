"""
Core functions:
    - make_dataset_iterator: goto function for building an iterator for a timespan with repository wide tools
    - partition_by_time: for multiprocessing, make multiple iterators breaking up a timespan

Two-fold iterator system for streaming through DARPA datasets.

Layer 1 — FileWindowIterator
    Iterates over a single huge file, yielding parsed records whose timestamps fall within a given time window.  
    Records without an explicit timestamp inherit the last observed timestamp.

Layer 2 — DatasetIterator
    Orchestrates across all files in a dataset instance (e.g. E3 + Cadets),
    iterating files sequentially sorted by their first realistic timestamp.

Both layers are meant to be lightweight and serialisable so that higher-level code can partition time ranges and run multiple iterators in parallel.

!! Usage examples are in notebooks/demo/raw_file_handling_demo.ipynb !! 
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Callable,
    Generator,
    Iterator,
    Optional,
    Sequence,
    TypeVar,
)
from provenance_explorer.registry.registry_all import DATA_RAW
logger = logging.getLogger(__name__)

T = TypeVar("T")

# Type aliases
TsExtractor = Callable[[str], Optional[int]]
"""Takes a text line, returns a nanosecond timestamp or None."""

ParseFn = Callable[[str], T]
"""User-supplied function that turns a text line into a domain record."""

# Constants
_SEEK_BACK_BYTES: int = 1024 * 1024  # 1 mb back seek for start point search
_NS_PER_SECOND: int = 1_000_000_000

# Layer 1 — FileWindowIterator
@dataclass(frozen=True)
class FileWindowConfig:
    """
    Immutable, serialisable configuration for a FileWindowIterator.
    """

    filepath: Path
    likely_ordered: bool
    encoding: str = "utf-8"
    t_start: Optional[int] = None  # inclusive, nanoseconds
    t_end: Optional[int] = None  # exclusive, nanoseconds
    test_run_seconds: Optional[int] = None
    seek_back_bytes: int = _SEEK_BACK_BYTES

    @property
    def t_start_safe(self) -> int:
        """Return t_start or 0 when unbounded."""
        return self.t_start if self.t_start is not None else 0

    @property
    def t_end_safe(self) -> int:
        """Return t_end or maxint when unbounded."""
        return self.t_end if self.t_end is not None else 2**63

class FileWindowIterator(Iterator[tuple[int, T]]):
    """
    Iterates over one file, yielding (timestamp_ns, parsed_record) for every line whose (explicit or inherited) timestamp falls within [t_start, t_end).

    Parameters
    ----------
    cfg : FileWindowConfig
        see above.
    ts_extractor : TsExtractor
        Dataset-specific function str -> int | None.
    parse_fn : ParseFn
        User-supplied record parser str -> T.
    """

    def __init__(
        self,
        cfg: FileWindowConfig,
        ts_extractor: TsExtractor,
        parse_fn: ParseFn[T],
    ) -> None:
        self.cfg = cfg
        self._ts_extractor = ts_extractor
        self._parse_fn = parse_fn

        self._fh = None  # opened lazily
        self._gen: Optional[Generator[tuple[int, T], None, None]] = None
        self._exhausted = False

    # -- Iterator impl -- 
    def __iter__(self) -> FileWindowIterator[T]:
        return self

    def __next__(self) -> tuple[int, T]:
        if self._gen is None:
            self._gen = self._iterate()
        try:
            return next(self._gen)
        except StopIteration:
            self._exhausted = True
            self.close()
            raise

    # -- Public --
    def close(self) -> None:
        if self._fh is not None and not self._fh.closed:
            self._fh.close()
            self._fh = None

    # -- Internals --
    def _open(self):
        self._fh = open(self.cfg.filepath, "r", encoding=self.cfg.encoding)

    def _iterate(self) -> Generator[tuple[int, T], None, None]:
        self._open()
        fh = self._fh

        t_start = self.cfg.t_start_safe
        t_end = self.cfg.t_end_safe

        # determine start position in file
        last_ts: Optional[int] = None

        if self.cfg.likely_ordered and self.cfg.t_start is not None:
            start_byte = self._bisect_start(t_start)
            fh.seek(start_byte) # type: ignore
            # After seeking we may be mid-line; skip to next full line
            if start_byte > 0:
                fh.readline()  # discard partial line # type: ignore
                # Recover the last timestamp before the seek point so that non-timestamped records right after the seek have a context.
                last_ts = self._scan_back_for_ts(start_byte)
        # else: start from byte 0

        # Streaming loop
        test_anchor: Optional[int] = None
        test_limit: Optional[int] = None

        for line in fh: # type: ignore
            line = line.rstrip("\n\r")
            if not line:
                continue

            ts = self._ts_extractor(line)
            if ts is not None:
                last_ts = ts
            # else: inherit last_ts (may still be None for leading non-ts lines)

            effective_ts = last_ts

            # test_run bookkeeping 
            if self.cfg.test_run_seconds is not None:
                if effective_ts is not None and test_anchor is None:
                    test_anchor = effective_ts
                    test_limit = test_anchor + self.cfg.test_run_seconds * _NS_PER_SECOND
                if test_limit is not None and effective_ts is not None and effective_ts > test_limit:
                    return  # done with this file's test window

            # Time window filtering
            if effective_ts is None:
                # Leading lines before any timestamp in the file.
                # Include them only if reading from the start (no t_start specified), so they arent silently dropped.
                if self.cfg.t_start is None:
                    yield (0, self._parse_fn(line))
                continue

            if effective_ts < t_start:
                continue
            if effective_ts >= t_end:
                if self.cfg.likely_ordered:
                    return  # past window in an ordered file 
                continue  # unordered file — keep scanning

            yield (effective_ts, self._parse_fn(line))

    def _bisect_start(self, target_ts: int) -> int:
        """
        Binary search for an approximate byte offset where timestamps first reach target_ts. 
        Returns a byte position that is conservatively before the true start.
        After seeking to the returned position, caller should skip the (only partial) first line and scan forward.
        """
        file_size = os.path.getsize(self.cfg.filepath)
        if file_size == 0:
            return 0

        lo, hi = 0, file_size
        best = 0  # default to start of file

        fh = self._fh  # already open

        while lo < hi:
            mid = (lo + hi) // 2
            fh.seek(mid) # type: ignore
            fh.readline()  # skip partial line # type: ignore

            # Scan forward to find first timestamped line
            ts = None
            attempts = 0
            while ts is None and attempts < 50:
                probe_line = fh.readline() # type: ignore
                if not probe_line:
                    break  # hit EOF
                ts = self._ts_extractor(probe_line.rstrip("\n\r"))
                attempts += 1

            if ts is None:
                # Couldnt find a timestamp in this region — narrow from top
                hi = mid
                continue

            if ts < target_ts:
                lo = mid + 1
                best = mid  # this position is before target, safe to use
            else:
                hi = mid

        # Back off conservatively
        return max(0, best - self.cfg.seek_back_bytes)

    def _scan_back_for_ts(self, seek_byte: int) -> Optional[int]:
        """
        Scan backwards from seek_byte to find the last timestamp before the seek position.  
        This gives non-timestamped records right after a bisect-seek a valid inherited timestamp.

        Reads up to seek_back_bytes before seek_byte.  
        Returns the last timestamp found, or None if no timestamp is found (e.g. near file start).
        """
        fh = self._fh
        scan_start = max(0, seek_byte - self.cfg.seek_back_bytes)
        if scan_start >= seek_byte:
            return None

        saved_pos = fh.tell()  # type: ignore
        try:
            fh.seek(scan_start)  # type: ignore
            if scan_start > 0:
                fh.readline()  # discard partial first line  # type: ignore

            last_ts: Optional[int] = None
            while fh.tell() < seek_byte:  # type: ignore
                line = fh.readline()  # type: ignore
                if not line:
                    break  # EOF
                ts = self._ts_extractor(line.rstrip("\n\r"))
                if ts is not None:
                    last_ts = ts
            return last_ts
        finally:
            fh.seek(saved_pos)  # type: ignore

# 2 — DatasetIterator
@dataclass(frozen=True)
class FileEntry:
    """Minimal metadata about one file in a dataset from the registry."""
    filepath: Path
    first_timestamp_ns: int
    last_timestamp_ns: int
    first_realistic_ts_ns: int
    likely_ordered: bool
    encoding: str = "utf-8"

def _select_files(
    files: Sequence[FileEntry],
    t_start: Optional[int],
    t_end: Optional[int],
) -> list[FileEntry]:
    """Return the subset of *files* whose time range overlaps [t_start, t_end).

    Uses 'first_realistic_ts_ns' as the effective start of each file
    and 'last_timestamp_ns' as its end.
    """
    t_lo = t_start if t_start is not None else 0
    t_hi = t_end if t_end is not None else 2**63

    selected = []
    for f in files:
        file_start = f.first_realistic_ts_ns
        file_end = f.last_timestamp_ns
        # overlap test [file_start, file_end) and [t_lo, t_hi)
        if file_start < t_hi and file_end > t_lo:
            selected.append(f)
    return sorted(selected, key=lambda f: f.first_realistic_ts_ns)

class DatasetIterator(Iterator[tuple[int, T]]):
    """Iterate over all records in a dataset instance within a time window.

    Files are iterated sequentially, sorted by their first realistic timestamp.  
    Records without an explicit timestamp inherit the last observed timestamp from the same file.

    Parameters: 

    files : Sequence[FileEntry]
        Registry entries for every file in this dataset instance.
        Typically comes from e.g. REGISTRY_E3_CADETS
    ts_extractor : TsExtractor
        Dataset-specific timestamp extractor.
    parse_fn : ParseFn
        User-supplied record parser.
    t_start, t_end : int | None
        Nanosecond bounds. 'None' means unbounded on that side.
    test_run_seconds : int | None
        When set, each file only yields records from its first
        test_run_seconds seconds.  Useful for smoke-testing.
    """
    def __init__(
        self,
        files: Sequence[FileEntry],
        ts_extractor: TsExtractor,
        parse_fn: ParseFn[T],
        t_start: Optional[int] = None,
        t_end: Optional[int] = None,
        test_run_seconds: Optional[int] = None,
    ) -> None:
        self._ts_extractor = ts_extractor
        self._parse_fn = parse_fn

        self._selected = _select_files(files, t_start, t_end)
        logger.info(
            "DatasetIterator: %d / %d files selected for window [%s, %s)",
            len(self._selected),
            len(files),
            t_start,
            t_end,
        )

        self._shared_cfg_kwargs = dict(
            t_start=t_start,
            t_end=t_end,
            test_run_seconds=test_run_seconds,
        )

        self._gen: Optional[Generator[tuple[int, T], None, None]] = None
        self._open_iters: list[FileWindowIterator] = []

    # -- Iterator implements --
    def __iter__(self) -> DatasetIterator[T]:
        return self

    def __next__(self) -> tuple[int, T]:
        if self._gen is None:
            self._gen = self._sequential_iterate()
        try:
            return next(self._gen)
        except StopIteration:
            self.close()
            raise

    # -- public --
    @property
    def selected_files(self) -> list[FileEntry]:
        """The files that overlap the requested time window."""
        return list(self._selected)

    def close(self) -> None:
        for it in self._open_iters:
            it.close()
        self._open_iters.clear()

    # -- iter strategies --
    def _make_file_iter(self, entry: FileEntry) -> FileWindowIterator[T]:
        cfg = FileWindowConfig(
            filepath=entry.filepath,
            likely_ordered=entry.likely_ordered,
            encoding=entry.encoding,
            **self._shared_cfg_kwargs, # type: ignore
        )
        it = FileWindowIterator(cfg, self._ts_extractor, self._parse_fn)
        self._open_iters.append(it)
        return it

    def _sequential_iterate(self) -> Generator[tuple[int, T], None, None]:
        """Per-file sequential: iterate files one at a time."""
        for entry in self._selected:
            file_iter = self._make_file_iter(entry)
            try:
                yield from file_iter
            finally:
                file_iter.close()
                
# Multiprocessing helper
def partition_by_time(
    files: Sequence[FileEntry],
    t_start: Optional[int],
    t_end: Optional[int],
    n_partitions: int,
) -> list[tuple[int, int]]:
    """
    Divide a time range into n_partitions equal-width (! not volume) slices.
    Returns 
        - list of (t_start_i, t_end_i) nanosecond bounds
    Each partition can be handed to a separate DatasetIterator in its own worker process.
    """
    if not files:
        return []

    effective_start = t_start if t_start is not None else min(
        f.first_realistic_ts_ns for f in files
    )
    effective_end = t_end if t_end is not None else max(
        f.last_timestamp_ns for f in files
    )

    width = (effective_end - effective_start) // n_partitions
    if width <= 0:
        return [(effective_start, effective_end)]

    partitions = []
    for i in range(n_partitions):
        p_start = effective_start + i * width
        p_end = effective_start + (i + 1) * width if i < n_partitions - 1 else effective_end
        partitions.append((p_start, p_end))
    return partitions

# Convenience: build from registry dict
def make_dataset_iterator(
    registry: list[dict[str, Any]],
    parse_fn: ParseFn[T],
    ts_extractor: TsExtractor,
    t_start: Optional[int] = None,
    t_end: Optional[int] = None,
    test_run_seconds: Optional[int] = None,
) -> DatasetIterator[T]:
    """
    Construct a DatasetIterator from a registry dictionary.
    Registry should contain: path, first_timestamp_ns, last_timestamp_ns, first_realistic_ts_ns, likely_ordered
    """
    entries = []
    for f in registry:
        entries.append(
            FileEntry(
                filepath=DATA_RAW / f["path"],
                first_timestamp_ns=f["first_timestamp_ns"],
                last_timestamp_ns=f["last_timestamp_ns"],
                first_realistic_ts_ns=f["first_realistic_ts_ns"],
                likely_ordered=f["likely_ordered"],
                encoding=f.get("encoding", "utf-8"),
            )
        )
    return DatasetIterator(
        files=entries,
        ts_extractor=ts_extractor,
        parse_fn=parse_fn,
        t_start=t_start,
        t_end=t_end,
        test_run_seconds=test_run_seconds,
    )
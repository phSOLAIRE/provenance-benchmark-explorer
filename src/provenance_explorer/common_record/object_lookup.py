"""
Object lookup - uuid->metadata cache for resolving event targets.

this is a bit heavier, as the naive approach (store object uuids in a dict) exceeds memory.

Strategy:
1. Filter: 
    only collect uuids for types that map to FILE, SOCKET, or PROCESS in the KRYSTAL-ish graph model. 
    Skip MemoryObject, most SrcSinkObjects, UnitDependencies, ProvenanceTagNode, etc.; 
    this will be marked as unresolved in iterations. these are based decisions to limit scope 
    and other configurations are arguably also defensible

2. Representation: 
    uuids stored as 16-byte binary (bytes.fromhex) & ObjectInfo with NamedTuple encoding.

3. SQLite: 
    when filtered entry count exceeds a memory threshold, the lookup is stored in a SQLite database on disk 
    with an in-memory LRU cache for fast repeated access. 
    Otherwise, a dict is used.

Also: 
Thread/unit collapse, to fit our Process-level granularity
- SUBJECT_THREAD and SUBJECT_UNIT entries store parent_uuid.
- resolve_to_process(uuid) follows parent_uuid chain to SUBJECT_PROCESS.
"""

from __future__ import annotations

import logging
import pickle
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional, NamedTuple

logger = logging.getLogger(__name__)

# CONFIGS
# If filtered entry count exceeds this, use SQLite instead of in-memory dict.
MEMORY_THRESHOLD = 20_000_000

# LRU cache size for SQLite mode (number of entries to keep in memory)
LRU_CACHE_SIZE = 20_000_000

# Compact types
class ObjectRoleCompact:
    """Compact role encoding as single ints for storage efficiency."""
    FILE = 1
    SOCKET = 2
    PROCESS = 3
    EXECUTABLE = 4

    @staticmethod
    def to_schema_role(val: int):
        """Convert compact int to schema.ObjectRole enum."""
        from .schema import ObjectRole as SchemaRole
        return {1: SchemaRole.FILE, 2: SchemaRole.SOCKET,
                3: SchemaRole.PROCESS, 4: SchemaRole.EXECUTABLE}.get(val)


class CompactInfo(NamedTuple):
    """
    Minimal per-uuid metadata. NamedTuple for low memory overhead.

    Fields:
        role:           int (ObjectRoleCompact constant) - resolved graph role
        ambiguous:      bool - True if uuid had multiple conflicting types
        path:           str | None - file path, socket path, registry key
        ip:             str | None - IP address (NetFlowObject, OpTC FLOW)
        port:           int | None - port number
        cmdline:        str | None - process command line
        parent_uuid:    bytes(16) | None - for thread/unit -> process collapse
        pid:            int | None - process ID
        principal_uuid: bytes(16) | None - user/principal behind this subject
        types_raw:      str - comma-joined original type strings (for debug)
    """
    role: int
    ambiguous: bool
    path: Optional[str]
    ip: Optional[str]
    port: Optional[int]
    cmdline: Optional[str]
    parent_uuid: Optional[bytes]
    pid: Optional[int]
    principal_uuid: Optional[bytes]
    types_raw: str



# uuid conversion helpers
def uuid_to_bytes(uuid_str: str) -> bytes:
    """Convert a uuid string (with or without dashes) to 16 bytes."""
    return bytes.fromhex(uuid_str.replace("-", ""))


def bytes_to_uuid(b: bytes) -> str:
    """Convert 16 bytes back to uppercase uuid string with dashes."""
    h = b.hex().upper()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


# Type filtering: which record types to KEEP in the lookup
CDM_KEEP_RECORD_TYPES = {"Subject", "FileObject", "NetFlowObject", "RegistryKeyObject", "Host", "Principal"}

CDM_SKIP_RECORD_TYPES = {
    "MemoryObject", "SrcSinkObject", "UnnamedPipeObject", "IpcObject",
    "ProvenanceTagNode", "UnitDependency", "PacketSocketObject",
    "TimeMarker", "StartMarker", "EndMarker", "Principal",
}

OPTC_KEEP_OBJECT_TYPES = {"FILE", "MODULE", "FLOW", "PROCESS", "REGISTRY"}
OPTC_SKIP_OBJECT_TYPES = {"THREAD", "SHELL", "HOST", "TASK", "USER_SESSION", "SERVICE"}


# Type -> role resolution
CDM_TYPE_TO_ROLE: dict[str, int] = {
    "FileObject(FILE_OBJECT_FILE)": ObjectRoleCompact.FILE,
    "FileObject(FILE_OBJECT_BLOCK)": ObjectRoleCompact.FILE,
    "FileObject(FILE_OBJECT_PEFILE)": ObjectRoleCompact.FILE,
    "FileObject(FILE_OBJECT_DIR)": ObjectRoleCompact.FILE,
    "FileObject(FILE_OBJECT_CHAR)": ObjectRoleCompact.FILE,
    "RegistryKeyObject": ObjectRoleCompact.FILE,
    "FileObject(FILE_OBJECT_UNIX_SOCKET)": ObjectRoleCompact.SOCKET,
    "NetFlowObject": ObjectRoleCompact.SOCKET,
    "Subject(SUBJECT_PROCESS)": ObjectRoleCompact.PROCESS,
    "Subject(SUBJECT_THREAD)": ObjectRoleCompact.PROCESS,
    "Subject(SUBJECT_UNIT)": ObjectRoleCompact.PROCESS,
}

OPTC_TYPE_TO_ROLE: dict[str, int] = {
    "FILE": ObjectRoleCompact.FILE,
    "MODULE": ObjectRoleCompact.FILE,
    "REGISTRY": ObjectRoleCompact.FILE,
    "FLOW": ObjectRoleCompact.SOCKET,
    "PROCESS": ObjectRoleCompact.PROCESS,
}

ROLE_PRIORITY = [ObjectRoleCompact.PROCESS, ObjectRoleCompact.FILE,
                 ObjectRoleCompact.SOCKET, ObjectRoleCompact.EXECUTABLE]


def _resolve_role(observed_types: set[str], type_map: dict[str, int]) -> tuple[Optional[int], bool]:
    """Resolve a set of observed type strings to a single role int."""
    roles = set()
    for t in observed_types:
        role = type_map.get(t)
        if role is not None:
            roles.add(role)
    if len(roles) == 0:
        return None, False
    if len(roles) == 1:
        return roles.pop(), False
    for r in ROLE_PRIORITY:
        if r in roles:
            return r, True
    return roles.pop(), True



# Host and Principal metadata (small side structures)
class HostInfo(NamedTuple):
    """Metadata for a Host record. Typically 2-22 per subdataset."""
    uuid: str
    hostname: str
    os_details: str
    host_type: str
    interfaces: list[dict]  # [{"name": ..., "macAddress": ..., "ipAddresses": [...]}]


class PrincipalInfo(NamedTuple):
    """Metadata for a Principal/User record. are ~ up to 100 per subdataset."""
    uuid: str
    user_id: Optional[str]
    username: Optional[str]
    group_ids: Optional[list[str]]


# Collection buffer (used during pass 1 before finalization); otherwise memory is killed for cases like trcce
class _CollectionEntry:
    """Mutable entry used only during pass 1 collection. Freed after finalization."""
    __slots__ = ("observed_types", "path", "ip", "port", "cmdline",
                 "parent_uuid_str", "pid", "principal_uuid_str")

    def __init__(self):
        self.observed_types: set[str] = set()
        self.path: Optional[str] = None
        self.ip: Optional[str] = None
        self.port: Optional[int] = None
        self.cmdline: Optional[str] = None
        self.parent_uuid_str: Optional[str] = None
        self.pid: Optional[int] = None
        self.principal_uuid_str: Optional[str] = None


# ObjectLookup - the main class
class ObjectLookup:
    """
    uuid -> CompactInfo mapping for one subdataset.

    Small datasets (< MEMORY_THRESHOLD entries): in-memory dict with bytes keys.
    Large datasets: SQLite on disk + in-memory LRU cache.
    """

    def __init__(self, dataset: str, sub_dataset: str):
        self.dataset = dataset
        self.sub_dataset = sub_dataset
        self._mode: str = "memory"  # "memory" or "sqlite"
        self._dict: Optional[dict[bytes, CompactInfo]] = None
        self._db_path: Optional[Path] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._lru: Optional[OrderedDict] = None
        self._finalized: bool = False
        self._entry_count: int = 0
        self._stats: dict[str, int] = {}

        # small side structures for graph metadata, later on important
        self.host_metadata: dict[str, HostInfo] = {} # host_uuid -> HostInfo
        self.principal_metadata: dict[str, PrincipalInfo] = {}  # principal_uuid -> PrincipalInfo

    def __len__(self) -> int:
        return self._entry_count

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def stats(self) -> dict[str, int]:
        return self._stats

    # Lookup funcs
    def get(self, uuid_bytes: bytes) -> Optional[CompactInfo]:
        """Look up a uuid (as 16 bytes). Returns CompactInfo | None."""
        if self._mode == "memory":
            return self._dict.get(uuid_bytes) if self._dict else None
        else:
            return self._sqlite_get(uuid_bytes)

    def get_str(self, uuid_str: str) -> Optional[CompactInfo]:
        """Convenience: look up by uuid string (handles dashes and case)."""
        try:
            return self.get(uuid_to_bytes(uuid_str.upper()))
        except (ValueError, AttributeError):
            return None

    def _sqlite_get(self, uuid_bytes: bytes) -> Optional[CompactInfo]:
        """SQLite lookup with LRU cache."""
        if self._lru is not None and uuid_bytes in self._lru:
            self._lru.move_to_end(uuid_bytes)
            return self._lru[uuid_bytes]

        if self._conn is None:
            return None

        cursor = self._conn.execute(
            "SELECT role, ambiguous, path, ip, port, cmdline, parent_uuid, pid, principal_uuid, types_raw "
            "FROM lookup WHERE uuid = ?",
            (uuid_bytes,)
        )
        row = cursor.fetchone()
        if row is None:
            if self._lru is not None:
                self._lru[uuid_bytes] = None
                if len(self._lru) > LRU_CACHE_SIZE:
                    self._lru.popitem(last=False)
            return None

        info = CompactInfo(
            role=row[0], ambiguous=bool(row[1]),
            path=row[2], ip=row[3], port=row[4],
            cmdline=row[5], parent_uuid=row[6],
            pid=row[7], principal_uuid=row[8],
            types_raw=row[9] or "",
        )

        if self._lru is not None:
            self._lru[uuid_bytes] = info
            if len(self._lru) > LRU_CACHE_SIZE:
                self._lru.popitem(last=False)

        return info

    # Thread/unit -> process collapse
    def resolve_to_process(self, uuid_bytes: bytes, max_depth: int = 10) -> bytes:
        """Follow parent_uuid chain to nearest SUBJECT_PROCESS."""
        current = uuid_bytes
        for _ in range(max_depth):
            info = self.get(current)
            if info is None:
                return current
            if "SUBJECT_PROCESS" in info.types_raw:
                return current
            if info.parent_uuid is None or info.parent_uuid == current:
                return current
            current = info.parent_uuid
        return current

    def resolve_to_process_str(self, uuid_str: str, max_depth: int = 10) -> str:
        """Convenience: resolve by string, return string."""
        try:
            result = self.resolve_to_process(uuid_to_bytes(uuid_str.upper()), max_depth)
            return bytes_to_uuid(result)
        except (ValueError, AttributeError):
            return uuid_str

    # ==============================================================================
    # lookup construction pass 1 - filtered collection with incremental flush
    # ==============================================================================

    # Max 5M entries in memory before flushing to SQLite staging to prevent memory failure.
    FLUSH_THRESHOLD = 5_000_000

    @classmethod
    def build_from_iterator(
        cls,
        dataset: str,
        sub_dataset: str,
        iterator,
        cache_root: Path,
        is_optc: bool = False,
    ) -> ObjectLookup:
        """
        Build the lookup from a raw dataset iterator (pass 1).

        For small datasets (< FLUSH_THRESHOLD unique uuids): collects everything in memory, then finalizes as pkl.

        For large datasets: flushes the in-memory buffer to a SQLite staging table every FLUSH_THRESHOLD entries, to keep low mem during collection
        """
        obj = cls(dataset, sub_dataset)
        buf: dict[str, _CollectionEntry] = {}
        n_seen = 0
        n_skipped = 0
        n_flushed = 0
        staging_conn: Optional[sqlite3.Connection] = None
        staging_path = obj._sqlite_path(cache_root).with_suffix(".staging.sqlite")

        t0 = time.time()
        for _ts, rec in iterator:
            n_seen += 1
            if is_optc:
                n_skipped += _collect_optc(rec, buf)
            else:
                n_skipped += _collect_cdm(rec, buf, obj.host_metadata, obj.principal_metadata)

            # Flush when buffer is too large
            if len(buf) >= cls.FLUSH_THRESHOLD:
                if staging_conn is None:
                    staging_conn = _create_staging_db(staging_path)
                _flush_buf_to_staging(buf, staging_conn)
                n_flushed += len(buf)
                logger.info(
                    f"  pass 1: flushed {len(buf)/1e6:.2f}M to staging "
                    f"({n_flushed/1e6:.1f}M total, {n_seen/1e6:.1f}M records seen)"
                )
                buf.clear()

            if n_seen % 10_000_000 == 0:
                logger.info(
                    f"  pass 1: {n_seen/1e6:.1f}M records, "
                    f"{(len(buf) + n_flushed)/1e6:.2f}M uuids (buf+staged), "
                    f"{n_skipped/1e6:.1f}M skipped"
                )

        elapsed = time.time() - t0
        total_approx = len(buf) + n_flushed
        logger.info(
            f"Pass 1 for {dataset}/{sub_dataset}: {n_seen} records in {elapsed:.1f}s, "
            f"~{total_approx} uuids, {n_skipped} skipped, "
            f"{len(obj.host_metadata)} hosts, {len(obj.principal_metadata)} principals"
        )

        if staging_conn is not None:
            # Large dataset: flush remaining, finalize from staging
            if buf:
                _flush_buf_to_staging(buf, staging_conn)
                buf.clear()
            staging_conn.commit()
            obj._finalize_from_staging(staging_conn, staging_path, cache_root, is_optc)
            staging_conn.close()
            if staging_path.exists():
                staging_path.unlink()
        else:
            # Small dataset: finalize from memory
            obj._finalize_and_store(buf, cache_root, is_optc)

        return obj

    def _finalize_and_store(
        self,
        buf: dict[str, _CollectionEntry],
        cache_root: Path,
        is_optc: bool,
    ) -> None:
        """Resolve roles, convert to compact form, & choose storage backend."""
        type_map = OPTC_TYPE_TO_ROLE if is_optc else CDM_TYPE_TO_ROLE
        self._entry_count = len(buf)
        stats: dict[str, int] = {"total_collected": len(buf)}
        use_sqlite = len(buf) > MEMORY_THRESHOLD

        if use_sqlite:
            self._init_sqlite_store(buf, type_map, cache_root, stats)
        else:
            self._init_memory_store(buf, type_map, stats)

        buf.clear()
        self._stats = stats
        self._finalized = True
        logger.info(f"Lookup finalized ({self._mode}): {stats}")

    def _init_memory_store(
        self,
        buf: dict[str, _CollectionEntry],
        type_map: dict[str, int],
        stats: dict[str, int],
    ) -> None:
        """Finalize into an in-memory dict."""
        self._mode = "memory"
        self._dict = {}

        for uuid_str, entry in buf.items():
            role, ambiguous = _resolve_role(entry.observed_types, type_map)
            if role is None:
                stats["filtered_no_role"] = stats.get("filtered_no_role", 0) + 1
                continue

            uuid_b = uuid_to_bytes(uuid_str)
            parent_b = uuid_to_bytes(entry.parent_uuid_str) if entry.parent_uuid_str else None
            principal_b = uuid_to_bytes(entry.principal_uuid_str) if entry.principal_uuid_str else None
            types_raw = ",".join(sorted(entry.observed_types))

            _count_role(stats, role, ambiguous)

            self._dict[uuid_b] = CompactInfo(
                role=role, ambiguous=ambiguous,
                path=_extract_string(entry.path) if not isinstance(entry.path, (str, type(None))) else entry.path,
                ip=_extract_string(entry.ip) if not isinstance(entry.ip, (str, type(None))) else entry.ip,
                port=_extract_int(entry.port) if not isinstance(entry.port, (int, type(None))) else entry.port,
                cmdline=_extract_string(entry.cmdline) if not isinstance(entry.cmdline, (str, type(None))) else entry.cmdline,
                parent_uuid=parent_b,
                pid=_extract_int(entry.pid) if not isinstance(entry.pid, (int, type(None))) else entry.pid,
                principal_uuid=principal_b,
                types_raw=types_raw,
            )

        self._entry_count = len(self._dict)

    def _init_sqlite_store(
        self,
        buf: dict[str, _CollectionEntry],
        type_map: dict[str, int],
        cache_root: Path,
        stats: dict[str, int],
    ) -> None:
        """Finalize into a SQLite database."""
        self._mode = "sqlite"
        self._db_path = self._sqlite_path(cache_root)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        if self._db_path.exists():
            self._db_path.unlink()

        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute(
            "CREATE TABLE lookup ("
            "uuid BLOB PRIMARY KEY, "
            "role INTEGER NOT NULL, ambiguous INTEGER NOT NULL, "
            "path TEXT, ip TEXT, port INTEGER, "
            "cmdline TEXT, parent_uuid BLOB, pid INTEGER, "
            "principal_uuid BLOB, types_raw TEXT)"
        )

        batch = []
        stored = 0
        for uuid_str, entry in buf.items():
            role, ambiguous = _resolve_role(entry.observed_types, type_map)
            if role is None:
                stats["filtered_no_role"] = stats.get("filtered_no_role", 0) + 1
                continue

            uuid_b = uuid_to_bytes(uuid_str)
            parent_b = uuid_to_bytes(entry.parent_uuid_str) if entry.parent_uuid_str else None
            principal_b = uuid_to_bytes(entry.principal_uuid_str) if entry.principal_uuid_str else None
            types_raw = ",".join(sorted(entry.observed_types))

            _count_role(stats, role, ambiguous)

            batch.append((
                uuid_b, role, int(ambiguous),
                _extract_string(entry.path) if not isinstance(entry.path, (str, type(None))) else entry.path,
                _extract_string(entry.ip) if not isinstance(entry.ip, (str, type(None))) else entry.ip,
                _extract_int(entry.port) if not isinstance(entry.port, (int, type(None))) else entry.port,
                _extract_string(entry.cmdline) if not isinstance(entry.cmdline, (str, type(None))) else entry.cmdline,
                parent_b,
                _extract_int(entry.pid) if not isinstance(entry.pid, (int, type(None))) else entry.pid,
                principal_b, types_raw
            ))
            stored += 1

            if len(batch) >= 100_000:
                conn.executemany("INSERT OR REPLACE INTO lookup VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
                batch.clear()

        if batch:
            conn.executemany("INSERT OR REPLACE INTO lookup VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)

        conn.commit()
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.close()

        self._conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        self._lru = OrderedDict()
        self._entry_count = stored
        logger.info(f"SQLite lookup: {stored} entries -> {self._db_path}")

    def _finalize_from_staging(
        self,
        staging_conn: sqlite3.Connection,
        staging_path: Path,
        cache_root: Path,
        is_optc: bool,
    ) -> None:
        """
        Finalize the lookup from a SQLite staging table.

        The staging table has raw entries (uuid_hex, types_csv, metadata) & possibly multiple rows per uuid
        To merge them: concatenate types, COALESCE metadata to resolve roles and write to the final lookup table.
        """
        type_map = OPTC_TYPE_TO_ROLE if is_optc else CDM_TYPE_TO_ROLE
        self._mode = "sqlite"
        self._db_path = self._sqlite_path(cache_root)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        if self._db_path.exists():
            self._db_path.unlink()

        logger.info("Finalizing: merging duplicate uuids...")

        # Read merged rows from staging
        # GROUP_CONCAT merges types from multiple flushes; 
        # !! COALESCE picks first non-null metadata !!
        merged_cursor = staging_conn.execute(
            "SELECT uuid_hex, GROUP_CONCAT(types_csv), "
            "COALESCE(MAX(path), NULL), COALESCE(MAX(ip), NULL), "
            "COALESCE(MAX(port), NULL), COALESCE(MAX(cmdline), NULL), "
            "COALESCE(MAX(parent_uuid_hex), NULL), COALESCE(MAX(pid), NULL), "
            "COALESCE(MAX(principal_uuid_hex), NULL) "
            "FROM staging GROUP BY uuid_hex"
        )

        # Write to final lookup DB
        final_conn = sqlite3.connect(str(self._db_path))
        final_conn.execute("PRAGMA journal_mode=WAL")
        final_conn.execute("PRAGMA synchronous=OFF")
        final_conn.execute(
            "CREATE TABLE lookup ("
            "uuid BLOB PRIMARY KEY, "
            "role INTEGER NOT NULL, ambiguous INTEGER NOT NULL, "
            "path TEXT, ip TEXT, port INTEGER, "
            "cmdline TEXT, parent_uuid BLOB, pid INTEGER, "
            "principal_uuid BLOB, types_raw TEXT)"
        )

        stats: dict[str, int] = {}
        batch = []
        stored = 0

        for row in merged_cursor:
            uuid_hex = row[0]
            types_csv_merged = row[1] or ""
            path = row[2]
            ip = row[3]
            port = row[4]
            cmdline = row[5]
            parent_hex = row[6]
            pid = row[7]
            principal_hex = row[8]

            # Deduplicate types (GROUP_CONCAT produces "Subject(X),Subject(X)")
            all_types = set(t.strip() for t in types_csv_merged.split(",") if t.strip())
            role, ambiguous = _resolve_role(all_types, type_map)
            if role is None:
                stats["filtered_no_role"] = stats.get("filtered_no_role", 0) + 1
                continue

            _count_role(stats, role, ambiguous)

            uuid_b = uuid_to_bytes(uuid_hex)
            parent_b = uuid_to_bytes(parent_hex) if parent_hex else None
            principal_b = uuid_to_bytes(principal_hex) if principal_hex else None
            types_raw = ",".join(sorted(all_types))

            batch.append((
                uuid_b, role, int(ambiguous),
                path, ip, port,
                cmdline, parent_b, pid,
                principal_b, types_raw
            ))
            stored += 1

            if len(batch) >= 100_000:
                final_conn.executemany(
                    "INSERT OR REPLACE INTO lookup VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch
                )
                batch.clear()

        if batch:
            final_conn.executemany(
                "INSERT OR REPLACE INTO lookup VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch
            )

        final_conn.commit()
        final_conn.execute("PRAGMA synchronous=NORMAL")
        final_conn.close()

        self._conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        self._lru = OrderedDict()
        self._entry_count = stored
        self._stats = stats
        self._finalized = True
        logger.info(f"Finalized from staging: {stored} entries -> {self._db_path} | {stats}")

    # path & save helpers
    def _cache_path(self, cache_root: Path) -> Path:
        d = cache_root / "object_lookups"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{self.dataset}_{self.sub_dataset}.pkl"

    def _sqlite_path(self, cache_root: Path) -> Path:
        d = cache_root / "object_lookups"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{self.dataset}_{self.sub_dataset}.sqlite"

    def _metadata_path(self, cache_root: Path) -> Path:
        """Sidecar pickle for host_metadata + principal_metadata."""
        d = cache_root / "object_lookups"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{self.dataset}_{self.sub_dataset}_meta.pkl"

    def save(self, cache_root: Path) -> Path:
        """Persist lookup to disk. Also saves host/principal metadata sidecar."""
        meta_p = self._metadata_path(cache_root)
        with open(meta_p, "wb") as f:
            pickle.dump({
                "host_metadata": self.host_metadata,
                "principal_metadata": self.principal_metadata,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)

        if self._mode == "sqlite":
            logger.info(f"Metadata sidecar saved: {len(self.host_metadata)} hosts, "
                        f"{len(self.principal_metadata)} principals -> {meta_p}")
            return self._db_path # type: ignore

        p = self._cache_path(cache_root)
        with open(p, "wb") as f:
            pickle.dump({
                "dataset": self.dataset,
                "sub_dataset": self.sub_dataset,
                "dict": self._dict,
                "stats": self._stats,
                "entry_count": self._entry_count,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(f"Saved: {self._entry_count} entries -> {p}")
        return p

    @classmethod
    def load(cls, dataset: str, sub_dataset: str, cache_root: Path) -> Optional["ObjectLookup"]:
        """Load from cache (SQLite or pickle). Returns None if not cached."""
        obj = cls(dataset, sub_dataset)

        # Try loading metadata sidecar (shared by both modes)
        meta_p = obj._metadata_path(cache_root)
        if meta_p.exists():
            with open(meta_p, "rb") as f:
                meta = pickle.load(f)
            obj.host_metadata = meta.get("host_metadata", {})
            obj.principal_metadata = meta.get("principal_metadata", {})

        # SQLite first
        sqlite_p = obj._sqlite_path(cache_root)
        if sqlite_p.exists():
            obj._mode = "sqlite"
            obj._db_path = sqlite_p
            obj._conn = sqlite3.connect(f"file:{sqlite_p}?mode=ro", uri=True)
            obj._lru = OrderedDict()
            cursor = obj._conn.execute("SELECT COUNT(*) FROM lookup")
            obj._entry_count = cursor.fetchone()[0]
            obj._finalized = True
            logger.info(f"Loaded (SQLite): {obj._entry_count} entries, "
                        f"{len(obj.host_metadata)} hosts, "
                        f"{len(obj.principal_metadata)} principals ← {sqlite_p}")
            return obj

        # Pickle fallback
        pkl_p = obj._cache_path(cache_root)
        if pkl_p.exists():
            with open(pkl_p, "rb") as f:
                data = pickle.load(f)
            obj._mode = "memory"
            obj._dict = data["dict"]
            obj._stats = data.get("stats", {})
            obj._entry_count = data.get("entry_count", len(obj._dict))  # type: ignore
            obj._finalized = True
            logger.info(f"Loaded (memory): {obj._entry_count} entries, "
                        f"{len(obj.host_metadata)} hosts, "
                        f"{len(obj.principal_metadata)} principals ← {pkl_p}")
            return obj

        return None

    def close(self):
        """Close SQLite connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()


# Pass 1 collection functions
def _collect_cdm(
    rec: dict[str, Any],
    buf: dict[str, _CollectionEntry],
    host_metadata: dict[str, HostInfo],
    principal_metadata: dict[str, PrincipalInfo],
) -> int:
    """Process one cdm record during pass 1. Returns 1 if skipped, 0 if collected."""
    datum = rec.get("datum")
    if not datum:
        return 1
    record_type = next(iter(datum), "")
    record_type_short = record_type.rsplit(".", 1)[-1]

    if record_type_short not in CDM_KEEP_RECORD_TYPES:
        return 1

    record_value = datum[record_type]
    uuid_str = record_value.get("uuid")
    if not uuid_str:
        # Principal records in some datasets might not have uuid at top level
        if record_type_short == "Principal":
            return 1
        return 1
    uuid_str = uuid_str.upper()

    # Principal records: store in side dict, dont go into main buf
    if record_type_short == "Principal":
        if uuid_str not in principal_metadata:
            # cdm18 Principal has userId, groupIds fields
            # cdm20 may differ slightly but the fields are similar
            user_id = _extract_string(record_value.get("userId"))
            username = _extract_string(record_value.get("username"))
            group_ids_raw = record_value.get("groupIds")
            group_ids = None
            if isinstance(group_ids_raw, dict):
                group_ids = group_ids_raw.get("array")
            elif isinstance(group_ids_raw, list):
                group_ids = group_ids_raw

            principal_metadata[uuid_str] = PrincipalInfo(
                uuid=uuid_str,
                user_id=user_id,
                username=username,
                group_ids=group_ids,
            )
        return 0

    # Host records: store in side dict AND in main buf (for uuid resolution)
    if record_type_short == "Host":
        if uuid_str not in host_metadata:
            hostname = record_value.get("hostName", "")
            os_details = _extract_string(record_value.get("osDetails")) or ""
            host_type = record_value.get("hostType", "")

            # Extract interfaces (cdm18: list directly, cdm20: {"array": [...]})
            ifaces_raw = record_value.get("interfaces")
            if isinstance(ifaces_raw, dict):
                ifaces_raw = ifaces_raw.get("array", [])
            interfaces = []
            if isinstance(ifaces_raw, list):
                for iface in ifaces_raw:
                    if isinstance(iface, dict):
                        ips = iface.get("ipAddresses", [])
                        if isinstance(ips, dict):
                            ips = ips.get("array", [])
                        interfaces.append({
                            "name": iface.get("name", ""),
                            "macAddress": iface.get("macAddress", ""),
                            "ipAddresses": ips if isinstance(ips, list) else [],
                        })

            host_metadata[uuid_str] = HostInfo(
                uuid=uuid_str,
                hostname=hostname,
                os_details=os_details,
                host_type=host_type,
                interfaces=interfaces,
            )

        # Also register in main buf for uuid lookups
        if uuid_str not in buf:
            buf[uuid_str] = _CollectionEntry()
        buf[uuid_str].observed_types.add("Host")
        return 0

    # Standard record types: Subject, FileObject, NetFlowObject, RegistryKeyObject
    if uuid_str not in buf:
        buf[uuid_str] = _CollectionEntry()
    entry = buf[uuid_str]

    if record_type_short == "Subject":
        subj_type = record_value.get("type", "")
        entry.observed_types.add(f"Subject({subj_type})")

        parent = record_value.get("parentSubject")
        if isinstance(parent, dict):
            parent = next(iter(parent.values()), None)
        if parent and isinstance(parent, str):
            entry.parent_uuid_str = parent.upper()

        # localPrincipal -> user uuid
        principal_ref = record_value.get("localPrincipal")
        if isinstance(principal_ref, dict):
            principal_ref = next(iter(principal_ref.values()), None)
        if principal_ref and isinstance(principal_ref, str):
            entry.principal_uuid_str = principal_ref.upper()

        entry.cmdline = entry.cmdline or _extract_string(record_value.get("cmdLine"))
        entry.pid = entry.pid or _extract_int(record_value.get("cid"))

        props = record_value.get("properties")
        if isinstance(props, dict):
            props = props.get("map", props)
            if not entry.cmdline and "path" in props:
                entry.cmdline = props["path"]
            if not entry.pid and "tgid" in props:
                entry.pid = _extract_int(props.get("tgid"))

    elif record_type_short == "FileObject":
        file_type = record_value.get("type", "")
        entry.observed_types.add(f"FileObject({file_type})")
        base = record_value.get("baseObject", {})
        props = base.get("properties") if base else None
        if isinstance(props, dict):
            props = props.get("map", props)
            entry.path = entry.path or props.get("path") or props.get("filename")

    elif record_type_short == "NetFlowObject":
        entry.observed_types.add("NetFlowObject")
        entry.ip = entry.ip or record_value.get("remoteAddress")
        entry.port = entry.port or _extract_int(record_value.get("remotePort"))
        if not entry.path:
            entry.path = record_value.get("localAddress")

    elif record_type_short == "RegistryKeyObject":
        entry.observed_types.add("RegistryKeyObject")
        base = record_value.get("baseObject", {})
        props = base.get("properties") if base else None
        if isinstance(props, dict):
            props = props.get("map", props)
            entry.path = entry.path or props.get("key")

    return 0


def _collect_optc(rec: dict[str, Any], buf: dict[str, _CollectionEntry]) -> int:
    """Process one OpTC record during pass 1. Returns 1 if skipped, 0 if collected."""
    obj_type = rec.get("object", "")
    actor_id = rec.get("actorID")
    object_id = rec.get("objectID")
    props = rec.get("properties", {}) or {}
    collected = False

    if actor_id:
        actor_id = actor_id.upper()
        if actor_id not in buf:
            buf[actor_id] = _CollectionEntry()
        ae = buf[actor_id]
        ae.observed_types.add("PROCESS")
        ae.cmdline = ae.cmdline or props.get("image_path")
        ae.pid = ae.pid or _extract_int(rec.get("pid"))
        collected = True

    if object_id and obj_type in OPTC_KEEP_OBJECT_TYPES:
        object_id = object_id.upper()
        if object_id not in buf:
            buf[object_id] = _CollectionEntry()
        oe = buf[object_id]
        oe.observed_types.add(obj_type)
        if obj_type in ("FILE", "MODULE"):
            oe.path = oe.path or props.get("file_path")
        elif obj_type == "FLOW":
            oe.ip = oe.ip or props.get("dest_ip") or props.get("src_ip")
            oe.port = oe.port or _extract_int(props.get("dest_port"))
        elif obj_type == "PROCESS":
            oe.cmdline = oe.cmdline or props.get("image_path")
            oe.pid = oe.pid or _extract_int(rec.get("pid"))
        elif obj_type == "REGISTRY":
            oe.path = oe.path or props.get("key") or props.get("value")
        collected = True

    return 0 if collected else 1



# Staging DB helpers (for incremental flush during pass 1)
def _create_staging_db(staging_path: Path) -> sqlite3.Connection:
    """Create a fresh staging SQLite DB for incremental flushing."""
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    if staging_path.exists():
        staging_path.unlink()
    conn = sqlite3.connect(str(staging_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    # Staging table stores raw strings - no role resolution yet.
    # Multiple rows per uuid are expected; they get merged during finalization.
    conn.execute(
        "CREATE TABLE staging ("
        "uuid_hex TEXT NOT NULL, "
        "types_csv TEXT, "
        "path TEXT, ip TEXT, port INTEGER, "
        "cmdline TEXT, parent_uuid_hex TEXT, pid INTEGER, "
        "principal_uuid_hex TEXT)"
    )
    # Index on uuid_hex for faster GROUP BY during finalization
    conn.execute("CREATE INDEX idx_staging_uuid ON staging(uuid_hex)")
    return conn


def _flush_buf_to_staging(buf: dict[str, _CollectionEntry], conn: sqlite3.Connection) -> None:
    """
    Flush the in-memory collection buffer to the staging table.

    Each _CollectionEntry becomes one row. If the same uuid was already
    flushed in a prior round, it'll be a second row - the GROUP BY
    in _finalize_from_staging merges them.
    """
    batch = []
    for uuid_str, entry in buf.items():
        types_csv = ",".join(sorted(entry.observed_types)) if entry.observed_types else ""
        batch.append((
            uuid_str,
            types_csv,
            entry.path if isinstance(entry.path, (str, type(None))) else _extract_string(entry.path),
            entry.ip if isinstance(entry.ip, (str, type(None))) else _extract_string(entry.ip),
            entry.port,
            entry.cmdline if isinstance(entry.cmdline, (str, type(None))) else _extract_string(entry.cmdline),
            entry.parent_uuid_str,
            entry.pid,
            entry.principal_uuid_str,
        ))
        if len(batch) >= 100_000:
            conn.executemany(
                "INSERT INTO staging VALUES (?,?,?,?,?,?,?,?,?)", batch
            )
            batch.clear()

    if batch:
        conn.executemany("INSERT INTO staging VALUES (?,?,?,?,?,?,?,?,?)", batch)
    conn.commit()


# other helpers
def _count_role(stats: dict[str, int], role: int, ambiguous: bool) -> None:
    name = {1: "FILE", 2: "SOCKET", 3: "PROCESS", 4: "EXECUTABLE"}.get(role, "UNKNOWN")
    stats[name] = stats.get(name, 0) + 1
    if ambiguous:
        stats["ambiguous"] = stats.get("ambiguous", 0) + 1


def _extract_string(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("string") or val.get("str") or next(iter(val.values()), None)
    return str(val)


def _extract_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, dict):
        # Check each key explicitly - dont use or which treats 0 as falsy
        for key in ("int", "long"):
            v = val.get(key)
            if v is not None:
                try:
                    return int(v)
                except (ValueError, TypeError):
                    pass
        # Fallback: try first value in the dict
        v = next(iter(val.values()), None)
        if v is not None:
            try:
                return int(v)
            except (ValueError, TypeError):
                pass
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
"""
Neo4j instance manager for GWDG HPC + Apptainer.

Each (dataset, sub_dataset, time_window) gets its own isolated data directory under $WS_NEO4J_PATH/instances/.
This manager handles directory creation, apptainer start/stop, bolt readiness, and initial password setting.

Shared components are:
    $WS_NEO4J_PATH/conf/
    $WS_NEO4J_PATH/plugins/
    $WS_NEO4J_PATH/neo4j.sif

Per-instance components are created automatically:
    $WS_NEO4J_PATH/instances/<name>/data/
    $WS_NEO4J_PATH/instances/<name>/logs/
    $WS_NEO4J_PATH/instances/<name>/run/
    $WS_NEO4J_PATH/instances/<name>/import/
"""

from __future__ import annotations

from provenance_explorer.registry.registry_all import WORK, DATA_NE04J
import logging
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from neo4j import Driver, GraphDatabase, basic_auth

logger = logging.getLogger(__name__)


def _ns_to_dirname_part(ns: int) -> str:
    """Convert ns timestamp to ISO-ish string: 20180405T100000 for filesystem"""
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%S")

def instance_dir_name(dataset: str, sub_dataset: str, t_start_ns: int, t_end_ns: int) -> str:
    """
    Build the directory name for an instance.

    Format: {dataset}_{sub_dataset}__{start}__{end}
    Example: e3_cadets__20180405T100000__20180408T223000
    """
    start = _ns_to_dirname_part(t_start_ns)
    end = _ns_to_dirname_part(t_end_ns)
    return f"{dataset}_{sub_dataset}__{start}__{end}"


def parse_instance_name(name: str) -> Optional["ParsedInstance"]:
    """
    Invert instance_dir_name: pull (dataset, sub_dataset, t_start_ns, t_end_ns) out
    of an instance directory name. Returns None on malformed input.

    sub_dataset may itself contain underscores (e.g. "aia_201_225"), so we split
    on the "__" delimiter first.
    """
    from datetime import datetime, timezone

    parts = name.split("__")
    if len(parts) != 3:
        return None
    prefix, start_s, end_s = parts
    if "_" not in prefix:
        return None
    dataset, sub_dataset = prefix.split("_", 1)
    try:
        start_dt = datetime.strptime(start_s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return ParsedInstance(
        dataset=dataset,
        sub_dataset=sub_dataset,
        t_start_ns=int(start_dt.timestamp() * 1_000_000_000),
        t_end_ns=int(end_dt.timestamp() * 1_000_000_000),
    )


@dataclass(frozen=True)
class ParsedInstance:
    dataset: str
    sub_dataset: str
    t_start_ns: int
    t_end_ns: int

@dataclass
class InstanceInfo:
    """instance directory data"""
    name: str
    path: Path

class Neo4jInstanceManager:
    """
    Manages Neo4j Community Edition instances running inside Apptainer.
    Only one instance can run at a time; TODO: maybe port management for more instances (?).
    """
    def __init__(
        self,
        bolt_host: str = "localhost",
        bolt_port: int = 7687,
        http_port: int = 7474,
        password: str = "test1234",
        startup_timeout_s: float = 180.0,
        startup_poll_interval_s: float = 1.0,
    ):
        self.ws_neo4j_path = DATA_NE04J
        self.sif_path = self.ws_neo4j_path / "neo4j.sif"
        self.conf_path = self.ws_neo4j_path / "conf"
        self.plugins_path = self.ws_neo4j_path / "plugins"
        self.instances_root = self.ws_neo4j_path / "instances"

        self.bolt_host = bolt_host
        self.bolt_port = bolt_port
        self.http_port = http_port
        self.password = password
        self.startup_timeout_s = startup_timeout_s
        self.startup_poll_interval_s = startup_poll_interval_s

        self._current_instance: Optional[Path] = None
        self._process: Optional[subprocess.Popen] = None

    # directory management
    def create_instance(
        self,
        dataset: str,
        sub_dataset: str,
        t_start_ns: int,
        t_end_ns: int,
    ) -> Path:
        """
        Create (or return existing) instance directories.
        """
        name = instance_dir_name(dataset, sub_dataset, t_start_ns, t_end_ns)
        inst_path = self.instances_root / name

        for subdir in ("data", "logs", "run", "import"):
            (inst_path / subdir).mkdir(parents=True, exist_ok=True)

        logger.info("Instance directory ready: %s", inst_path)
        return inst_path

    def list_instances(self) -> List[InstanceInfo]:
        """List availbale instance directories with basic metadata."""
        if not self.instances_root.exists():
            return []

        results = []
        for p in sorted(self.instances_root.iterdir()):
            if p.is_dir(): # and (p / "data").exists(): # TODO quick check if instance is credibly populated, otherwise list as broken
                results.append(InstanceInfo(name=p.name, path=p))
        return results

    def delete_instance(self, instance_path: Path) -> None:
        """remove an instance directory"""
        if instance_path.exists():
            shutil.rmtree(instance_path)
            logger.info("Deleted instance: %s", instance_path)

    # Lifecycle: start / stop
    def _build_apptainer_cmd(self, instance_path: Path, *neo4j_cmd: str) -> List[str]:
        """build the apptainer exec command with all bind mounts"""
        return [
            "apptainer", "exec",
            "--bind", f"{instance_path / 'data'}:/var/lib/neo4j/data",
            "--bind", f"{instance_path / 'logs'}:/var/lib/neo4j/logs",
            "--bind", f"{instance_path / 'run'}:/var/lib/neo4j/run",
            "--bind", f"{instance_path / 'import'}:/var/lib/neo4j/import",
            "--bind", f"{self.plugins_path}:/var/lib/neo4j/plugins",
            "--bind", f"{self.conf_path}:/var/lib/neo4j/conf",
            str(self.sif_path),
            *neo4j_cmd,
        ]

    def _set_initial_password(self, instance_path: Path) -> None:
        """
        Set the initial password for a fresh Neo4j instance.
        """
        auth_dir = instance_path / "data" / "dbms"
        if (auth_dir / "auth").exists():
            return  # already configured

        cmd = [
            "apptainer", "exec",
            "--bind", f"{instance_path / 'data'}:/var/lib/neo4j/data",
            "--bind", f"{self.conf_path}:/var/lib/neo4j/conf",
            str(self.sif_path),
            "/var/lib/neo4j/bin/neo4j-admin",
            "dbms", "set-initial-password", self.password,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.info("Initial password set for %s", instance_path.name)
            else:
                logger.warning(
                    "set-initial-password returned %d: %s",
                    result.returncode, result.stderr.strip(),
                )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Could not set initial password: %s", e)

    def start(self, instance_path: Path) -> None:
        """
        Blocking; start Neo4j for the given instance. 
        Raises RuntimeError if another instance is already running.
        """
        if self._process is not None and self._process.poll() is None:
            raise RuntimeError(
                f"Neo4j already running (PID {self._process.pid}).  "
                f"Call stop() first."
            )

        self._set_initial_password(instance_path)

        cmd = self._build_apptainer_cmd(instance_path, "/var/lib/neo4j/bin/neo4j", "console")

        log_file = instance_path / "logs" / "neo4j_startup.log"
        fh = open(log_file, "w")  # only closed when the process terminates # TODO explicit close 

        logger.info("Starting Neo4j for %s ...", instance_path.name)
        self._process = subprocess.Popen(
            cmd,
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
        self._current_instance = instance_path

        # wait for bolt
        self._wait_for_bolt()
        logger.info("Neo4j ready on bolt://%s:%d", self.bolt_host, self.bolt_port)

    def stop(self) -> None:
        """Stop the running Neo4j instance."""
        if self._current_instance is None:
            logger.warning("No instance currently running.")
            return

        cmd = self._build_apptainer_cmd(
            self._current_instance, "/var/lib/neo4j/bin/neo4j", "stop"
        )

        logger.info("Stopping Neo4j for %s ...", self._current_instance.name)
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("neo4j stop timed out, terminating process")

        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        self._current_instance = None
        logger.info("Neo4j stopped.")

    def get_driver(self) -> Driver:
        """
        Return a Neo4j driver connected to the currently running instance.
        Here the callers themselfes are responsible for closing the driver.
        """
        uri = f"bolt://{self.bolt_host}:{self.bolt_port}"
        return GraphDatabase.driver(
            uri,
            auth=basic_auth("neo4j", self.password),
            connection_acquisition_timeout=60.0,
            connection_timeout=30.0,
            max_transaction_retry_time=180.0,
        )

    # wait:
    def _wait_for_bolt(self) -> None:
        """Poll the bolt port until it accepts connections or timeout."""
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            # check the process hasnt died
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"Neo4j process exited with code {self._process.returncode} "
                    f"during startup.  Check logs."
                )
            try:
                with socket.create_connection(
                    (self.bolt_host, self.bolt_port), timeout=2.0
                ):
                    return # Neo4j is ready
            except (ConnectionRefusedError, socket.timeout, OSError):
                time.sleep(self.startup_poll_interval_s)

        raise RuntimeError(
            f"Neo4j did not become ready within {self.startup_timeout_s}s."
            f"Check {self._current_instance}/logs/"
        )
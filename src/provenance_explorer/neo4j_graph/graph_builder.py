"""
Graph builder - the main orchestrator.

Depends on:
    - ObjectLookup (metadata for hosts & principals)
    - CommonRecord iterator (event stream for a time window)
    - GraphIngester (batched Cypher execution)
    - Neo4jInstanceManager (neo4j apptainer & folder management/ startup)

Usage:
    from pathlib import Path
    from provenance_explorer.neo4j_graph import GraphBuilder
    from provenance_explorer.utils.time_conversion import date_string_to_ns_timestamp
    import logging
    logging.basicConfig(
        level=logging.INFO,  # or DEBUG for more detail
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    start_ns = date_string_to_ns_timestamp("2018-04-05 00:00:00")
    end_ns = date_string_to_ns_timestamp("2018-04-06 00:00:00")

    builder = GraphBuilder(
        dataset="e3",
        sub_dataset="cadets",
        t_start_ns=start_ns,
        t_end_ns=end_ns,
    )
    builder.build()
    # Neo4j remains running for exploration; call builder.teardown() when done; this will stop neo4j 
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from provenance_explorer.registry.registry_all import WORK
from provenance_explorer.common_record import iterate_common_records, drop_log
from provenance_explorer.common_record import object_lookup

from .cypher_templates import build_index_statements
from .ingestion import GraphIngester
from .instance_manager import Neo4jInstanceManager

logger = logging.getLogger(__name__)

class GraphBuilder:
    """
    Build a Neo4j provenance graph for a (dataset, sub_dataset, time_window).

    Each call to :meth:`build` creates an isolated Neo4j instance with its own data directory, 
    populates metadata nodes from the ObjectLookup, then streams CommonRecords into the graph.
    """

    def __init__(
        self,
        dataset: str,
        sub_dataset: str,
        t_start_ns: int,
        t_end_ns: int,
        neo4j_password: str = "test1234",
        flush_threshold: int = 500_000,
        chunk_size: int = 50_000,
        progress_interval: int = 10_000_000,
    ):
        self.dataset = dataset
        self.sub_dataset = sub_dataset
        self.t_start_ns = t_start_ns
        self.t_end_ns = t_end_ns
        self.cache_dir = WORK / "provenance-explorer-cache"

        self.flush_threshold = flush_threshold
        self.chunk_size = chunk_size
        self.progress_interval = progress_interval

        self._manager = Neo4jInstanceManager(password=neo4j_password,)
        self._driver = None
        self._instance_path: Optional[Path] = None

    # public API
    def build(self) -> None:
        """
        Full pipeline: 
            1. create instance
            2. start Neo4j
            3. create indexes
            4. pre-populate metadata
            5. stream events
            6. flush
            X. report
        """
        t_total_start = time.monotonic()

        # 1. Load ObjectLookup
        logger.info("Loading ObjectLookup for %s/%s ...", self.dataset, self.sub_dataset)
        lookup = object_lookup.ObjectLookup.load(
            self.dataset, self.sub_dataset, self.cache_dir
        )
        if lookup is None:
            raise RuntimeError(
                f"ObjectLookup not found for {self.dataset}/{self.sub_dataset} "
                f"in {self.cache_dir}; needs to be bulit first."
            )

        # 2. Create instance directory & start Neo4j
        self._instance_path = self._manager.create_instance(
            self.dataset, self.sub_dataset, self.t_start_ns, self.t_end_ns,
        )
        self._manager.start(self._instance_path)
        self._driver = self._manager.get_driver()

        try:
            # 3. Create indexes and constraints
            self._create_indexes()

            # 4. Pre-populate metadata nodes
            ingester = GraphIngester(
                self._driver,
                chunk_size=self.chunk_size,
            )
            self._prepopulate_metadata(ingester, lookup)

            # 5. Main ingestion loop
            self._ingest_events(ingester)

            # Print report
            logger.info("Build complete in %.1fs\n%s", time.monotonic() - t_total_start, ingester.stats.summary(),)

        except Exception:
            logger.exception("Build failed; Neo4j still left running.")
            raise

    def teardown(self) -> None:
        """close & stop Neo4j."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
        self._manager.stop()


    # Internal steps
    def _create_indexes(self) -> None:
        """for running all (IF NOT EXISTS) index/constraint creation statements."""
        stmts = build_index_statements()
        assert self._driver is not None
        with self._driver.session(database="neo4j") as session:
            for stmt in stmts:
                try:
                    session.run(stmt).consume() # type: ignore
                except Exception as e:
                    # Some indexes may already exist; log and continue
                    logger.warning("Index creation warning: %s — %s", stmt[:60], e)
        logger.info("Created %d indexes/constraints.", len(stmts))

    def _prepopulate_metadata(self, ingester: GraphIngester, lookup: object_lookup.ObjectLookup) -> None:
        """
        Insert (Host, User, IPAddress nodes, hasHostIP edges) from ObjectLookup before the main loop.
        """
        # Host rows
        host_rows: List[Dict] = []
        host_ip_rows: List[Dict] = []

        host_metadata: dict = lookup.host_metadata 
        for _uuid, host_info in host_metadata.items():
            host_rows.append({
                "uuid": host_info.uuid,
                "hostname": getattr(host_info, "hostname", None),
                "os_details": getattr(host_info, "os_details", None),
                "host_type": getattr(host_info, "host_type", None),
            })
            # extract IPs from interfaces
            for iface in getattr(host_info, "interfaces", []) or []:
                for ip_addr in iface.get("ipAddresses", []):
                    clean_ip = ip_addr.split("%")[0] if "%" in ip_addr else ip_addr
                    host_ip_rows.append({
                        "src_uuid": host_info.uuid,
                        "dst_ip": clean_ip,
                    })

        # user rows
        user_rows: List[Dict] = []
        principal_metadata = lookup.principal_metadata
        for _uuid, principal_info in principal_metadata.items():
            user_rows.append({
                "uuid": principal_info.uuid,
                "username": getattr(principal_info, "username", None),
                "user_id": getattr(principal_info, "user_id", None),
            })

        ingester.flush_metadata_nodes(host_rows, user_rows, host_ip_rows)

    def _ingest_events(self, ingester: GraphIngester) -> None:
        """Stream CommonRecords for the time window through the ingester."""
        logger.info(
            "Starting event ingestion for %s/%s [%d .. %d] ...",
            self.dataset, self.sub_dataset, self.t_start_ns, self.t_end_ns,
        )

        dlog = drop_log.DropLog()
        iterator = iterate_common_records(
            self.dataset,
            self.sub_dataset,
            drop_log=dlog,
            t_start=self.t_start_ns,
            t_end=self.t_end_ns,
        )

        count = 0
        for record in iterator:
            ingester.ingest(record)
            count += 1

            if ingester.pending_count >= self.flush_threshold:
                ingester.flush()

            if count % self.progress_interval == 0:
                logger.info(
                    "  ... %d records processed (%d pending)",
                    count, ingester.pending_count,
                )

        # Final flush
        ingester.flush()

        logger.info("Event ingestion done: %d records from iterator.", count)
        dlog.summary(self.dataset, self.sub_dataset)
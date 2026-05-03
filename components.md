# Provenance Benchmark Explorer Package

## Download
Under `src/provenance_explorer/download`, functions for downloading and extracting the data files and according labels are found: 
- `/src/provenance_explorer/download/darpa_downloads.py` : download & conversion
- `/src/provenance_explorer/download/darpa_label_downloads.py` : label downloads
- `/src/provenance_explorer/download/gdrive.py` : gdrive interaction to enable massive downloads

## Registry: 
Under `src/provenance_explorer/registry` data structures containing necessary metadata when interacting with the files are contained. 
- `./src/provenance_explorer/registry/attack_registry_e3.py` : attack slices in E3 Sub Datasets; as dict with {("<start_str>", "<end_str>"): {"description":"", "report_section":"", "tactics":[<tactic>, ...], "labels":{"<label_set>":"<relative_path>"}}}
- `./src/provenance_explorer/registry/attack_registry_e5.py` : attack slices in E5 Sub Datasets; as dict as above
- `./src/provenance_explorer/registry/attack_registry_optc.py` : attack slices in OpTC Dataset; as dict as above
- `./src/provenance_explorer/registry/attack_data.py` : summary class for attack windows containing AttackWindow data class. 
- `./src/provenance_explorer/registry/darpa_e3_registry.py` : metadata for interacting with the raw E3 files
- `./src/provenance_explorer/registry/darpa_e5_registry.py` : metadata for interacting with the raw E5 files
- `./src/provenance_explorer/registry/darpa_optc_registry.py` : metadata for interacting with the raw OpTC files
- `./src/provenance_explorer/registry/registry_all.py` : Summary and helper Functions; paths used throughout are 
    - WORK (= $WORK) for the plot cache directory and the object lookups (additionally defined as CACHE_ROOT)
    - DATA_RAW (=$WS_RAW_PATH) for the raw data files
    - DATA_NEO4J (=$WS_NEO4J_PATH) for the insatnces, apptainer file and darpa labels (additionally defined as DARPA_LABEL_PATH)
    - FIGURES_ROOT for the /img folder where all visualizations should be written

## Raw File Handling
Under `src/provenance_explorer/raw_file_handling` all functions for interacting with the raw DARPA datasets live:
- `./src/provenance_explorer/raw_file_handling/dataset_iterator.py` : The core piece for interacting with the raw files; an iterator taking in a timespan, a timestamp extractor, a parsing function and the corresponding dataset registry, to yield records from that timespan. Built with `make_dataset_iterator(...)`
- `./src/provenance_explorer/raw_file_handling/file_annotations.py` : Metadata extraction function for the individual files; used to build the registries. 
- `./src/provenance_explorer/raw_file_handling/parsing_helpers.py` : Functions that can be included for parsing log lines in the individual files. 

## Common Record
Under `src/provenance_explorer/common_record` all functions, schemas and objects for iterating through the data on a unified scheme are defined: 
- `./src/provenance_explorer/common_record/common_record_iterator.py` : Core piece; with iterate_common_records(dataset, sub_dataset, drop_log, t_start, t_end) an iterator yielding unified records is defined, logging excluded lines to a DropLog. 
- `./src/provenance_explorer/common_record/dispatch.py` : mapping logic from individual raw records to common record. 
- `./src/provenance_explorer/common_record/drop_log.py` : object for logging dropped events and keeping statistics of iteration.
- `./src/provenance_explorer/common_record/object_lookup.py` : necessary part for record validation; builds and returns data structures used in validating that e.g. a 'read' event actually connects something readable with a process. 
- `./src/provenance_explorer/common_record/schema.py` : Enums and Dataclasses used throughout the sub-package. 

## Neo4j Graph
Under `src/provenance_explorer/neo4j_graph` functions and a schema for managing and creating apptainer neo4j (community edition) instances for time windows. 
- `./src/provenance_explorer/neo4j_graph/cypher_templates.py` : query templates for graph construction; importantly also contains build_index_statements() for initializing the databases so they can be used quickly.
- `./src/provenance_explorer/neo4j_graph/graph_builder.py` : orchestrates object lookup + common record + grpah ingester and the instance manager to build a graph for a timespan
- `./src/provenance_explorer/neo4j_graph/ingestion.py` : manages accumulation and preparation of big cypher insertions
- `./src/provenance_explorer/neo4j_graph/instance_manager.py` : manages paths, overlap and start/ stop of neo4j container and instance data directories; one Apptainer-hosted Neo4j per `(dataset, sub_dataset, t_start_ns, t_end_ns)` slice. Starts/stops via `apptainer exec`, binds per-instance `data/logs/run/import` dirs, shared `conf/plugins/neo4j.sif`. Default bolt 7687 / http 7474, password `test1234`. 
- `./src/provenance_explorer/neo4j_graph/annotator.py` : annotate graph with (for now only node) labels from different label sources; also exposes read-only helpers used by threat_coverage: `fetch_window_active_uuids(driver, host_uuid, t_start_ns, t_end_ns)` (host-scoped uuid set in a half-open event-timestamp range), `fetch_host_anytime_uuids(driver, host_uuid)` (any time on host), and `fetch_existing_uuids(driver, uuids)` (which of a given uuid set is instantiated as nodes in the current instance).
- `./src/provenance_explorer/neo4j_graph/schema.py` : the information flow direction adjusted common schema (i.e. Process-'reads'-File becomes File<-'isReadBy'-Process)
- `./src/provenance_explorer/neo4j_graph/metrics.py` 

## Plotting
Under `src/provenance_explorer/plotting` a pipeline to be implemented by actual analysis logic is defined, to force users to keep plots consistent and re-runnable without expensive dataset iterations.
- `./src/provenance_explorer/plotting/cache.py` : implements functions saving data retreived for a plot. 
- `./src/provenance_explorer/plotting/style.mplstyle` : style sheet for consisttent plots
- `./src/provenance_explorer/plotting/config.py` : functions for loading style sheet components
- `./src/provenance_explorer/plotting/pipeline.py` : abstract class to be implemented by analyses runs 
- `./src/provenance_explorer/plotting/template_plot.py` : template example

## Analysis
Under `src/provenance_explorer/analysis` live the implemented plots used throughout the assessment of the benchmark datasets. They are spread throughout the categories 'provenance capture', 'system scale', 'threat coverage' and 'activity realism'. 
- `./src/provenance_explorer/analysis/activity_realism/activity_evolution/evolution_metrics.py` : evolution metric calculation, namely 'n_unique_normalized_cmdlines' and 'saturation_auc_unit'
- `./src/provenance_explorer/analysis/activity_realism/activity_evolution/cmdline_normalization.py` : normalization functions used in evolution metrics
- `./src/provenance_explorer/analysis/activity_realism/activity_evolution/evolution_plot.py` : plot for (unnormalized) saturation curve 
- `./src/provenance_explorer/analysis/activity_realism/activity_regularity/mttkrp_helpers.py` : helpers for building a NTF decomposition of a temporal graph expressed as tensor of adjacency slices. 
- `./src/provenance_explorer/analysis/activity_realism/activity_regularity/ntf_decomposition_plot.py` : plot showing density and a time aggreagted view of an NTF decomposition.
- `./src/provenance_explorer/analysis/provenance_capture/correctness.py` : functions for computing '% gaps per host' and 'Timing errors per host', which depend on a full run of a volumetrics plot. 
- `./src/provenance_explorer/analysis/provenance_capture/data_model_types_plot.py` : plot for sweep across all sub datasets of a dataset to determine relative occurences of different type+subtype combinations for the Data Models natively in the datasets (CDM18, CDM20, eCAR)
- `./src/provenance_explorer/analysis/provenance_capture/dataset_timespans_plot.py` : plot for timespans covered by single files in the datasets.
- `./src/provenance_explorer/analysis/provenance_capture/timestamp_disorder_plot.py` : bars for timing errors throughout the datasets. 
- `./src/provenance_explorer/analysis/threat_coverage/attack_window_table.py` : builds the per-attack-window coverage table and exclusions sidecar. One row per `AttackWindow` from `registry.attack_data`; per-source columns (PM/FL/WW/RV) report the drop funnel `labelset_size_<src>` → `l1_<src>` (in object_lookup) → `l2_<src>` (node in graph) → `l3a_<src>` (ever on host) → `l3b_<src>` (on host in padded instance range) → `matched_<src>` (on host in unpadded window), plus `label_files_<src>`, `pct_of_labelset_<src>`, `base_rate_<src>` (matched/total), and `authors_intended_<src>`. Also emits `total_nodes`, `local_base_rate`, and instance bounds `inst_t_start_ns`/`inst_t_end_ns` for padding diagnostics. WWTAWWTAL is filtered per `report_sec` via the `attack_chain` column; other sources use the whole-file UUID set. Returns `(windows_df, exclusions_df)`; the second frame is the L1\L2 shortlist (uuid passes common-model type filter but no node exists in graph — the event-type-filter H3b candidates), capped at 500 uuids per (window, source). Windows missing `host_uuid` in the registry or without a matching Neo4j instance are emitted with a `skip_reason`.
- `./src/provenance_explorer/analysis/system_scale/event_per_host.py` : host-aware sweep through sub-datasets to get densities of events across timeline
- `./src/provenance_explorer/analysis/system_scale/volumetrics.py` : metrics for events/s and information_flow_events/s 
- `./src/provenance_explorer/analysis/system_scale/workload_variability.py` : discrete HMM estimation of workload regimes in a dataset, based on event frequencies. 

# Connecting Scripts and Notebooks

## Scripts

Under `scripts/`, various pieces of the package are put together: 

- `scripts/build_attack_neo4j_graphs.py` : run build & ingestion of neo4j instances for attack slices defined in src.registry.attack_data
- `scripts/build_attack_window_table.py` : starts each attack-window instance once, runs the threat_coverage window-scoped queries, and writes `$WORK/threat_coverage/attack_windows.{parquet,csv}` (main funnel table) and `$WORK/threat_coverage/attack_window_exclusions.{parquet,csv}` (per-uuid sidecar for the L1\L2 exclusion shortlist).
- `scripts/explore_graph.py` : utility script for firing up instances and annotating with labels
- `scripts/run_download.py` : utility script for runnning download of whole datasets (e3, e5 or optc)
- `scripts/get_e5_samples.py` : get samples of various object types and subtypes for E5 (CDM20)
- `scripts/get_optc_samples.py` : same as above, but for OpTC (eCAR)
- `scripts/get_information_flow_semantics.py` : get samples of which object types are connected by what event types for CDM 18 and CDM 20 datasets (E3 and E5)
- `scripts/get_information_flow_semantics_ecar.py` : same as above, but for eCAR (OpTC)
- `scripts/hpc_monitoring/* `: scripts for monitoring a HPC login node to get data for comparing the datasets to production data
- `scripts/slurm/*` submit scripts for long running actions like building a graph or calculating an expensive plot

## Notebooks

Under `notebooks/`, analysis and API components are connected to gain insight or demonstrate how the repository works.
- `notebooks/activity_regularity_demo.ipynb` : script showing the concept of the NTF analysis on a sample tensor with synthetic structures
`notebooks/demo/common_record_tools_demo.ipynb` : demo of common record iterator
`notebooks/demo/raw_file_handling_demo.ipynb` : demo of raw record iterator and other raw file interactions
- `notebooks/per_host_metrics.ipynb` : notebook combining various metric into a big dataset|sub_dataset|host|{provenance capture metrics}|{system scale metrics}|{activity realism metrics}|{attack coverage metrics}
- `notebooks/secondary_plots.ipynb` : plots derived data from big data sweep plots found in `src/analysis/`
- `notebooks/thesis_plots.ipynb` : plots that are derived and e.g. miss titles or are more specific as they are included in the accompanying thesis
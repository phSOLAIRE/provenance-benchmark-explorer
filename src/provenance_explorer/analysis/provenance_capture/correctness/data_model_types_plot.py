"""
DataModelTypesPlot
Go through all sub datasets of a certain data model
    - "cdm18" => all E3 Datasets
    - "cdm20" => all E5 Datasets
    - "ecar" => all OpTC Datasets
and plot Types and Subtypes relative occurences, where applicable.
Collects the data by iterating over every full dataset and writing the summary statistics as

nested json
    dict[str, dict[str, dict[str, int]]]
    meaning: {'sub_dataset': {'type': {'subtype': <int absolute count>}}}

Displays the data as a table with percentages in each sub dataset: <sub_dataset> x <type_subtype> -> subtype percentage relative to whole subdataset

Example usage in notebook: 

    from provenance_explorer.analysis.provenance_capture.correctness.data_model_types_plot import DataModelTypesPlot
    from provenance_explorer.plotting import apply_style

    apply_style()
    plot = DataModelTypesPlot()
    # plot.invalidate(data_model = "cdm18") # cache invalidate for recalculating
    fig  = plot.run(data_model = "cdm18")
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline
from provenance_explorer.registry.registry_all import get_big_registry
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator
from provenance_explorer.raw_file_handling.parsing_helpers import TS_EXTRACTORS, PARSERS

from pprint import pprint
from multiprocessing import Pool

def _process_one_subdataset_cdm20(
    subdataset_name: str,
) -> tuple[str, dict[str, dict[str, int]]]:
    """
    Worker function for one sub-dataset. Must be top-level for pickling.
    Rebuilds the registry internally to avoid pickling complex objects.
    """
    print(f"\t[processing sub dataset] {subdataset_name}")
    all_cdm20_registry = get_big_registry("e5")
    subdataset_registry = all_cdm20_registry[subdataset_name]
    ts_extr = TS_EXTRACTORS[("e5", subdataset_name)]
    parser = PARSERS[("e5", subdataset_name)]
    iterator = make_dataset_iterator(
        registry=subdataset_registry,
        ts_extractor=ts_extr,
        parse_fn=parser,
        test_run_seconds=60 * 10,
    )
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ts, record in iterator:
        record = record["datum"]
        record_type = next(iter(record.keys()))
        record_type_short = record_type.rsplit('.', 1)[-1]
        match record_type_short:
            case record_type_short if record_type_short in [
                "Event", "FileObject", "Principal", "SrcSinkObject", "Subject", "IpcObject",
            ]:
                subtype = record[record_type]["type"]
                counts[record_type_short][subtype] += 1

            case record_type_short if record_type_short in ["Host"]:
                subtype = record[record_type]["hostType"]
                counts[record_type_short][subtype] += 1

            case record_type_short if record_type_short in [
                "NetFlowObject", "UnnamedPipeObject", "ProvenanceTagNode", "UnitDependency",
                "StartMarker", "TimeMarker", "EndMarker", "MemoryObject", "RegistryKeyObject",
            ]:
                counts[record_type_short][record_type_short] += 1

            case _:
                pprint(record)
                raise Exception(f"no type {record_type_short} handled")
            
    return subdataset_name, {k: dict(v) for k, v in counts.items()}

def _cdm20_types_and_subtypes_dict(n_workers: int = 8) -> dict[str, dict[str, dict[str, int]]]:
    all_cdm20_registry = get_big_registry("e5")
    subdataset_names = list(all_cdm20_registry.keys())
    print(f"\t[multiprocessing] {len(subdataset_names)} sub-datasets with {n_workers} workers")
    with Pool(processes=n_workers) as pool:
        results = pool.map(_process_one_subdataset_cdm20, subdataset_names)
    return dict(results)
        
def _cdm18_types_and_subtypes_dict() -> dict[str, dict[str, dict[str, int]]]:
    all_cdm18_registry = get_big_registry("e3")
    out: dict[str, dict[str, dict[str, int]]] = {}

    for subdataset_name, subdataset_registry in all_cdm18_registry.items():
        print(f"\t[processing sub dataset] {subdataset_name}")
        ts_extr = lambda _: None # TS_EXTRACTORS[("e3", subdataset_name)]  # we do not need the timestamps here, so when not doing test runs, replace with lambda _: None
        parser = PARSERS[("e3", subdataset_name)]
        iterator = make_dataset_iterator(
            registry=subdataset_registry,
            ts_extractor=ts_extr,
            parse_fn=parser,
            # test_run_seconds=5,  # remove later & switch ts extractor for something faster
        )

        counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for _, record in iterator:
            record = record["datum"]
            record_type = next(iter(record.keys()))
            record_type_short = record_type.rsplit('.', 1)[-1]

            match record_type_short:
                case record_type_short if record_type_short in [
                    "Event", "FileObject", "Principal", "SrcSinkObject", "Subject",
                ]:
                    subtype = record[record_type]["type"]
                    counts[record_type_short][subtype] += 1

                case record_type_short if record_type_short in ["Host"]:
                    subtype = record[record_type]["hostType"]
                    counts[record_type_short][subtype] += 1

                case record_type_short if record_type_short in [
                    "NetFlowObject", "UnnamedPipeObject", "ProvenanceTagNode", "UnitDependency",
                    "StartMarker", "TimeMarker", "EndMarker", "MemoryObject", "RegistryKeyObject",
                ]:
                    counts[record_type_short][record_type_short] += 1

                case _:
                    pprint(record)
                    raise Exception(f"no type {record_type_short} handled")

        # convert nested defaultdicts to plain dicts for JSON serialisation
        out[subdataset_name] = {k: dict(v) for k, v in counts.items()}

    return out

def _build_percentage_table(
    data: dict[str, dict[str, dict[str, int]]],
) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, int]], np.ndarray, np.ndarray]:
    """Convert the nested count dict into aligned arrays for plotting.

    The matrix is oriented as **type/subtype rows x sub-dataset columns**.

    Returns
    -------
    sub_dataset_names : list[str]
        Column labels (one per sub-dataset).
    type_subtype_pairs : list[tuple[str, str]]
        (record_type, subtype) for every row, grouped by type then sorted by subtype within each group.
    groups : list[tuple[str, int]]
        (type_name, count_of_subtypes) contiguous row groups in the order they appear.
    pct : np.ndarray, shape (n_type_subtypes, n_sub_datasets) 
        consiting of percentage values or NaN where the type/subtype is absent.
    mask_none : np.ndarray[bool]
        true for cells that should display "None" instead of a number.
    """
    # collect all unique (type, subtype) pairs, grouped & sorted
    all_pairs: set[tuple[str, str]] = set()
    for sub_ds in data:
        for record_type in data[sub_ds]:
            for subtype in data[sub_ds][record_type]:
                all_pairs.add((record_type, subtype))

    # group by type (sorted), subtypes sorted within each group
    from itertools import groupby as _groupby
    sorted_pairs = sorted(all_pairs, key=lambda p: (p[0], p[1]))
    groups: list[tuple[str, int]] = []
    type_subtype_pairs: list[tuple[str, str]] = []
    for typ, grp in _groupby(sorted_pairs, key=lambda p: p[0]):
        members = list(grp)
        groups.append((typ, len(members)))
        type_subtype_pairs.extend(members)

    sub_dataset_names = sorted(data)
    n_rows = len(type_subtype_pairs)
    n_cols = len(sub_dataset_names)

    pct = np.full((n_rows, n_cols), np.nan)
    mask_none = np.ones((n_rows, n_cols), dtype=bool)

    for j, sub_ds in enumerate(sub_dataset_names):
        total = sum(
            count
            for type_dict in data[sub_ds].values()
            for count in type_dict.values()
        )
        if total == 0:
            continue
        for i, (typ, sub) in enumerate(type_subtype_pairs):
            if typ in data[sub_ds] and sub in data[sub_ds][typ]:
                pct[i, j] = data[sub_ds][typ][sub] / total * 100.0
                mask_none[i, j] = False

    return sub_dataset_names, type_subtype_pairs, groups, pct, mask_none

class DataModelTypesPlot(PlotPipeline):
    """Heatmap of record-type / subtype percentages across sub-datasets."""

    @property
    def cache_suffix(self) -> str:
        return "json"

    def relative_path(self, data_model: str, **kwargs: Any) -> str:
        return f"{data_model}"

    # data retrieval
    def retrieve_data(self, data_model: str, **kwargs: Any) -> Any:
        match data_model:
            case "cdm18":
                print(f"\t[processing datasets] for {data_model}")
                out_dict = _cdm18_types_and_subtypes_dict()
                return out_dict
            case "cdm20": 
                print(f"\t[processing datasets] for {data_model}")
                out_dict = _cdm20_types_and_subtypes_dict()
                return out_dict
            case _:
                raise NotImplementedError

    # plot rendering
    def make_plot(self, data: Any, **kwargs: Any) -> Figure:
        sub_datasets, pairs, groups, pct, mask_none = _build_percentage_table(data)

        n_rows, n_cols = pct.shape  # where rows = type/subtypes, cols = sub-datasets

        # y-axis labels: subtype
        row_labels = [
            sub if sub != typ else typ
            for typ, sub in pairs
        ]

        # dynamic figure size 
        cell_w, cell_h = 1.25, 0.38
        fig_w = max(7, n_cols * cell_w + 3.6)
        fig_h = max(4, n_rows * cell_h + 1.8)

        # override some style settings expected in get_style()
        prev_grid = plt.rcParams["axes.grid"]
        prev_sp_top = plt.rcParams["axes.spines.top"]
        prev_sp_right = plt.rcParams["axes.spines.right"]

        try:
            plt.rcParams["axes.grid"] = False
            plt.rcParams["axes.spines.top"] = True
            plt.rcParams["axes.spines.right"] = True

            fig, ax = plt.subplots(figsize=(fig_w, fig_h))

            # colormap
            pct_display = np.where(mask_none, 0.0, pct)

            vmin = 1e-3
            vmax = 100.0
            norm = mcolors.LogNorm(vmin=vmin, vmax=vmax, clip=True)

            cmap = mcolors.LinearSegmentedColormap.from_list(
                "two_tone", ["#fcfcfc", "#1a5276"], N=256,
            )
            cmap.set_bad(color="white")
            pct_masked = np.ma.array(pct_display, mask=mask_none)
            im = ax.imshow(
                pct_masked, cmap=cmap, norm=norm, aspect="auto",
            )

            # cell annotations
            for i in range(n_rows):
                for j in range(n_cols):
                    if mask_none[i, j]:
                        text = "None"
                        color = "#888888"
                    else:
                        val = pct[i, j]
                        if val < 0.05:
                            text = f"{val:.1e}%"
                        elif val < 1.0:
                            text = f"{val:.2f}%"
                        else:
                            text = f"{val:.1f}%"
                        color = "white" if norm(val) > 0.55 else "#222222" # so text is readable

                    ax.text(
                        j, i, text,
                        ha="center", va="center",
                        fontsize=7, color=color,
                    )

            # top x-axis for sub-datasets
            ax.set_xticks(range(n_cols))
            ax.set_xticklabels(sub_datasets, rotation=45, ha="right", fontsize=8)
            ax.xaxis.set_ticks_position("top")
            ax.xaxis.set_label_position("top")

            # y-axis subtypes
            ax.set_yticks(range(n_rows))
            ax.set_yticklabels(row_labels, fontsize=7)

            # type labels on the right
            row_cursor = 0
            for group_name, group_size in groups:
                if row_cursor > 0:
                    ax.axhline(
                        y=row_cursor - 0.5, color="#333333",
                        linewidth=1.0, linestyle="-",
                    )
                group_center_y = row_cursor + (group_size - 1) / 2.0
                ax.text(
                    n_cols - 0.5 + 0.3, group_center_y, group_name,
                    ha="left", va="center",
                    fontsize=8, fontweight="bold",
                    clip_on=False,
                )
                row_cursor += group_size

            ax.set_title("Record Type & Subtype Distribution", pad=14)

            # # colour bar
            # cbar = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.12)
            # cbar.set_label("% of sub-dataset", fontsize=8)
            # cbar.ax.tick_params(labelsize=7)

            fig.subplots_adjust(
                left=0.18, right=0.78, top=0.92, bottom=0.03,
            )

        finally:
            plt.rcParams["axes.grid"] = prev_grid
            plt.rcParams["axes.spines.top"] = prev_sp_top
            plt.rcParams["axes.spines.right"] = prev_sp_right

        return fig
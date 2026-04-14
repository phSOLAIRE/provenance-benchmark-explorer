"""
DatasetTimespansPlot

Example usage in jupyter notebook::

    from provenance_explorer.analysis.provenance_capture.dataset_timespans_plot import DatasetTimespansPlot
    from provenance_explorer.plotting.config import apply_style

    DATSET = "optc"
    SUB_DATASET = "AIA-201-225"

    apply_style()
    plot = DatasetTimespansPlot()
    plot_size = (10, 10)
    # plot.invalidate(dataset = DATSET, sub_dataset=SUB_DATASET) # uncomment e.g. if something changes in plottijng logic
    fig = plot.run(dataset = DATSET, sub_dataset=SUB_DATASET, override_plot_size=plot_size)
    fig.set_size_inches(plot_size)
"""

from __future__ import annotations

from typing import Any

import pandas as pd 
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from provenance_explorer.plotting import PlotPipeline, color

class DatasetTimespansPlot(PlotPipeline):
    """
    Plot files making up a dataset to determine overlap and uncovered timespans.
    """

    # cache format e.g. "csv" | "json" | "pkl" | "parquet" 
    @property
    def cache_suffix(self) -> str:
        return "csv"

    # cache path without suffix
    def relative_path(self, dataset: str, sub_dataset: str, **kwargs) -> str:
        return f"{dataset}/{sub_dataset}"

    # data retrieval; here will be saved as csv with "to_csv"
    def retrieve_data(self, dataset: str, sub_dataset: str, **kwargs) -> Any:
        from provenance_explorer.raw_file_handling.file_annotations import build_file_registry
        import pandas as pd 
        
        registry = build_file_registry(dataset, sub_dataset)
        
        df = pd.DataFrame(registry)[["path", "first_realistic_ts_ns", "last_timestamp_ns"]]
        return df
    
    # plot rendering
    def make_plot(
        self,
        data,
        time_zone: timezone = timezone.utc,
        **kwargs,
    ) -> Figure:

        fig, ax = plt.subplots()

        df = data.copy()

        labels = []

        for i in range(len(df)):
            row = df.iloc[i]

            path = row["path"]
            labels.append(path)

            start = datetime.fromtimestamp(
                row["first_realistic_ts_ns"] / 1e9, tz=timezone.utc
            ).astimezone(time_zone)

            end = datetime.fromtimestamp(
                row["last_timestamp_ns"] / 1e9, tz=timezone.utc
            ).astimezone(time_zone)

            start_num = mdates.date2num(start)
            end_num = mdates.date2num(end)

            ax.hlines(float(i), start_num, end_num)

        ax.set_yticks(range(len(df)))
        ax.set_yticklabels(labels)

        ax.xaxis_date()

        ax.set_xlabel(f"time ({time_zone})")
        ax.set_ylabel("files")
        ax.set_title("Dataset file time coverage")

        fig.autofmt_xdate()

        return fig
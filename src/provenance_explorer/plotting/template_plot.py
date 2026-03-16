"""
<PLOT_TITLE>

Example usage in notebook: 

    from provenance_explorer.plotting import apply_style
    apply_style()

    plot = <ClassName>()
    fig  = plot.run(<kwargs>)
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from provenance_explorer.plotting import PlotPipeline


class TODO_RenameMe(PlotPipeline):
    """TODO: docstring."""

    # cache format e.g. "csv" | "json" | "pkl" | "parquet" 
    # or add functions _load_<suffix> and _save_<suffix>
    @property
    def cache_suffix(self) -> str:
        return "csv"

    # cache path without suffix
    def relative_path(self, **kwargs: Any) -> str:
        # Example: dataset/sub_dataset/start-end
        dataset: str = kwargs["dataset"]
        sub_dataset: str = kwargs["sub_dataset"]
        return f"{dataset}/{sub_dataset}/TODO"

    # data retrieval
    def retrieve_data(self, **kwargs: Any) -> Any:
        raise NotImplementedError("TODO: implement data retrieval")

    # plot rendering
    def make_plot(self, data: Any, **kwargs: Any) -> Figure:
        fig, ax = plt.subplots()

        # TODO: replace with actual plotting logic
        # ax.plot(data["x"], data["y"])

        ax.set_xlabel("TODO")
        ax.set_ylabel("TODO")
        ax.set_title("TODO")
        return fig
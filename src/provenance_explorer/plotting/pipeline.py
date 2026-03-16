"""Plot pipeline abstract base class.

A PlotPipeline is the single entry-point for every plot in the project.
It composes:

1. Data retrieval — expensive computation, cached via ArtifactCache.
2. Plot rendering — pure matplotlib, reads cached data + central style.
3. Figure saving  — auto-saves PNG into figures/<plot_name>/....

Concrete subclasses implement four things:

* cache_suffix      — inherited from ArtifactCache
* relative_path()   — inherited from ArtifactCache
* retrieve_data()   — the expensive computation
* make_plot()       — matplotlib drawing from cached data

Everything else (caching, style application, figure) is handled by the base class.

Typical usage in a notebook::
    from provenance_explorer.plotting.config import apply_style
    apply_style()                       # once per session

    plot = NodeInteractionRasterPlot()  # some implemented subclass
    fig  = plot.run(dataset="OpTC", sub_dataset="AIA-51-75", timespan=(10000, 10050))
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from provenance_explorer.plotting.cache import ArtifactCache
from provenance_explorer.registry.repo_paths import FIGURES_ROOT


class PlotPipeline(ArtifactCache):
    """
    ABC for every plot in provenance-explorer.

    Lifecycle
    run(**kwargs)
    - check cache (hit -> load; miss -> retrieve_data -> save)
    - make_plot(data, **kwargs)
        saves figure PNG and returns matplotlib.figure.Figure
    """

    # Interface
    @abstractmethod
    def retrieve_data(self, **kwargs: Any) -> Any:
        """
        Run the (expensive) data retrieval / computation.
        Return an object whose type matches what make_plot expects and what tzhe chosen cache_suffix can serialise.
        """
        ...

    @abstractmethod
    def make_plot(self, data: Any, **kwargs: Any) -> Figure:
        """Create and return a matplotlib Figure from cached data.

        The central style sheet is already applied when this is called.
        Use ``from provenance_explorer.plotting.config import color, PALETTE``
        for colours.
        """
        ...

    def figure_path(self, **kwargs: Any) -> Path:
        """Absolute path where the PNG will be saved."""
        rel = self.relative_path(**kwargs)
        return FIGURES_ROOT / self.plot_name / f"{rel}.png"

    # Orchestrator
    def data_retrieval(self, **kwargs: Any) -> Any:
        """Return cached data, running retrieval only on cache miss."""
        if self.has_cache(**kwargs):
            return self.load(**kwargs)

        print(f"[cache miss] Retrieving data for {self.plot_name}...")
        data = self.retrieve_data(**kwargs)
        self.save(data, **kwargs)
        return data

    def plot(self, **kwargs: Any) -> Figure:
        """Load cached data and render the plot (no data retrieval)."""
        data = self.load(**kwargs) 
        fig = self.make_plot(data, **kwargs)
        self._save_figure(fig, **kwargs)
        return fig

    def run(self, **kwargs: Any) -> Figure:
        """Full pipeline: ensure data exists -> plot _> save figure."""
        data = self.data_retrieval(**kwargs)
        fig = self.make_plot(data, **kwargs)
        self._save_figure(fig, **kwargs)
        return fig

    def _save_figure(self, fig: Figure, **kwargs: Any) -> None:
        path = self.figure_path(**kwargs)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        print(f"[figure]     {path}")

    # Convenience: invalidate cache to force re-retrieval
    def invalidate(self, **kwargs: Any) -> None:
        """Delete the cached artifact for these args, if it exists."""
        path = self.cache_path(**kwargs)
        if path.is_file():
            path.unlink()
            print(f"[cache del]  {path}")
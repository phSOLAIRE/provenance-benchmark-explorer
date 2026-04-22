"""
Artifact cache for intermediate data used in plots.

Each concrete plot pipeline declares
- how its data is serialised (format + suffix) 
- and where it lives (the relative path under the cache root).  
This base class takes care of reading, writing, and cache-hit detection.

Subclasses set cache_suffix to one of the registered formats.  
adding a new format requires _load_<suffix> / _save_<suffix> method pair in the implementing class
"""
# from __future__ import annotations

import json
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from provenance_explorer.registry.registry_all import CACHE_ROOT


class ArtifactCache(ABC):
    """ABC that every plot pipeline inherits for data caching.

    Subclasses **must** implement
    * ``cache_suffix``   — property returning the file extension (no dot),
                           e.g. ``"csv"``, ``"json"``, ``"pkl"``.
    * ``relative_path()`
        — given the plot's keyword arguments, return the path <relative_path>
        which is then (automatically) embedded in <CACHE_ROOT> / <plot_name> / <relative_path>.<cache_suffix>
    """

    # Interface that subclasses must provide: 
    @property
    @abstractmethod
    def cache_suffix(self) -> str:
        """File extension e.g.'csv')."""
        ...

    @abstractmethod
    def relative_path(self, **kwargs: Any) -> str:
        """
        Return the cache-relative path (no extension) for these args.
        
        The returned string is joined as:
        <CACHE_ROOT> / <plot_name> / <relative_path>.<cache_suffix>
        It is the implementing classes responsibility to ensure uniqueness across different parameter combinations.
        """
        ...

    @property
    def plot_name(self) -> str:
        """Derive the plot name from the concrete class name.

        e.g. NodeInteractionRasterPlot -> node_interaction_raster_plot
        Override if you need a custom name.
        """
        name = type(self).__name__
        # CamelCase to snake_case
        import re
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

    def cache_path(self, **kwargs: Any) -> Path:
        """Full absolute path to the cached artifact."""
        rel = self.relative_path(**kwargs)
        return CACHE_ROOT / self.plot_name / f"{rel}.{self.cache_suffix}"

    def has_cache(self, **kwargs: Any) -> bool:
        """Return True if a cached artifact exists for these args."""
        return self.cache_path(**kwargs).is_file()

    def load(self, **kwargs: Any) -> Any:
        """Load a cached artifact.  Raises FileNotFoundError on miss."""
        path = self.cache_path(**kwargs)
        if not path.is_file():
            raise FileNotFoundError(f"No artifact at {path}")
        print(f"[cache hit]  {path}")
        return self._load(path)

    def save(self, data: Any, **kwargs: Any) -> Path:
        """Persist data to the cache and return the written path."""
        path = self.cache_path(**kwargs)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._save(data, path)
        print(f"[cache save] {path}")
        return path

    def _load(self, path: Path) -> Any:
        loader = getattr(self, f"_load_{self.cache_suffix}", None)
        if loader is None:
            raise NotImplementedError(f"No loader for suffix '{self.cache_suffix}'.")
        return loader(path)

    def _save(self, data: Any, path: Path) -> None:
        saver = getattr(self, f"_save_{self.cache_suffix}", None)
        if saver is None:
            raise NotImplementedError(f"No saver for suffix '{self.cache_suffix}'.")
        saver(data, path)

    # some format handlers: 
    @staticmethod
    def _load_csv(path: Path) -> pd.DataFrame:
        return pd.read_csv(path)

    @staticmethod
    def _save_csv(data: pd.DataFrame, path: Path) -> None:
        data.to_csv(path, index=False)

    @staticmethod
    def _load_json(path: Path) -> Any:
        with open(path, "r") as fh:
            return json.load(fh)

    @staticmethod
    def _save_json(data: Any, path: Path) -> None:
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2, default=str)

    @staticmethod
    def _load_pkl(path: Path) -> Any:
        with open(path, "rb") as fh:
            return pickle.load(fh)

    @staticmethod
    def _save_pkl(data: Any, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _load_parquet(path: Path) -> pd.DataFrame:
        return pd.read_parquet(path)

    @staticmethod
    def _save_parquet(data: pd.DataFrame, path: Path) -> None:
        data.to_parquet(path, index=False)
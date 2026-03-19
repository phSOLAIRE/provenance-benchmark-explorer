import os
from pathlib import Path

from provenance_explorer.registry.darpa_e3_registry import E3_ALL
from provenance_explorer.registry.darpa_e5_registry import E5_ALL
from provenance_explorer.registry.darpa_optc_registry import OPTC_ALL

REPO_ROOT = Path(__file__).resolve().parents[3]
WORK = Path(os.getenv("WORK", "")) # present on unified HPC system

# defined in setup.md
DATA_RAW = Path(os.getenv("WS_RAW_PATH", ""))
DATA_NE04J = Path(os.getenv("WS_NEO4J_PATH", ""))

# Cache for expesive data retrieval for plots
CACHE_ROOT = WORK / "provenance-explorer-cache"
 
# Plot output
FIGURES_ROOT = REPO_ROOT / "img" / "figures" 

def get_subdataset_registry(dataset: str, sub_dataset: str) -> list[dict]: 
    match dataset:
        case "e3": 
            return E3_ALL[sub_dataset]
        case "e5":
            return E5_ALL[sub_dataset]
        case "optc":
            return OPTC_ALL[sub_dataset]
        case _:
            raise

def get_big_registry(dataset: str) -> dict: 
    match dataset:
        case "e3": 
            return E3_ALL
        case "e5":
            return E5_ALL
        case "optc":
            return OPTC_ALL
        case _:
            raise
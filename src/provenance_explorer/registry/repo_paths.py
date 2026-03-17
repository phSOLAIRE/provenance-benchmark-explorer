import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORK = Path(os.getenv("WORK", "")) # present on unified HPC system

# defined in setup.md
DATA_RAW = Path(os.getenv("WS_RAW_PATH", ""))
DATA_NE04J = Path(os.getenv("WS_NEO4J_PATH", ""))

# Cache for expesive data retrieval for plots
CACHE_ROOT = WORK / "provenance-explorer-cache"
 
# Plot output
FIGURES_ROOT = REPO_ROOT / "img" / "figures" 
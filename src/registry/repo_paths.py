import os
from pathlib import Path
DATA_RAW = Path(os.getenv("WS_RAW_PATH", ""))
DATA_NE04J = Path(os.getenv("WS_NEO4J_PATH", ""))

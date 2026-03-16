"""
plotting configuration: 
call apply_style() once at the start of a notebook or script to ensure all figures share the same look.
"""
from pathlib import Path

import matplotlib.pyplot as plt

_STYLE_PATH = Path(__file__).with_name("style.mplstyle")

def apply_style() -> None:
    """Apply the project-wide matplotlib style sheet."""
    plt.style.use(str(_STYLE_PATH))

def palette() -> list[str]:
    """Return the active colour cycle as a list of hex strings."""
    return [c["color"] for c in plt.rcParams["axes.prop_cycle"]]

def color(index: int) -> str:
    """Return the *index*-th palette colour (wraps around)."""
    pal = palette()
    return pal[index % len(pal)]
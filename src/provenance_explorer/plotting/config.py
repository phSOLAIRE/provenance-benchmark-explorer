"""
plotting configuration: 
call apply_style() once at the start of a notebook or script to ensure all figures share the same look.
"""
from pathlib import Path

import matplotlib.pyplot as plt

_STYLE_PATH = Path(__file__).with_name("style.mplstyle")
_STYLE_APPLIED = False

def apply_style() -> None:
    """Apply the project-wide matplotlib style sheet."""
    global _STYLE_APPLIED
    if not _STYLE_APPLIED:
        plt.style.use(str(_STYLE_PATH))
        _STYLE_APPLIED = True

def palette() -> list[str]:
    """Return the active colour cycle as a list of hex strings."""
    apply_style()
    return [c["color"] for c in plt.rcParams["axes.prop_cycle"]]

def color(index: int) -> str:
    """Return the *index*-th palette colour (wraps around)."""
    pal = palette()
    return pal[index % len(pal)]
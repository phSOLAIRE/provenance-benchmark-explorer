"""
component_metrics.py

Per-component scoring for NTF factorizations of the information-flow tensor.

For a CP decomposition 'T ~~ [[A, B, C]]' with 'R' components, we derive:

* relevance_r — normalized component weight, 
    proportional to ||a_r||*||b_r||*||c_r||, rescaled so that sum_r relevance_r = 1.
* periodicity_r — default autocorrelation-based score on 'C[:, r]' 
    (max absolute normalized autocorrelation over lags >= 1).
* burstiness_r — Goh-Barabasi (sigma - mu) / (sigma + mu) on C[:, r].
* concentration_r — top bin share of 'C[:, r]' after coarsening bins into #'corasening' blocks, 
    Value in [0, 1]: close to 1 = all activity in one block (isolated burst); 
    close to 1/n_blocks = evenly spread.
* regime_r — either "periodic", "bursty", "aperiodic", or "noise" following the decisions below:
    periodic if periodicity > 0.3;
    bursty   if burstiness > 0.3 AND concentration > 0.3 (meaning single significant event);
    aperiodic if burstiness > 0.3 (spread-out activity that is not rhythmic nor isolated);
    noise otherwise (flat signal NTF picked up but which does not describe an intresting temporal pattern).

* fraction per regime builds on node-to-regime assignment:
    For node i, aggregate relevance of components grouped by regime, 
    weighted by the node's participation (A[i, r] + B[i, r]). 
    Assign the node to the regime with the largest aggregated weight.
    Then: 
        regime_fractions[g] = |{nodes assigned to g}| / |assigned nodes|.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


PERIODICITY_THRESHOLD = 0.3
BURSTINESS_THRESHOLD = 0.3
CONCENTRATION_THRESHOLD = 0.3
CONCENTRATION_COARSENING = 5

REGIME_NAMES = ("periodic", "bursty", "aperiodic", "noise")

def component_relevance(A: np.ndarray, B: np.ndarray, C: np.ndarray) -> np.ndarray:
    wA = np.linalg.norm(A, axis=0)
    wB = np.linalg.norm(B, axis=0)
    wC = np.linalg.norm(C, axis=0)
    w = wA * wB * wC
    total = w.sum()
    # if total <= 0:
    #     return np.zeros_like(w)
    return w / total


def periodicity_score(
    c: np.ndarray,
    active_rel_threshold: float = 0.05,
    min_lag_floor: int = 2,
) -> float:
    """
    Max positive autocorrelation of 'c' at lags beyond the burst width.
    Skip lags <= 'active_rel_threshold * max(c)' 
    otherwise autocorrelation can be high without any periodicity. 
    """
    x = np.asarray(c, dtype=np.float64)
    n = x.size
    if n < 4:
        return 0.0
    m = x.max()
    if m <= 0.0:
        return 0.0
    burst_width = int((x >= active_rel_threshold * m).sum())
    min_lag = max(min_lag_floor, burst_width)
    x_c = x - x.mean()
    var = np.dot(x_c, x_c)
    if var <= 1e-12:
        return 0.0
    max_lag = n // 2
    if min_lag >= max_lag:
        return 0.0
    full = np.correlate(x_c, x_c, mode="full")
    mid = n - 1
    lags = full[mid + min_lag: mid + max_lag + 1]
    if lags.size == 0:
        return 0.0
    return float(max(0.0, float(lags.max()) / var))


def burstiness_score(c: np.ndarray) -> float:
    """Goh-Barabasi B = (sigma - mu) / (sigma + mu)."""
    x = np.asarray(c, dtype=np.float64)
    mu = x.mean()
    sigma = x.std()
    denom = sigma + mu
    if denom <= 1e-12:
        return 0.0
    return float((sigma - mu) / denom)


def concentration_score(c: np.ndarray, coarsening: int = CONCENTRATION_COARSENING) -> float:
    """
    share of top bin on a coarsened bin profile.
    returns max(block_sums) / sum(block_sums), meaning a value close to 1 menas an isolated activity burst.
    """
    x = np.asarray(c, dtype=np.float64)
    n = x.size
    k = max(1, int(coarsening))
    n_blocks = n // k
    if n_blocks < 1:
        return 0.0
    trimmed = x[: n_blocks * k].reshape(n_blocks, k)
    block_sums = trimmed.sum(axis=1)
    total = block_sums.sum()
    if total <= 1e-12:
        return 0.0
    return float(block_sums.max() / total)


def classify_regime(periodicity: float, burstiness: float, concentration: float) -> str:
    """
    Four-way classifier:
      periodic  : repetitive scripted / system activity.
      bursty    : single significant event (bursty + concentrated).
      aperiodic : bursty but spread out.
      noise     : flat signal NTF picked up but that is close to background noise than significant behavior.
    """
    if periodicity > PERIODICITY_THRESHOLD:
        return "periodic"
    if burstiness > BURSTINESS_THRESHOLD and concentration > CONCENTRATION_THRESHOLD:
        return "bursty"
    if burstiness > BURSTINESS_THRESHOLD:
        return "aperiodic"
    return "noise"


@dataclass
class ComponentAnalysis:
    scores: pd.DataFrame # per-component: r, relevance, periodicity, burstiness, regime
    regime_fractions: Dict[str, float] # over assigned nodes
    node_regime: np.ndarray # shape (N,), values in {periodic, bursty, aperiodic, unassigned}
    regime_node_counts: Dict[str, int] = field(default_factory=dict)
    n_assigned: int = 0
    n_nodes: int = 0


def analyze_components(
    A: np.ndarray, B: np.ndarray, C: np.ndarray,
    concentration_coarsening: int = CONCENTRATION_COARSENING,
) -> ComponentAnalysis:
    """Compute per-component scores, regime labels, and per-node regime assignment."""
    R = A.shape[1]
    rel = component_relevance(A, B, C)

    rows = []
    regimes: List[str] = []
    for r in range(R):
        p = periodicity_score(C[:, r])
        b = burstiness_score(C[:, r])
        c = concentration_score(C[:, r], coarsening=concentration_coarsening)
        g = classify_regime(p, b, c)
        regimes.append(g)
        rows.append({
            "r": r, "relevance": rel[r],
            "periodicity": p, "burstiness": b, "concentration": c,
            "regime": g,
        })
    scores = pd.DataFrame(rows)

    # node-regime assignment: weighted participation per regime; argmax wins, as desribed above
    N = A.shape[0]
    regime_names = list(REGIME_NAMES)
    weights = np.zeros((N, len(regime_names)), dtype=np.float64)
    node_participation = A + B  # (N, R), both non-negative
    for r in range(R):
        g_idx = regime_names.index(regimes[r]) # type: ignore
        weights[:, g_idx] += rel[r] * node_participation[:, r]

    total = weights.sum(axis=1)
    node_regime = np.full(N, "unassigned", dtype=object)
    assigned_mask = total > 1e-12
    if assigned_mask.any():
        picks = np.argmax(weights[assigned_mask], axis=1)
        node_regime[assigned_mask] = np.array(regime_names)[picks]

    counts = {g: int(np.sum(node_regime == g)) for g in regime_names}
    n_assigned = int(assigned_mask.sum())
    fractions = {
        g: (counts[g] / n_assigned) if n_assigned > 0 else 0.0
        for g in regime_names
    }

    return ComponentAnalysis(
        scores=scores,
        regime_fractions=fractions,
        node_regime=node_regime,
        regime_node_counts=counts,
        n_assigned=n_assigned,
        n_nodes=N,
    )


def best_explained_variance_under(sweep_table: pd.DataFrame, max_R: int = 25) -> Optional[float]:
    """
    Best explained-variance percentage achieved with R <= max_R.
    """
    sub = sweep_table[sweep_table["R"] <= max_R]
    if sub.empty:
        return None
    return float(sub["explained_pct"].max())

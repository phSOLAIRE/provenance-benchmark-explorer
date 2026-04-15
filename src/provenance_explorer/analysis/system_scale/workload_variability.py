"""
Metric:
Number of distinct workload patterns per host, determined by fitting a discrete HMM to a clustered sequence.
Adapted from (Harrison, 2012) "Storage workload modelling by hidden Markov models: Application to Flash memory"

Procedure (per host):
  1. Aggregate raw 5-min bins into bins of bin_size_minutes (sum poer event type)
  2. Build a feature vector per bin.  
  3. Log-transform non-zero entries s.t. x' = log(x + 1).
  4. Cluster the feature vectors with k-means into n_obs_classes discrete observation classes.
  5. Fit a discrete HMM for K = 1..K_max.
  6. Compute BIC for each K.
  7. Select K with the lowest BIC.
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd
from typing import Optional, Tuple, Dict, Any, List

from provenance_explorer.plotting.config import color

# Raw resolution of the incoming data
_RAW_BIN_MINUTES = 5

# Default number of observation classes produced by k-means
_DEFAULT_N_OBS_CLASSES = 12

def _validate_bin_size(bin_size_minutes: int) -> None:
    if (bin_size_minutes < _RAW_BIN_MINUTES) \
        or (bin_size_minutes % _RAW_BIN_MINUTES != 0):
        raise ValueError

def _resample_to_bin_size(
    ts: pd.DataFrame,
    bin_size_minutes: int,
    time_col: str,
    value_cols: list[str],
) -> pd.DataFrame:
    """Aggregate a per-host time series from 5-min bins to coarser bins."""
    if bin_size_minutes == _RAW_BIN_MINUTES:
        return ts

    bin_ns = bin_size_minutes * 60 * 10**9
    ts = ts.copy()
    ts["_coarse_bin"] = (ts[time_col] // bin_ns) * bin_ns
    resampled = (
        ts.groupby("_coarse_bin")[value_cols]
        .sum()
        .reset_index()
        .rename(columns={"_coarse_bin": time_col})
    )
    return resampled


def _build_feature_matrix(
    ts: pd.DataFrame,
    event_type_col: Optional[str],
    time_col: str,
    count_col: str,
) -> Tuple[pd.DataFrame, List[str]]:
    """Pivot per-bin counts into a feature matrix."""
    if event_type_col is not None and event_type_col in ts.columns:
        n_types = ts[event_type_col].nunique()
    else:
        n_types = 0

    if n_types > 1:
        wide = (
            ts.pivot_table(
                index=time_col,
                columns=event_type_col,
                values=count_col,
                aggfunc="sum",
                fill_value=0,
            )
            .sort_index()
        )
        # for stable column order
        wide.columns = [str(c) for c in wide.columns]
        feature_cols = sorted(wide.columns.tolist())
        wide = wide[feature_cols]
    else:
        # aggregate across all event types
        wide = (
            ts.groupby(time_col)[count_col]
            .sum()
            .reset_index()
            .rename(columns={count_col: "total_count"})
            .set_index(time_col)
            .sort_index()
        )
        feature_cols = ["total_count"]

    return wide, feature_cols


def _cluster_observations(
    X_log: np.ndarray,
    idle_mask: np.ndarray,
    n_obs_classes: int,
    random_state: int,
) -> Tuple[np.ndarray, np.ndarray, int]:
    """Assign each bin to a discrete observation class via k-means.

    X_log : np.ndarray, shape (n_bins, n_features) 
        Log-transformed feature matrix (log1p of raw counts).
    idle_mask : np.ndarray, shape (n_bins,), bool 
        has to be True for bins where all feature dimensions are zero.
    n_obs_classes : int
        Number of k-means clusters for non-idle bins.
    """
    from sklearn.cluster import KMeans

    n_bins = X_log.shape[0]
    obs_seq = np.zeros(n_bins, dtype=int)  # 0 = idle by default

    active_idx = np.where(~idle_mask)[0]

    if len(active_idx) == 0:
        return obs_seq, np.empty((0, X_log.shape[1])), 1

    X_active = X_log[active_idx]

    # fewer active bins than requested clusters -> reduce k
    effective_k = min(n_obs_classes, len(active_idx))

    km = KMeans(
        n_clusters=effective_k,
        n_init=10,
        random_state=random_state,
    )
    labels = km.fit_predict(X_active)
    obs_seq[active_idx] = labels + 1
    n_total_classes = effective_k + 1
    return obs_seq, km.cluster_centers_, n_total_classes

def _compute_discrete_bic(
    log_likelihood: float,
    n_samples: int,
    K: int,
    M: int,
) -> float:
    """Compute BIC for a categorical HMM."""
    n_params = K * (K - 1) + (K - 1) + K * (M - 1)
    return -2.0 * log_likelihood + n_params * np.log(n_samples)

# Main function
def fit_hmm_select_k(
    event_counts: pd.DataFrame,
    k_max: int = 8,
    n_obs_classes: int = _DEFAULT_N_OBS_CLASSES,
    n_iter: int = 200,
    n_restarts: int = 5,
    random_state: int = 42,
    time_col: str = "time_bin_ns",
    host_col: str = "host_id",
    count_col: str = "count",
    event_type_col: Optional[str] = "event_type",
    bin_size_minutes: int = 5,
) -> pd.DataFrame:
    """Fit discrete HMMs for K=1..k_max per host and select best K via BIC.

    This follows the methodology of Harrison et al. (2012): bin → cluster
    → discrete HMM → BIC model selection.

    Parameters
    ----------
    event_counts : pd.DataFrame
        Columns: [host_id, time_bin_ns, count] and optionally event_type
    k_max : int
        Maximum number of hidden states to try
    n_obs_classes : int
        Number of k-means clusters for non-idle bins
    n_iter : int
        Max EM iterations per HMM fit
    n_restarts : int
        Number of random restarts per K; best (highest log-likelihood) kept.
    random_state : int
        seed
    event_type_col : str or None
        Column name for the event type.
    bin_size_minutes : int
        Width of the time bins used for modelling, in minutes.

    Returns a df
        One row per host with columns:
        - host_id
        - best_k         : selected number of workload patterns
        - best_bic       : BIC at the selected K
        - bic_curve      : list of (K, BIC) tuples for all K tried
        - n_obs_classes  : total observation classes used (incl. idle)
        - feature_cols   : list of feature dimensions used
        - centroids      : k-means centroids in log-space (non-idle only)
        - bin_size_min   : the bin size used
        - idle_frac      : fraction of bins that were idle (zero events)
    """
    from hmmlearn.hmm import CategoricalHMM

    _validate_bin_size(bin_size_minutes)

    results = []
    for host, grp in event_counts.groupby(host_col):
        grp = grp.sort_values(time_col).copy()

        # per-bin feature matrix
        wide, feature_cols = _build_feature_matrix(
            grp, event_type_col, time_col, count_col,
        )

        # resample bin size
        wide = wide.reset_index()
        wide = _resample_to_bin_size(wide, bin_size_minutes, time_col, feature_cols)
        wide = wide.set_index(time_col).sort_index()

        raw_counts = wide[feature_cols].values  # (n_bins, n_features)

        # idle bins (all dimensions zero)
        idle_mask = (raw_counts.sum(axis=1) == 0)
        idle_frac = idle_mask.mean()

        if len(wide) < 10:
            results.append({
                "host_id": host,
                "best_k": np.nan,
                "best_bic": np.nan,
                "bic_curve": [],
                "n_obs_classes": np.nan,
                "feature_cols": feature_cols,
                "centroids": None,
                "bin_size_min": bin_size_minutes,
                "idle_frac": idle_frac,
            })
            continue

        # log-transform
        X_log = np.log1p(raw_counts.astype(float))

        # cluster into discrete observation classes
        obs_seq, centroids, n_total_classes = _cluster_observations(
            X_log, idle_mask, n_obs_classes, random_state,
        )

        # CategoricalHMM expects a 2D column vector of integer labels
        obs_col = obs_seq.reshape(-1, 1)

        # fit categorical HMMs for K = 1..k_max
        bic_curve: list[Tuple[int, float]] = []

        for k in range(1, k_max + 1):
            best_score = -np.inf
            best_model = None

            for restart in range(n_restarts):
                try:
                    model = CategoricalHMM(
                        n_components=k,
                        n_features=n_total_classes,
                        n_iter=n_iter,
                        random_state=random_state + restart,
                        verbose=False,
                    )
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        model.fit(obs_col)

                    score = model.score(obs_col)
                    if score > best_score:
                        best_score = score
                        best_model = model
                except Exception:
                    continue

            if best_model is not None:
                bic = _compute_discrete_bic(
                    best_score, len(obs_seq), k, n_total_classes,
                )
                bic_curve.append((k, bic))

        if bic_curve:
            best_k, best_bic = min(bic_curve, key=lambda x: x[1])
        else:
            best_k, best_bic = np.nan, np.nan

        results.append({
            "host_id": host,
            "best_k": int(best_k) if not np.isnan(best_k) else np.nan,
            "best_bic": round(best_bic, 2) if not np.isnan(best_bic) else np.nan,
            "bic_curve": bic_curve,
            "n_obs_classes": n_total_classes,
            "feature_cols": feature_cols,
            "centroids": centroids,
            "bin_size_min": bin_size_minutes,
            "idle_frac": round(idle_frac, 4),
        })

    return pd.DataFrame(results)


def plot_bic_curve(
    bic_curve: list,
    title: str = "BIC vs K",
    ax=None,
):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(6, 3))

    ks = [k for k, _ in bic_curve]
    bics = [b for _, b in bic_curve]
    best_k = ks[np.argmin(bics)]

    ax.plot(ks, bics, "o-", color=color(0))
    ax.axvline(best_k, color=color(2), linestyle="--", alpha=0.7, label=f"best K={best_k}")
    ax.set_xlabel("K (number of states)")
    ax.set_ylabel("BIC")
    ax.set_title(title)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), borderaxespad=0)
    return ax


def plot_state_sequence(
    event_counts: pd.DataFrame,
    host_id: str,
    best_k: int,
    n_obs_classes: int = _DEFAULT_N_OBS_CLASSES,
    n_iter: int = 200,
    random_state: int = 42,
    time_col: str = "time_bin_ns",
    host_col: str = "host_id",
    count_col: str = "count",
    event_type_col: Optional[str] = "event_type",
    bin_size_minutes: int = 5,
    log_scale: bool = True,
    title_hostname = None,
    ax=None,
):
    """
    Re-fit the best model and plot the decoded state sequence overlaid on the total event rate time series.

    bin_size_minutes : int
        Must match the value used in fit_hmm_select_k
    log_scale : bool
        If True (default), plot the log-transformed series
    """
    import matplotlib.pyplot as plt
    from hmmlearn.hmm import CategoricalHMM

    _validate_bin_size(bin_size_minutes)

    host_data = event_counts[event_counts[host_col] == host_id].copy()

    # Build feature matrix & resample
    wide, feature_cols = _build_feature_matrix(
        host_data, event_type_col, time_col, count_col,
    )
    wide = wide.reset_index()
    wide = _resample_to_bin_size(wide, bin_size_minutes, time_col, feature_cols)
    wide = wide.set_index(time_col).sort_index()

    raw_counts = wide[feature_cols].values
    idle_mask = (raw_counts.sum(axis=1) == 0)
    X_log = np.log1p(raw_counts.astype(float))

    obs_seq, _, n_total_classes = _cluster_observations(
        X_log, idle_mask, n_obs_classes, random_state,
    )
    obs_col = obs_seq.reshape(-1, 1)

    model = CategoricalHMM(
        n_components=best_k,
        n_features=n_total_classes,
        n_iter=n_iter,
        random_state=random_state,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(obs_col)

    states = model.predict(obs_col)

    # Choose y-axis series
    total_raw = raw_counts.sum(axis=1)# .astype(float)
    total_log = np.log1p(total_raw)

    if log_scale:
        y = total_log
        y_label = "log(events + 1)"
        line_label = "log(events+1)"
    else:
        y = total_raw
        y_label = "events per bin"
        line_label = "events"

    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(14, 3))

    t_idx = np.arange(len(y))
    y_max = y.max() if y.max() > 0 else 1.0

    ax.plot(t_idx, y, color=color(0), alpha=0.8, label=line_label)

    for s in range(best_k):
        mask = states == s
        ax.fill_between(
            t_idx, 0, y_max,
            where=mask, alpha=0.18, color=color(s), label=f"State {s}",
        )
    host_name = host_id if not title_hostname else title_hostname
    ax.set_xlabel(f"Time bin index ({bin_size_minutes}-min bins)")
    ax.set_ylabel(y_label)
    ax.set_title(
        f"State sequence — {host_name} (K={best_k}, "
        f"bin={bin_size_minutes} min)"
    )
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), borderaxespad=0, ncol=1)
    return ax
"""
Drop log for tracking excluded records during common record construction.

Accumulates counts by 
    (dataset, sub_dataset, drop_reason) 
and optionally
    by (dataset, sub_dataset, drop_reason, raw_event_type, raw_object_type) 
    for fine-grained reporting.

Usage:
    log = DropLog()
    log.record("e3", "clearscope", DropReason.SRCSINK_TARGET,
               raw_event_type="EVENT_WRITE", raw_object_type="SrcSinkObject(SRCSINK_BINDER)")
    ...
    df = log.to_dataframe()
    log.to_latex("drop_report.tex")
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .schema import DropReason


@dataclass
class DropLog:
    """Accumulator for dropped record statistics."""

    # coarse: (dataset, sub_dataset, reason) -> count
    _coarse: Counter = field(default_factory=Counter)

    # fine: (dataset, sub_dataset, reason, raw_event_type, raw_object_type) -> count
    _fine: Counter = field(default_factory=Counter)

    # total records seen (including kept)
    _total_seen: Counter = field(default_factory=Counter)

    # total records kept
    _total_kept: Counter = field(default_factory=Counter)

    def record_seen(self, dataset: str, sub_dataset: str) -> None:
        """Call for every record the iterator yields (before classification)."""
        self._total_seen[(dataset, sub_dataset)] += 1

    def record_kept(self, dataset: str, sub_dataset: str) -> None:
        """Call for every record that becomes a CommonRecord."""
        self._total_kept[(dataset, sub_dataset)] += 1

    def record_drop(
        self,
        dataset: str,
        sub_dataset: str,
        reason: DropReason,
        raw_event_type: str = "",
        raw_object_type: str = "",
    ) -> None:
        """Log one 'dropped' record."""
        self._coarse[(dataset, sub_dataset, reason)] += 1
        if raw_event_type or raw_object_type:
            self._fine[(dataset, sub_dataset, reason, raw_event_type, raw_object_type)] += 1

    def summary(self, dataset: str, sub_dataset: str) -> dict[str, int]:
        """Returns {reason_name: count} for a subdataset."""
        return {
            reason.name: self._coarse.get((dataset, sub_dataset, reason), 0)
            for reason in DropReason
            if self._coarse.get((dataset, sub_dataset, reason), 0) > 0
        }

    def to_dataframe(self):
        """
        Export fine-grained drop log as a pd DataFrame.
        Columns: dataset, sub_dataset, reason, raw_event_type, raw_object_type, count
        """
        import pandas as pd

        rows = []
        for (ds, sub, reason, evt, obj), count in self._fine.items():
            rows.append({
                "dataset": ds,
                "sub_dataset": sub,
                "reason": reason.name,
                "raw_event_type": evt,
                "raw_object_type": obj,
                "count": count,
            })

        # add coarse entries that have no fine breakdown
        for (ds, sub, reason), count in self._coarse.items():
            fine_total = sum(
                c for (d, s, r, _, _), c in self._fine.items()
                if d == ds and s == sub and r == reason
            )
            if fine_total == 0 and count > 0:
                rows.append({
                    "dataset": ds,
                    "sub_dataset": sub,
                    "reason": reason.name,
                    "raw_event_type": "",
                    "raw_object_type": "",
                    "count": count,
                })

        return pd.DataFrame(rows)

    def coverage_dataframe(self):
        """
        Export kept/dropped/total summary per subdataset.
        """
        import pandas as pd

        keys = sorted(set(self._total_seen.keys()) | set(self._total_kept.keys()))
        rows = []
        for ds, sub in keys:
            seen = self._total_seen[(ds, sub)]
            kept = self._total_kept[(ds, sub)]
            rows.append({
                "dataset": ds,
                "sub_dataset": sub,
                "total_records": seen,
                "kept": kept,
                "dropped": seen - kept,
                "kept_pct": round(100 * kept / seen, 2) if seen > 0 else 0,
            })
        return pd.DataFrame(rows)

    def to_latex(self, path: str, table_type: str = "coverage") -> None:
        """Write a LaTeX table to disk. table_type: 'coverage' or 'fine'."""
        df = self.coverage_dataframe() if table_type == "coverage" else self.to_dataframe()
        with open(path, "w") as f:
            f.write(df.to_latex(index=False))
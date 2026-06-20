"""Speedup / parallel-efficiency computation, generalized over labeled
timings (node counts, layout names, etc.) rather than hardcoded to
1-vs-2-nodes.
"""
from __future__ import annotations


def compute_speedup(baseline_time: float, times: dict[str, float]) -> dict[str, dict]:
    """baseline_time: wall time of the reference run (typically the
    smallest parallelism, e.g. 1 node).
    times: {label: wall_time} for each configuration to compare, where the
    label may encode parallelism (e.g. "2" for 2 nodes, or a layout name).
    Returns {label: {'speedup': ..., 'efficiency_pct': ...}}.
    Efficiency is reported relative to a parallelism factor parsed from
    the label if it's numeric, else relative to speedup alone (factor=1).
    """
    results: dict[str, dict] = {}
    for label, t in times.items():
        speedup = baseline_time / t if t else float("inf")
        try:
            factor = float(label)
        except ValueError:
            factor = 1.0
        efficiency_pct = speedup / factor * 100.0 if factor else float("inf")
        results[label] = {"speedup": speedup, "efficiency_pct": efficiency_pct}
    return results

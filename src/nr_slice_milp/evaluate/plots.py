"""Plotting functions for judging solution quality and parallel scaling."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..config import ProblemConfig
from .parascip_log import parse_parascip_log


def plot_admission_quality(results: dict, cfg: ProblemConfig, out_path: str) -> None:
    names = cfg.slice_names
    admitted = [results["admitted"].get(s, 0) for s in names]
    totals = [cfg.n_b] * len(names)
    pct = [100.0 * a / t if t else 0.0 for a, t in zip(admitted, totals)]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(names, pct, color=["#3b82f6", "#ef4444", "#10b981"][: len(names)])
    for bar, a, t in zip(bars, admitted, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                 f"{a}/{t}", ha="center")
    ax.set_ylabel("Admission rate (%)")
    ax.set_title("Slice Admission Quality")
    ax.set_ylim(0, 110)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_rb_utilization(results: dict, cfg: ProblemConfig, out_path: str) -> None:
    util = results.get("avg_rb_util", 0.0)
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.pie([util, max(0.0, 100.0 - util)],
           labels=["Used", "Free"], autopct="%1.1f%%",
           colors=["#f59e0b", "#e5e7eb"])
    ax.set_title("Average RB Utilization")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_gap_convergence(log_paths: dict[str, str], out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    for label, log_file in log_paths.items():
        try:
            log = parse_parascip_log(log_file)
        except FileNotFoundError:
            print(f"Log file not found: {log_file}")
            continue
        gap = [
            abs(u - l) / max(abs(u), 1e-10) * 100.0
            for u, l in zip(log["bounds_ub"], log["bounds_lb"])
        ]
        style = "-" if log["header_found"] else "--"
        ax.plot(log["times"], gap, style, label=label)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("MIP Gap (%)")
    ax.set_title("Convergence: MIP Gap over Time")
    ax.set_yscale("log")
    ax.legend()
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ub_lb_convergence(log_paths: dict[str, str], out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    colors = plt.cm.tab10.colors
    for i, (label, log_file) in enumerate(log_paths.items()):
        try:
            log = parse_parascip_log(log_file)
        except FileNotFoundError:
            print(f"Log file not found: {log_file}")
            continue
        color = colors[i % len(colors)]
        ax.plot(log["times"], log["bounds_ub"], "--", color=color, alpha=0.7, label=f"{label} UB")
        ax.plot(log["times"], log["bounds_lb"], "-", color=color, label=f"{label} LB")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Objective Value")
    ax.set_title("UB/LB Convergence")
    ax.legend()
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_speedup_efficiency(timings: dict[str, float], baseline_label: str, out_path: str) -> None:
    from .speedup import compute_speedup

    baseline_time = timings[baseline_label]
    others = {k: v for k, v in timings.items() if k != baseline_label}
    speedup_data = compute_speedup(baseline_time, others)

    labels = list(speedup_data.keys())
    speedups = [speedup_data[l]["speedup"] for l in labels]
    efficiencies = [speedup_data[l]["efficiency_pct"] for l in labels]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.bar(labels, speedups, color="#3b82f6")
    ax1.set_ylabel("Speedup (x)")
    ax1.set_title(f"Speedup vs {baseline_label}")
    ax1.grid(True, axis="y", alpha=0.3)

    ax2.bar(labels, efficiencies, color="#10b981")
    ax2.set_ylabel("Parallel efficiency (%)")
    ax2.set_title("Efficiency")
    ax2.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

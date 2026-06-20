"""Evaluation entrypoint: wires summarize/plot/speedup together.

Replaces the old evaluate.py's dead __main__ block, which called
summarize_solution and plot_convergence but never compute_speedup --
here, --results passed for 2+ labels always triggers the speedup
computation and plot.
"""
from __future__ import annotations

import argparse
import json
import os

from ..config import ProblemConfig
from .parascip_log import parse_parascip_log
from .plots import (
    plot_admission_quality,
    plot_gap_convergence,
    plot_rb_utilization,
    plot_speedup_efficiency,
    plot_ub_lb_convergence,
)
from .speedup import compute_speedup


def _parse_kv_list(items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        label, _, path = item.partition("=")
        out[label] = path
    return out


def summarize_solution(results: dict, cfg: ProblemConfig) -> None:
    # results may come from either the HiGHS path (has solve_time/gap) or
    # the ParaSCIP .sol parser (objective/admitted/avg_rb_util only) -- so
    # every field beyond objective/admitted is treated as optional.
    print("\n" + "=" * 50)
    print("SOLUTION SUMMARY")
    print("=" * 50)
    obj = results.get("objective")
    print(f"Objective (weighted admissions): {obj:.2f}" if obj is not None
          else "Objective (weighted admissions): N/A")
    gap = results.get("gap")
    print(f"MIP gap: {gap * 100:.4f}%" if gap is not None else "MIP gap: N/A")
    solve_time = results.get("solve_time")
    print(f"Solve time: {solve_time:.1f}s" if solve_time is not None else "Solve time: N/A")

    total_possible = cfg.n_b * cfg.n_s
    total_admitted = sum(results["admitted"].values())
    print(f"\nTotal admitted: {total_admitted}/{total_possible} "
          f"({100.0 * total_admitted / total_possible:.1f}%)")
    for s, count in results["admitted"].items():
        print(f"  {s}: {count}/{cfg.n_b} ({100.0 * count / cfg.n_b:.1f}%)")

    print(f"\nAverage RB utilization: {results.get('avg_rb_util', 0):.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate solve results and generate plots.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--results", action="append",
                         help="label=path/to/results.json, repeatable")
    parser.add_argument("--logs", action="append",
                         help="label=path/to/parascip.log, repeatable")
    parser.add_argument("--out-dir", default="plots")
    args = parser.parse_args()

    cfg = ProblemConfig.from_yaml(args.config)
    os.makedirs(args.out_dir, exist_ok=True)

    results_paths = _parse_kv_list(args.results)
    log_paths = _parse_kv_list(args.logs)

    all_results: dict[str, dict] = {}
    for label, path in results_paths.items():
        with open(path) as f:
            r = json.load(f)
        all_results[label] = r
        summarize_solution(r, cfg)
        plot_admission_quality(r, cfg, os.path.join(args.out_dir, f"admission_{label}.png"))
        plot_rb_utilization(r, cfg, os.path.join(args.out_dir, f"rb_util_{label}.png"))

    if log_paths:
        plot_gap_convergence(log_paths, os.path.join(args.out_dir, "gap_convergence.png"))
        plot_ub_lb_convergence(log_paths, os.path.join(args.out_dir, "ub_lb_convergence.png"))

    # Build wall-clock timings for the speedup comparison. The HiGHS path
    # records solve_time directly; for ParaSCIP results (which lack it),
    # fall back to the last timestamp in the matching log, if one was given.
    timings: dict[str, float] = {}
    for label, r in all_results.items():
        t = r.get("solve_time")
        if t is None and label in log_paths:
            try:
                log = parse_parascip_log(log_paths[label])
                if log["times"]:
                    t = max(log["times"])
            except FileNotFoundError:
                t = None
        if t is not None:
            timings[label] = t

    if len(timings) >= 2:
        baseline_label = min(timings, key=lambda l: float(l) if l.replace(".", "").isdigit() else 0)
        speedup_data = compute_speedup(timings[baseline_label],
                                        {k: v for k, v in timings.items() if k != baseline_label})
        print("\nSpeedup / efficiency relative to", baseline_label)
        for label, d in speedup_data.items():
            print(f"  {label}: speedup={d['speedup']:.2f}x efficiency={d['efficiency_pct']:.1f}%")
        plot_speedup_efficiency(timings, baseline_label,
                                  os.path.join(args.out_dir, "speedup_efficiency.png"))
    elif len(all_results) >= 2:
        print("\nSkipping speedup: fewer than 2 results have a known solve time. "
              "Pass --solve-time to parse_solution or provide matching --logs.")

    print(f"\nPlots written to {args.out_dir}/")


if __name__ == "__main__":
    main()

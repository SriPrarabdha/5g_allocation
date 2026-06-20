"""Tiny end-to-end local sanity check: build + solve configs/problem_toy.yaml
with HiGHS and assert the result is in a sane range. No cluster/MPI/SCIP
dependency -- runs anywhere highspy is installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nr_slice_milp.config import ProblemConfig
from nr_slice_milp.model import build_model
from nr_slice_milp.solve_highs import solve_and_evaluate


def main() -> None:
    cfg_path = Path(__file__).resolve().parent.parent / "configs" / "problem_toy.yaml"
    cfg = ProblemConfig.from_yaml(str(cfg_path))

    h, meta = build_model(cfg)
    results = solve_and_evaluate(h, cfg, meta, results_path="/tmp/sanity_results.json")

    print("Row counts per constraint family:")
    for name, count in meta["row_counts"].items():
        print(f"  {name}: {count}")

    total_admitted = sum(results["admitted"].values())
    total_possible = cfg.n_b * cfg.n_s
    assert 0 <= total_admitted <= total_possible, "admitted count out of range"
    assert 0.0 <= results["avg_rb_util"] <= 100.0, "RB utilization out of range"
    assert results["gap"] is not None

    print(f"\nOK: objective={results['objective']:.2f} "
          f"admitted={total_admitted}/{total_possible} "
          f"avg_rb_util={results['avg_rb_util']:.1f}% "
          f"gap={results['gap']:.4f}")


if __name__ == "__main__":
    main()

"""HiGHS solve driver: single-node baseline / LP-relaxation warm-start path."""
from __future__ import annotations

import argparse
import json
import time

from .config import ProblemConfig
from .indexing import idx_a, idx_x
from .model import build_model


def solve_and_evaluate(h, cfg: ProblemConfig, meta: dict, results_path: str = "results.json") -> dict:
    start = time.time()
    h.run()
    solve_time = time.time() - start

    status = h.getModelStatus()
    obj = h.getInfoValue("objective_function_value")[1]
    gap = h.getInfoValue("mip_gap")[1]

    solution = h.getSolution()
    col_value = solution.col_value

    admitted = {name: 0 for name in cfg.slice_names}
    rb_used_total = 0
    for b in range(cfg.n_b):
        for s_idx, slc in enumerate(cfg.slices):
            if col_value[idx_x(b, s_idx, cfg)] > 0.5:
                admitted[slc.name] += 1
            for r in range(cfg.n_r):
                if col_value[idx_a(b, s_idx, r, cfg)] > 0.5:
                    rb_used_total += 1

    avg_rb_util = 100.0 * rb_used_total / (cfg.n_b * cfg.n_r) if cfg.n_b * cfg.n_r else 0.0

    results = {
        "status": str(status),
        "solve_time": solve_time,
        "objective": -obj,  # negated back to weighted-admissions maximization
        "gap": gap,
        "admitted": admitted,
        "avg_rb_util": avg_rb_util,
        "row_counts": meta["row_counts"],
    }
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    return results


def _main() -> None:
    parser = argparse.ArgumentParser(description="Build and solve the model with HiGHS.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--results-out", default="results.json")
    args = parser.parse_args()

    cfg = ProblemConfig.from_yaml(args.config)
    h, meta = build_model(cfg)
    results = solve_and_evaluate(h, cfg, meta, results_path=args.results_out)
    print(f"objective={results['objective']:.2f} gap={results['gap']:.4f} "
          f"solve_time={results['solve_time']:.1f}s")


if __name__ == "__main__":
    _main()

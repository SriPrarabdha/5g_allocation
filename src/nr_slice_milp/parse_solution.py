"""SCIP .sol parser.

Extended beyond the original prototype (which only parsed x_/t_ lines) to
also parse a_ variables, enabling RB-utilization reporting from ParaSCIP
solutions, not just the HiGHS path. Variable name patterns mirror
indexing.var_name_x/a/t exactly, so naming drift between export_mps.py and
this file is structurally impossible.
"""
from __future__ import annotations

import argparse
import json
import re

from .config import ProblemConfig

_RE_X = re.compile(r"^x_(\d+)_(\d+)$")
_RE_A = re.compile(r"^a_(\d+)_(\d+)_(\d+)$")
_RE_T = re.compile(r"^t_(\d+)_(\d+)$")


def parse_scip_solution(sol_file: str, cfg: ProblemConfig, solve_time: float | None = None) -> dict:
    vars_x: dict[tuple[int, int], bool] = {}
    vars_a: dict[tuple[int, int, int], bool] = {}
    vars_t: dict[tuple[int, int], float] = {}
    obj = None

    with open(sol_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("objective value:"):
                obj = float(line.split()[-1])
                continue

            parts = line.split()
            if len(parts) < 2:
                continue
            name, val_str = parts[0], parts[1]
            try:
                val = float(val_str)
            except ValueError:
                continue

            if m := _RE_X.match(name):
                b, si = int(m.group(1)), int(m.group(2))
                vars_x[(b, si)] = val > 0.5
            elif m := _RE_A.match(name):
                b, si, r = int(m.group(1)), int(m.group(2)), int(m.group(3))
                vars_a[(b, si, r)] = val > 0.5
            elif m := _RE_T.match(name):
                b, si = int(m.group(1)), int(m.group(2))
                vars_t[(b, si)] = val

    names = cfg.slice_names
    admitted = {
        s: sum(1 for (b, si), v in vars_x.items() if si == names.index(s) and v)
        for s in names
    }

    rb_used_total = sum(1 for v in vars_a.values() if v)
    avg_rb_util = (
        100.0 * rb_used_total / (cfg.n_b * cfg.n_r) if cfg.n_b * cfg.n_r else 0.0
    )

    result = {
        "objective": obj,
        "admitted": admitted,
        "avg_rb_util": avg_rb_util,
        "n_x_parsed": len(vars_x),
        "n_a_parsed": len(vars_a),
        "n_t_parsed": len(vars_t),
    }
    if solve_time is not None:
        # Recorded so the evaluate CLI can compute speedup for the ParaSCIP
        # path, which otherwise has no solve_time of its own.
        result["solve_time"] = solve_time
    return result


def _main() -> None:
    parser = argparse.ArgumentParser(description="Parse a SCIP .sol file.")
    parser.add_argument("sol_file")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="parsed_results.json")
    parser.add_argument("--solve-time", type=float, default=None,
                        help="Wall-clock solve time (s) to record for speedup analysis")
    args = parser.parse_args()

    cfg = ProblemConfig.from_yaml(args.config)
    result = parse_scip_solution(args.sol_file, cfg, solve_time=args.solve_time)

    print(f"Objective: {result['objective']:.4f}" if result["objective"] is not None else "Objective: N/A")
    for s, count in result["admitted"].items():
        print(f"  {s}: {count} gNBs admitted")
    print(f"Average RB utilization: {result['avg_rb_util']:.1f}%")

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    _main()

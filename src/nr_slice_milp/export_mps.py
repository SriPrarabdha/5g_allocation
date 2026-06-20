"""MPS export and the variable-naming fix.

The original prototype called h.addVars(N_VARS, lb, ub) with no names
argument, so HiGHS assigned generic column names (C0, C1, ...) on MPS
export -- this silently broke the SCIP .sol parser downstream, which
expects literal x_<b>_<si> / a_<b>_<si>_<r> / t_<b>_<si> names. Fix:
call h.passColName(idx, name) for every variable, using the same naming
functions parse_solution.py's regexes are built against, before any
writeModel() call.
"""
from __future__ import annotations

import argparse

from .config import ProblemConfig
from .indexing import idx_a, idx_t, idx_x, var_name_a, var_name_t, var_name_x


def assign_variable_names(h, cfg: ProblemConfig) -> None:
    for b in range(cfg.n_b):
        for s_idx in range(cfg.n_s):
            h.passColName(idx_x(b, s_idx, cfg), var_name_x(b, s_idx, cfg))
            h.passColName(idx_t(b, s_idx, cfg), var_name_t(b, s_idx, cfg))
            for r in range(cfg.n_r):
                h.passColName(idx_a(b, s_idx, r, cfg), var_name_a(b, s_idx, r, cfg))


def write_mps(h, path: str) -> None:
    h.writeModel(path)


def _main() -> None:
    from .model import build_model

    parser = argparse.ArgumentParser(description="Build the model and export it to MPS.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    cfg = ProblemConfig.from_yaml(args.config)
    h, _meta = build_model(cfg)
    write_mps(h, args.out)
    print(f"MPS written to {args.out}")


if __name__ == "__main__":
    _main()

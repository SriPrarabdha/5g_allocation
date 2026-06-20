"""Flat variable indexing and naming.

Variable ordering: [x_{b,s}: N_B*N_S] [a_{b,s,r}: N_B*N_S*N_R] [t_{b,s}: N_B*N_S]

Naming functions live here (not in export_mps.py or parse_solution.py)
so both the MPS-export naming and the .sol-parsing regexes are generated
from / checked against the exact same convention.
"""
from __future__ import annotations

from .config import ProblemConfig


def idx_x(b: int, s_idx: int, cfg: ProblemConfig) -> int:
    return b * cfg.n_s + s_idx


def idx_a(b: int, s_idx: int, r: int, cfg: ProblemConfig) -> int:
    offset = cfg.n_b * cfg.n_s
    return offset + b * cfg.n_s * cfg.n_r + s_idx * cfg.n_r + r


def idx_t(b: int, s_idx: int, cfg: ProblemConfig) -> int:
    offset = cfg.n_b * cfg.n_s + cfg.n_b * cfg.n_s * cfg.n_r
    return offset + b * cfg.n_s + s_idx


def n_vars(cfg: ProblemConfig) -> int:
    return cfg.n_b * cfg.n_s * (2 + cfg.n_r)


def var_name_x(b: int, s_idx: int, cfg: ProblemConfig) -> str:
    return f"x_{b}_{s_idx}"


def var_name_a(b: int, s_idx: int, r: int, cfg: ProblemConfig) -> str:
    return f"a_{b}_{s_idx}_{r}"


def var_name_t(b: int, s_idx: int, cfg: ProblemConfig) -> str:
    return f"t_{b}_{s_idx}"

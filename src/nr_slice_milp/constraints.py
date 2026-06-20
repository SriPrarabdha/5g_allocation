"""Constraint families C1-C9, one function per family.

Splitting these out of a single build_model() makes each independently
unit-testable against a tiny config (e.g. assert C1's row count equals
n_b*n_r exactly, inspect one row's (indices, values) against the expected
linear expression).

Each add_c*() takes the HiGHS model handle plus whatever data it needs and
returns the number of rows it added, so model.py can log/verify counts
against the closed-form formulas in README.
"""
from __future__ import annotations

import networkx as nx

from .config import ProblemConfig
from .indexing import idx_a, idx_t, idx_x

# HiGHS treats any bound with absolute value >= kHighsInf (1e30) as
# infinity. Use this sentinel rather than Python's float('inf') for one-
# sided rows, matching HiGHS' own convention.
INF = 1.0e30


def add_c1_rb_exclusivity(h, cfg: ProblemConfig) -> int:
    """Sum_s a_{b,s,r} <= 1, for each (b, r)."""
    rows = 0
    for b in range(cfg.n_b):
        for r in range(cfg.n_r):
            indices = [idx_a(b, s_idx, r, cfg) for s_idx in range(cfg.n_s)]
            values = [1.0] * cfg.n_s
            h.addRow(0.0, 1.0, len(indices), indices, values)
            rows += 1
    return rows


def add_c2_capacity(h, cfg: ProblemConfig) -> int:
    """Sum_{s,r} a_{b,s,r} <= N_R (total RBs available at the gNB), for each b."""
    rows = 0
    for b in range(cfg.n_b):
        indices = [
            idx_a(b, s_idx, r, cfg) for s_idx in range(cfg.n_s) for r in range(cfg.n_r)
        ]
        values = [1.0] * len(indices)
        h.addRow(0.0, float(cfg.n_r), len(indices), indices, values)
        rows += 1
    return rows


def add_c3_throughput_link(h, cfg: ProblemConfig, eff: dict[tuple[int, int], float]) -> int:
    """t_{b,s} - Sum_r a_{b,s,r} * W_rb * eff_{b,s} <= 0, for each (b, s)."""
    rows = 0
    for b in range(cfg.n_b):
        for s_idx in range(cfg.n_s):
            coeff = cfg.rb_bandwidth_mhz * eff[(b, s_idx)]
            indices = [idx_t(b, s_idx, cfg)] + [
                idx_a(b, s_idx, r, cfg) for r in range(cfg.n_r)
            ]
            values = [1.0] + [-coeff] * cfg.n_r
            h.addRow(-INF, 0.0, len(indices), indices, values)
            rows += 1
    return rows


def add_c4_sla(h, cfg: ProblemConfig) -> int:
    """t_{b,s} - T_s_min * x_{b,s} >= 0, for each (b, s)."""
    rows = 0
    for b in range(cfg.n_b):
        for s_idx, slc in enumerate(cfg.slices):
            indices = [idx_t(b, s_idx, cfg), idx_x(b, s_idx, cfg)]
            values = [1.0, -slc.t_min_mbps]
            h.addRow(0.0, INF, len(indices), indices, values)
            rows += 1
    return rows


def add_c5_min_rb(h, cfg: ProblemConfig) -> int:
    """Sum_r a_{b,s,r} - RB_s_min * x_{b,s} >= 0, for each (b, s)."""
    rows = 0
    for b in range(cfg.n_b):
        for s_idx, slc in enumerate(cfg.slices):
            indices = [idx_a(b, s_idx, r, cfg) for r in range(cfg.n_r)] + [
                idx_x(b, s_idx, cfg)
            ]
            values = [1.0] * cfg.n_r + [-float(slc.rb_min)]
            h.addRow(0.0, INF, len(indices), indices, values)
            rows += 1
    return rows


def add_c6_max_rb(h, cfg: ProblemConfig) -> int:
    """Sum_r a_{b,s,r} - RB_s_max * x_{b,s} <= 0, for each (b, s)."""
    rows = 0
    for b in range(cfg.n_b):
        for s_idx, slc in enumerate(cfg.slices):
            indices = [idx_a(b, s_idx, r, cfg) for r in range(cfg.n_r)] + [
                idx_x(b, s_idx, cfg)
            ]
            values = [1.0] * cfg.n_r + [-float(slc.rb_max)]
            h.addRow(-INF, 0.0, len(indices), indices, values)
            rows += 1
    return rows


def add_c7_rb_admission_link(h, cfg: ProblemConfig) -> int:
    """a_{b,s,r} - x_{b,s} <= 0, for each (b, s, r)."""
    rows = 0
    for b in range(cfg.n_b):
        for s_idx in range(cfg.n_s):
            x_i = idx_x(b, s_idx, cfg)
            for r in range(cfg.n_r):
                indices = [idx_a(b, s_idx, r, cfg), x_i]
                values = [1.0, -1.0]
                h.addRow(-INF, 0.0, len(indices), indices, values)
                rows += 1
    return rows


def add_c8_interference(
    h,
    cfg: ProblemConfig,
    edges: list[tuple[int, int]],
    alpha: dict[tuple[int, int], float] | None,
) -> int:
    """Sum_s a_{b,s,r} + Sum_s a_{b',s,r} <= 1 + 1[alpha_{b,b'} < alpha_thresh],
    for each interfering edge (b, b') and each RB r.

    When cfg.use_alpha_threshold is False, the conditional relaxation term
    is dropped and every edge gets the conservative `<= 1` bound regardless
    of alpha -- kept available for A/B comparison against the original
    (overly conservative) prototype behavior.
    """
    rows = 0
    for b, bp in edges:
        if cfg.use_alpha_threshold and alpha is not None and alpha[(b, bp)] < cfg.alpha_thresh:
            rhs = 2.0
        else:
            rhs = 1.0
        for r in range(cfg.n_r):
            indices = [idx_a(b, s_idx, r, cfg) for s_idx in range(cfg.n_s)] + [
                idx_a(bp, s_idx, r, cfg) for s_idx in range(cfg.n_s)
            ]
            values = [1.0] * (2 * cfg.n_s)
            h.addRow(0.0, rhs, len(indices), indices, values)
            rows += 1
    return rows


def add_c9_urllc_isolation(h, cfg: ProblemConfig) -> int:
    """a_{b,URLLC,r} + a_{b,eMBB,r} <= 1, for each (b, r)."""
    names = cfg.slice_names
    urllc_idx = names.index("URLLC")
    embb_idx = names.index("eMBB")
    rows = 0
    for b in range(cfg.n_b):
        for r in range(cfg.n_r):
            indices = [idx_a(b, urllc_idx, r, cfg), idx_a(b, embb_idx, r, cfg)]
            values = [1.0, 1.0]
            h.addRow(0.0, 1.0, len(indices), indices, values)
            rows += 1
    return rows

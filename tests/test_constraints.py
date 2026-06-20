"""Constraint row-count / coefficient tests using a lightweight fake HiGHS
handle (just records addRow calls) so these tests don't require highspy
to be installed -- they exercise pure constraint-building logic only.
"""
from __future__ import annotations

import pytest

from nr_slice_milp import constraints as C
from nr_slice_milp.constraints import INF
from nr_slice_milp.config import ProblemConfig
from nr_slice_milp.indexing import idx_a, idx_x
from nr_slice_milp.network import build_alpha, build_eff, build_interference_graph


class FakeHighs:
    def __init__(self):
        self.rows = []  # list of (lo, hi, indices, values)

    def addRow(self, lo, hi, nnz, indices, values):
        assert nnz == len(indices) == len(values)
        self.rows.append((lo, hi, list(indices), list(values)))


CFG = ProblemConfig(n_b=3, n_r=4)


def test_c1_row_count_and_row_content():
    h = FakeHighs()
    rows = C.add_c1_rb_exclusivity(h, CFG)
    assert rows == CFG.n_b * CFG.n_r
    assert len(h.rows) == rows
    lo, hi, indices, values = h.rows[0]
    assert (lo, hi) == (0.0, 1.0)
    expected_indices = [idx_a(0, s, 0, CFG) for s in range(CFG.n_s)]
    assert sorted(indices) == sorted(expected_indices)
    assert values == [1.0] * CFG.n_s


def test_c2_row_count():
    h = FakeHighs()
    rows = C.add_c2_capacity(h, CFG)
    assert rows == CFG.n_b
    _, hi, indices, _ = h.rows[0]
    assert hi == float(CFG.n_r)
    assert len(indices) == CFG.n_s * CFG.n_r


def test_c3_row_count():
    h = FakeHighs()
    eff = build_eff(CFG)
    rows = C.add_c3_throughput_link(h, CFG, eff)
    assert rows == CFG.n_b * CFG.n_s


def test_c4_c5_c6_row_counts():
    h = FakeHighs()
    assert C.add_c4_sla(h, CFG) == CFG.n_b * CFG.n_s
    h = FakeHighs()
    assert C.add_c5_min_rb(h, CFG) == CFG.n_b * CFG.n_s
    h = FakeHighs()
    assert C.add_c6_max_rb(h, CFG) == CFG.n_b * CFG.n_s


def test_c7_row_count():
    h = FakeHighs()
    rows = C.add_c7_rb_admission_link(h, CFG)
    assert rows == CFG.n_b * CFG.n_s * CFG.n_r
    lo, hi, indices, values = h.rows[0]
    assert (lo, hi) == (-INF, 0.0)
    assert values == [1.0, -1.0]


def test_c8_row_count_and_alpha_threshold_effect():
    graph = build_interference_graph(CFG)
    edges = list(graph.edges())
    alpha = build_alpha(CFG, graph)

    h = FakeHighs()
    rows = C.add_c8_interference(h, CFG, edges, alpha)
    assert rows == len(edges) * CFG.n_r

    # rhs should be 1.0 for high-alpha edges, 2.0 for low-alpha edges when
    # use_alpha_threshold=True (the default in CFG).
    seen_rhs = {round(r[1], 4) for r in h.rows}
    assert seen_rhs <= {1.0, 2.0}


def test_c8_disabled_alpha_threshold_always_conservative():
    cfg = ProblemConfig(n_b=CFG.n_b, n_r=CFG.n_r, use_alpha_threshold=False)
    graph = build_interference_graph(cfg)
    edges = list(graph.edges())

    h = FakeHighs()
    C.add_c8_interference(h, cfg, edges, alpha=None)
    assert all(r[1] == 1.0 for r in h.rows)


def test_c9_row_count_uses_urllc_and_embb():
    h = FakeHighs()
    rows = C.add_c9_urllc_isolation(h, CFG)
    assert rows == CFG.n_b * CFG.n_r
    names = CFG.slice_names
    urllc_idx = names.index("URLLC")
    embb_idx = names.index("eMBB")
    _, _, indices, _ = h.rows[0]
    assert idx_a(0, urllc_idx, 0, CFG) in indices
    assert idx_a(0, embb_idx, 0, CFG) in indices

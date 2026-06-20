"""Model assembly: wires together network/eff/alpha generation, variable
bounds/integrality, the objective, and the C1-C9 constraint families.
"""
from __future__ import annotations

import highspy
import numpy as np

from . import constraints as C
from .config import ProblemConfig
from .export_mps import assign_variable_names
from .indexing import idx_x, n_vars
from .network import build_alpha, build_eff, build_interference_graph


def build_model(cfg: ProblemConfig) -> tuple["highspy.Highs", dict]:
    """Returns (h, meta). meta carries eff/graph/edges/alpha/row_counts so
    callers (e.g. evaluate/plots.py) can report constraint-family sizes
    without recomputing them.
    """
    graph = build_interference_graph(cfg)
    edges = list(graph.edges())
    alpha = build_alpha(cfg, graph) if cfg.use_alpha_threshold else None
    eff = build_eff(cfg)

    n_v = n_vars(cfg)
    # Variable layout is [x][a][t] (see indexing.py): x and a occupy the
    # first n_bin columns (binary), t the final n_cont columns (continuous).
    n_bin = cfg.n_b * cfg.n_s + cfg.n_b * cfg.n_s * cfg.n_r  # x + a
    n_cont = cfg.n_b * cfg.n_s  # t

    cost = np.zeros(n_v, dtype=np.float64)
    for b in range(cfg.n_b):
        for s_idx, slc in enumerate(cfg.slices):
            cost[idx_x(b, s_idx, cfg)] = -slc.weight  # negated -> maximize admissions

    lower = np.zeros(n_v, dtype=np.float64)
    upper = np.empty(n_v, dtype=np.float64)
    upper[:n_bin] = 1.0
    upper[n_bin:] = 1.0e6

    h = highspy.Highs()
    # Add all columns with objective/bounds in one shot, no matrix entries
    # yet. addCols creates continuous columns by default.
    h.addCols(
        n_v,
        cost,
        lower,
        upper,
        0,
        np.array([], dtype=np.int32),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.float64),
    )
    # Flip x and a to integer (the first n_bin columns); t stays continuous.
    # Use the scalar setter with an actual HighsVarType enum instance -- this
    # is stable across highspy versions, unlike the batch form whose
    # integrality-array binding differs between releases.
    for i in range(n_bin):
        h.changeColIntegrality(i, highspy.HighsVarType.kInteger)

    row_counts = {
        "C1_rb_exclusivity": C.add_c1_rb_exclusivity(h, cfg),
        "C2_capacity": C.add_c2_capacity(h, cfg),
        "C3_throughput_link": C.add_c3_throughput_link(h, cfg, eff),
        "C4_sla": C.add_c4_sla(h, cfg),
        "C5_min_rb": C.add_c5_min_rb(h, cfg),
        "C6_max_rb": C.add_c6_max_rb(h, cfg),
        "C7_rb_admission_link": C.add_c7_rb_admission_link(h, cfg),
        "C8_interference": C.add_c8_interference(h, cfg, edges, alpha),
        "C9_urllc_isolation": C.add_c9_urllc_isolation(h, cfg),
    }

    assign_variable_names(h, cfg)

    meta = {
        "graph": graph,
        "edges": edges,
        "alpha": alpha,
        "eff": eff,
        "row_counts": row_counts,
        "n_vars": n_v,
    }
    return h, meta

"""Interference topology and per-gNB/slice radio efficiency.

The interference graph is a random geometric graph, not a literal
hexagonal grid -- the original prototype named this function
`hex_grid_graph` despite calling `nx.random_geometric_graph` under the
hood. Renamed here to `build_interference_graph` to match what it
actually does; see README "Known Simplifications" for the rationale on
why a real hex grid wasn't implemented.
"""
from __future__ import annotations

import math

import networkx as nx
import numpy as np

from .config import ProblemConfig


def build_interference_graph(cfg: ProblemConfig) -> nx.Graph:
    """Random geometric graph used as an interference-topology proxy.

    nx.random_geometric_graph stores each node's random position in
    graph.nodes[n]['pos'] by construction -- build_alpha() reuses these
    positions, so no additional randomness/seeding is introduced.
    """
    return nx.random_geometric_graph(
        cfg.n_b, radius=cfg.interference_radius, seed=cfg.interference_seed
    )


def build_alpha(cfg: ProblemConfig, graph: nx.Graph) -> dict[tuple[int, int], float]:
    """Per-edge interference factor alpha_{b,b'} in [0, 1].

    Deterministic function of the existing graph positions: closer gNBs
    (smaller distance relative to the connection radius) interfere more
    strongly, so alpha = clip(1 - dist/radius, 0, 1). This is a reasonable
    physical proxy (closer cells co-channel-interfere more) but is not a
    measured/simulated RF propagation model.
    """
    pos = nx.get_node_attributes(graph, "pos")
    alpha: dict[tuple[int, int], float] = {}
    for b, bp in graph.edges():
        dx = pos[b][0] - pos[bp][0]
        dy = pos[b][1] - pos[bp][1]
        dist = math.hypot(dx, dy)
        alpha[(b, bp)] = max(0.0, min(1.0, 1.0 - dist / cfg.interference_radius))
    return alpha


def build_eff(cfg: ProblemConfig) -> dict[tuple[int, int], float]:
    """Per-(gNB, slice-index) spectral efficiency, Mbps per RB per W_rb MHz."""
    rng = np.random.default_rng(cfg.eff_seed)
    return {
        (b, s_idx): float(rng.uniform(cfg.eff_low, cfg.eff_high))
        for b in range(cfg.n_b)
        for s_idx in range(cfg.n_s)
    }

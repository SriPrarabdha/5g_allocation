from nr_slice_milp.config import ProblemConfig
from nr_slice_milp.network import build_alpha, build_eff, build_interference_graph

CFG = ProblemConfig(n_b=30, n_r=4, interference_radius=0.3, interference_seed=42)


def test_graph_is_deterministic():
    g1 = build_interference_graph(CFG)
    g2 = build_interference_graph(CFG)
    assert set(g1.edges()) == set(g2.edges())
    assert g1.number_of_nodes() == CFG.n_b


def test_alpha_in_unit_interval_and_monotonic_in_distance():
    import math

    g = build_interference_graph(CFG)
    alpha = build_alpha(CFG, g)
    pos = g.nodes(data="pos")
    pos = dict(pos)

    assert len(alpha) == g.number_of_edges()
    for (b, bp), a in alpha.items():
        assert 0.0 <= a <= 1.0
        dist = math.hypot(pos[b][0] - pos[bp][0], pos[b][1] - pos[bp][1])
        expected = max(0.0, min(1.0, 1.0 - dist / CFG.interference_radius))
        assert abs(a - expected) < 1e-9


def test_eff_deterministic_and_in_range():
    eff1 = build_eff(CFG)
    eff2 = build_eff(CFG)
    assert eff1 == eff2
    assert len(eff1) == CFG.n_b * CFG.n_s
    for v in eff1.values():
        assert CFG.eff_low <= v <= CFG.eff_high

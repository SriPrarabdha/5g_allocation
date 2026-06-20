import re

from nr_slice_milp.config import ProblemConfig
from nr_slice_milp.indexing import (
    idx_a,
    idx_t,
    idx_x,
    n_vars,
    var_name_a,
    var_name_t,
    var_name_x,
)

TINY_CFG = ProblemConfig(n_b=3, n_r=4)


def test_bijective_no_collisions():
    seen = set()
    cfg = TINY_CFG
    for b in range(cfg.n_b):
        for s in range(cfg.n_s):
            seen.add(idx_x(b, s, cfg))
            seen.add(idx_t(b, s, cfg))
            for r in range(cfg.n_r):
                seen.add(idx_a(b, s, r, cfg))
    expected = cfg.n_b * cfg.n_s * 2 + cfg.n_b * cfg.n_s * cfg.n_r
    assert len(seen) == expected
    assert n_vars(cfg) == expected


def test_max_index_matches_n_vars_minus_one():
    cfg = TINY_CFG
    last_b, last_s, last_r = cfg.n_b - 1, cfg.n_s - 1, cfg.n_r - 1
    assert idx_a(last_b, last_s, last_r, cfg) == n_vars(cfg) - 1


def test_name_roundtrip():
    cfg = TINY_CFG
    name = var_name_a(2, 1, 3, cfg)
    m = re.match(r"a_(\d+)_(\d+)_(\d+)", name)
    assert m is not None
    assert m.groups() == ("2", "1", "3")

    name = var_name_x(2, 1, cfg)
    m = re.match(r"x_(\d+)_(\d+)", name)
    assert m.groups() == ("2", "1")

    name = var_name_t(2, 1, cfg)
    m = re.match(r"t_(\d+)_(\d+)", name)
    assert m.groups() == ("2", "1")

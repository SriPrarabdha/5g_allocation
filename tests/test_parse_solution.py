import json

from nr_slice_milp.config import ProblemConfig
from nr_slice_milp.parse_solution import parse_scip_solution

CFG = ProblemConfig(n_b=2, n_r=3)


def _write_fake_sol(path, lines):
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def test_parse_x_a_t_and_admission_counts(tmp_path):
    sol_file = tmp_path / "fake.sol"
    _write_fake_sol(sol_file, [
        "objective value:                 8.0",
        "x_0_0                            1",
        "x_0_1                            0",
        "x_1_0                            1",
        "a_0_0_0                          1",
        "a_0_0_1                          1",
        "a_0_0_2                          0",
        "t_0_0                            120.5",
    ])

    result = parse_scip_solution(str(sol_file), CFG)

    assert result["objective"] == 8.0
    assert result["admitted"]["eMBB"] == 2
    assert result["admitted"]["URLLC"] == 0
    assert result["n_a_parsed"] == 3
    assert result["n_t_parsed"] == 1
    # avg_rb_util = used a_ vars (2 true) / (n_b * n_r) = 2 / (2*3)
    assert abs(result["avg_rb_util"] - (200.0 / 6.0)) < 1e-6


def test_parse_handles_empty_lines_and_unmatched_names(tmp_path):
    sol_file = tmp_path / "fake.sol"
    _write_fake_sol(sol_file, [
        "objective value:                 0.0",
        "",
        "some_other_var                   1",
    ])
    result = parse_scip_solution(str(sol_file), CFG)
    assert result["objective"] == 0.0
    assert result["n_x_parsed"] == 0
    assert result["n_a_parsed"] == 0

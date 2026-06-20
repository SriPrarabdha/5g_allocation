import warnings

from nr_slice_milp.evaluate.parascip_log import parse_parascip_log
from nr_slice_milp.evaluate.speedup import compute_speedup

FIXTURE_STANDARD = """\
SCIP version 9.1.0
  time | node  | left |LP iter|LP it/n| mem |mdpt |frac|vars|cons|cols|rows|cuts|confs|strbr|  dualbound | primalbound |  gap   |
   1.2 |     1 |    0 |    50 |  50.0 | 10.0|   0 | 0.0|100 |200 |100 |200 |  0 |   0 |   0 |  10.000000 |  50.000000  | 400.00%|
   5.4 |    10 |    2 |   500 |  50.0 | 12.0|   1 | 0.0|100 |200 |100 |200 |  0 |   0 |   0 |  20.000000 |  40.000000  | 100.00%|
  10.1 |    50 |    4 |  2000 |  40.0 | 15.0|   2 | 0.0|100 |200 |100 |200 |  0 |   0 |   0 |  30.000000 |  32.000000  |  6.67% |
"""

FIXTURE_REORDERED = """\
SCIP version 9.1.0
  primalbound | time | dualbound | other |
   50.000000  |  1.2 |  10.000000 |   1   |
   40.000000  |  5.4 |  20.000000 |   2   |
   32.000000  | 10.1 |  30.000000 |   3   |
"""

FIXTURE_NO_HEADER = """\
some unrelated log content
with no recognizable table at all
"""


def test_header_driven_parsing_standard_order(tmp_path):
    log_file = tmp_path / "standard.log"
    log_file.write_text(FIXTURE_STANDARD)

    result = parse_parascip_log(str(log_file))
    assert result["header_found"] is True
    assert result["times"] == [1.2, 5.4, 10.1]
    assert result["bounds_ub"] == [50.0, 40.0, 32.0]
    assert result["bounds_lb"] == [10.0, 20.0, 30.0]


def test_header_driven_parsing_reordered_columns(tmp_path):
    log_file = tmp_path / "reordered.log"
    log_file.write_text(FIXTURE_REORDERED)

    result = parse_parascip_log(str(log_file))
    assert result["header_found"] is True
    assert result["times"] == [1.2, 5.4, 10.1]
    assert result["bounds_ub"] == [50.0, 40.0, 32.0]
    assert result["bounds_lb"] == [10.0, 20.0, 30.0]


def test_falls_back_with_warning_when_no_header(tmp_path):
    log_file = tmp_path / "noheader.log"
    log_file.write_text(FIXTURE_NO_HEADER)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = parse_parascip_log(str(log_file))
        assert any("falling back" in str(warning.message) for warning in w)
    assert result["header_found"] is False


def test_compute_speedup_basic():
    result = compute_speedup(100.0, {"2": 60.0, "4": 40.0})
    assert abs(result["2"]["speedup"] - 100.0 / 60.0) < 1e-9
    assert abs(result["2"]["efficiency_pct"] - (100.0 / 60.0) / 2 * 100) < 1e-6
    assert abs(result["4"]["speedup"] - 2.5) < 1e-9
    assert abs(result["4"]["efficiency_pct"] - 2.5 / 4 * 100) < 1e-6


def test_compute_speedup_non_numeric_label_defaults_factor_one():
    result = compute_speedup(100.0, {"layout-A": 50.0})
    assert abs(result["layout-A"]["speedup"] - 2.0) < 1e-9
    assert abs(result["layout-A"]["efficiency_pct"] - 200.0) < 1e-9

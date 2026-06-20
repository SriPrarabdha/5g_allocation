"""Header-driven ParaSCIP/fscip stdout log parser.

The original prototype used a fixed positional regex
(r'\\|\\s*([\\d.]+)\\s*\\|.*?\\|\\s*([\\d.e+\\-]+)\\s*\\|\\s*([\\d.e+\\-]+)\\s*\\|')
that was an unverified guess at the real fscip table format -- it would
silently misparse if the real column order/count differs.

This version instead locates the header row, matches known SCIP-table
column-name tokens to find positions for time / dual bound (lower bound)
/ primal bound (upper bound), then parses each subsequent row positionally
against those columns. Falls back to a legacy heuristic (with a loud
`header_found=False` flag) if no recognizable header is found, so callers
can detect when the lower-confidence path was used.

IMPORTANT: this has not been validated against a real fscip log capture
(none was available in this environment). The first real cluster run's
log MUST be inspected and diffed against tests/fixtures/parascip_log_*.txt
before trusting any plot generated from it -- see README "Known
Simplifications" / verification plan.
"""
from __future__ import annotations

import re
import warnings

_TIME_TOKENS = ("time",)
_UB_TOKENS = ("primalbound", "ub", "primal")
_LB_TOKENS = ("dualbound", "lb", "dual")

_LEGACY_RE = re.compile(
    r"\|\s*([\d.]+)\s*\|.*?\|\s*([\d.e+\-]+)\s*\|\s*([\d.e+\-]+)\s*\|"
)


def _find_column(tokens: list[str], candidates: tuple[str, ...]) -> int | None:
    for i, tok in enumerate(tokens):
        norm = tok.lower().replace(" ", "")
        if any(c in norm for c in candidates):
            return i
    return None


def _try_parse_header(line: str) -> dict[str, int] | None:
    if "|" not in line:
        return None
    tokens = [t.strip() for t in line.strip().strip("|").split("|")]
    time_col = _find_column(tokens, _TIME_TOKENS)
    ub_col = _find_column(tokens, _UB_TOKENS)
    lb_col = _find_column(tokens, _LB_TOKENS)
    if time_col is None or ub_col is None or lb_col is None:
        return None
    return {"time": time_col, "ub": ub_col, "lb": lb_col}


def parse_parascip_log(log_file: str) -> dict:
    """Returns {'times': [...], 'bounds_ub': [...], 'bounds_lb': [...],
    'header_found': bool}.
    """
    times: list[float] = []
    bounds_ub: list[float] = []
    bounds_lb: list[float] = []
    columns: dict[str, int] | None = None

    with open(log_file) as f:
        for line in f:
            if columns is None:
                columns = _try_parse_header(line)
                continue

            if "|" not in line:
                continue
            tokens = [t.strip() for t in line.strip().strip("|").split("|")]
            if len(tokens) <= max(columns.values()):
                continue
            try:
                t = float(tokens[columns["time"]])
                ub = float(tokens[columns["ub"]])
                lb = float(tokens[columns["lb"]])
            except (ValueError, IndexError):
                continue
            times.append(t)
            bounds_ub.append(ub)
            bounds_lb.append(lb)

    if columns is not None and times:
        return {
            "times": times,
            "bounds_ub": bounds_ub,
            "bounds_lb": bounds_lb,
            "header_found": True,
        }

    warnings.warn(
        f"No recognizable SCIP-table header found in {log_file}; "
        "falling back to legacy positional-regex heuristic. Treat results "
        "with low confidence and validate against the real log format.",
        stacklevel=2,
    )
    times, bounds_ub, bounds_lb = [], [], []
    with open(log_file) as f:
        for line in f:
            m = _LEGACY_RE.search(line)
            if m:
                try:
                    times.append(float(m.group(1)))
                    bounds_ub.append(float(m.group(2)))
                    bounds_lb.append(float(m.group(3)))
                except ValueError:
                    pass

    return {
        "times": times,
        "bounds_ub": bounds_ub,
        "bounds_lb": bounds_lb,
        "header_found": False,
    }

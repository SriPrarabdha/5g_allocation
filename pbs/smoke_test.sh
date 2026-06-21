#!/bin/bash
# 60-second SCIP smoke test on the exported MPS file, before committing
# a full PBS walltime budget to a real ParaSCIP run.
set -euo pipefail

MPS_FILE=${1:-5gnr_slice.mps}
SCIP_BIN="${SCIP_BIN:-$(command -v scip || echo "$HOME/scip_install/bin/scip")}"

"$SCIP_BIN" -f "$MPS_FILE" -c "set limits/time 60" -c "optimize" -c "quit"

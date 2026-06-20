#!/bin/bash
# 60-second SCIP smoke test on the exported MPS file, before committing
# a full PBS walltime budget to a real ParaSCIP run.
set -euo pipefail

MPS_FILE=${1:-5gnr_slice.mps}

$HOME/scip_install/bin/scip -f "$MPS_FILE" -c "set limits/time 60" -c "optimize" -c "quit"

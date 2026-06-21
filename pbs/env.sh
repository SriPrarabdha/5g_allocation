# Shared environment setup, sourced by every PBS job script (after any
# `module load` lines). Edit the conda env name / solver paths here ONCE
# instead of in each script.
#
# Override per submission, e.g.:
#   qsub -v CONDA_ENV=otherenv pbs/run_highs_1node.pbs

CONDA_ENV="${CONDA_ENV:-penv}"

# --- Initialize conda for this (non-interactive) shell, then activate ---
_CONDA_BASE=""
if command -v conda >/dev/null 2>&1; then
    _CONDA_BASE="$(conda info --base 2>/dev/null)"
fi
for _b in "$_CONDA_BASE" "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/conda"; do
    if [ -n "$_b" ] && [ -f "$_b/etc/profile.d/conda.sh" ]; then
        # shellcheck disable=SC1090
        source "$_b/etc/profile.d/conda.sh"
        break
    fi
done
conda activate "$CONDA_ENV" \
    || echo "WARN: could not 'conda activate $CONDA_ENV' -- is the env name right?"

# --- Make the package importable even without `pip install -e .` ---
export PYTHONPATH="$PWD/src:$PYTHONPATH"

# --- Solver binaries ---
# SCIP usually comes from conda (on PATH). fscip/ParaSCIP must be compiled
# (README S4.2) -- once built, point FSCIP_BIN at it (or just have it on PATH).
export SCIP_BIN="${SCIP_BIN:-$(command -v scip || echo "$HOME/scip_install/bin/scip")}"
export FSCIP_BIN="${FSCIP_BIN:-$(command -v fscip || echo "$HOME/scip_install/bin/fscip")}"

echo "[env.sh] conda env=${CONDA_DEFAULT_ENV:-none} python=$(command -v python || echo none)"
echo "[env.sh] SCIP_BIN=$SCIP_BIN"
echo "[env.sh] FSCIP_BIN=$FSCIP_BIN"

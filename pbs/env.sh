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

# Guard: catch a stale/inherited CONDA_ENV activating the wrong env silently.
# (PBS can carry an exported CONDA_ENV from the submitting shell into the job,
# overriding the 'penv' default above.)
if [ -n "${CONDA_DEFAULT_ENV:-}" ] && [ "${CONDA_DEFAULT_ENV}" != "$CONDA_ENV" ]; then
    echo "WARN: requested env '$CONDA_ENV' but active env is '$CONDA_DEFAULT_ENV'" \
         "-- an inherited CONDA_ENV may be overriding the default; 'unset CONDA_ENV' to fix."
fi

# --- Make the package importable even without `pip install -e .` ---
export PYTHONPATH="$PWD/src:$PYTHONPATH"

# --- SCIP/SoPlex shared libraries ---
# Cray compute nodes may ignore RPATH embedded in the binary; set LD_LIBRARY_PATH
# explicitly so libscip.so.9.1 and libsoplex.so are found by the dynamic linker.
# This also allows PALS to dlopen the binary cleanly (needed for the sgicheckppversion check).
export LD_LIBRARY_PATH="${HOME}/scip_install/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

# --- Solver binaries ---
# SCIP usually comes from conda (on PATH). fscip/ParaSCIP must be compiled
# (README S4.2) -- once built, point FSCIP_BIN at it (or just have it on PATH).
export SCIP_BIN="${SCIP_BIN:-$(command -v scip || echo "$HOME/scip_install/bin/scip")}"
# parascip is the MPI-distributed binary (UG+MPI); fscip is shared-memory only (UG+pthreads).
# For multi-node runs, parascip is required. Fall back to fscip if parascip not found.
export FSCIP_BIN="${FSCIP_BIN:-$(command -v parascip || echo "$HOME/scip_install/bin/parascip")}"

echo "[env.sh] conda env=${CONDA_DEFAULT_ENV:-none} python=$(command -v python || echo none)"
echo "[env.sh] SCIP_BIN=$SCIP_BIN"
echo "[env.sh] FSCIP_BIN=$FSCIP_BIN"

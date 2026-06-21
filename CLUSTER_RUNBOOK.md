# Cluster Runbook — 5G NR Slice MILP

Step-by-step commands to run **on the HPE Cray Shasta cluster (PBS Pro)**, in order:
verify the setup → confirm the 2 nodes and their CPUs are visible → build the MILP →
solve it (1-node baseline + 2-node ParaSCIP) → evaluate.

Scheduler facts for this cluster (don't mix these up with Slurm):
- Submit a job: **`qsub`** · Monitor: **`qstat`** · Cancel: **`qdel`**
- MPI launcher inside jobs: **`mpiexec`** (HPE PALS / Cray MPICH) — **not** `srun`
- All commands below assume you are in the repo root (`cd ~/5g_allocation`) and have
  done the one-time environment setup in **Phase S** below.

Throughout, monitor any submitted job with:
```bash
qstat -u $USER                       # all your jobs
bash scripts/qstat_monitor.sh        # auto-refreshing view of all your jobs
bash scripts/qstat_monitor.sh <jobid>   # detailed view of one job
```
Job output lands in `logs/<jobname>.out` (and `.err`). `qsub` prints the `<jobid>`.

---

## Phase S — One-time environment setup (do this first, on the login node)

This is the conda-based setup that matches how this cluster is actually used (you use
your **own conda**, not the system `anaconda` module). Run it once.

```bash
cd ~/5g_allocation

# 1. Create the conda env. NOTE: install 'scip' + 'pyscipopt' from conda-forge for
#    the single-node SCIP CLI; the Python HiGHS binding 'highspy' comes via pip in
#    step 2 (the conda 'highs' package is the C++ lib, NOT the Python binding).
conda create -n penv -c conda-forge python=3.11 git scip pyscipopt -y
conda activate penv

# 2. Install the package + all Python deps in one shot. This pulls in:
#    highspy, numpy, networkx, matplotlib, pyyaml  (from pyproject.toml).
pip install -e .

# 3. Verify the Python side (no cluster job needed):
python -c "import highspy; print('highspy OK', highspy.__version__)"
python -c "import nr_slice_milp; from nr_slice_milp.model import build_model; print('package OK')"
which scip            # SCIP CLI from conda (used for the MPS smoke test)
```

> If you already created `penv` with just `highs`/`pyscipopt` earlier: just
> `conda activate penv && pip install -e .` — that adds `highspy` and the missing
> `networkx`/`matplotlib`/`pyyaml`. The plain conda `highs` package is not enough.

ParaSCIP (the MPI `fscip` binary for the 2-node run) is **not** on conda — you
compile it in **Phase 4.5**. The single-node baseline works without it.

If you named the env something other than `penv`, either pass `CONDA_ENV=<name>` to
every `qsub` (`qsub -v CONDA_ENV=<name> ...`) or edit `CONDA_ENV` at the top of
`pbs/env.sh` once.

---

## Phase 0 — Login-node quick checks (no job needed, instant)

These run on the login/UAN node and need no allocation.

```bash
# 0a. Is the scheduler up and which queues exist?
qstat -B            # server status (should say "Active")
qstat -Q            # queues — confirm 'workq' exists and is enabled/started

# 0b. Do the nodes exist and how many CPUs does PBS think each has?
pbsnodes -a | grep -E 'Mom|resources_available.ncpus|state' | head -40
#   Look for resources_available.ncpus = 128 per node and state = free.
#   A one-line-per-node summary:
pbsnodes -aSj | head -20

# 0c. Are the modules available?
module avail anaconda PrgEnv-gnu cray-mpich 2>&1 | grep -Ei 'anaconda|PrgEnv-gnu|cray-mpich'
```

If `pbsnodes -a` shows nodes with `ncpus=128` in `state=free`, the cluster has capacity.
The "usable 125" figure (3 reserved) is confirmed in Phase 2.

---

## Phase 1 — Dependency sanity check (1 small job)

Verifies the full toolchain **on a compute node** (where the modules and compiled
binaries actually live): Python deps, the `nr_slice_milp` package import, the
`scip`/`fscip` binaries, `mpiexec`, and that the rank/thread layout validates.

```bash
qsub pbs/check_dependencies.pbs
# watch it, then read:
cat logs/check_deps.out
```

**Pass criteria:** `OK highspy`, `OK nr_slice_milp importable`, `OK scip`,
`OK mpiexec`, and `OK ParascipLayout validates`. **`WARN fscip not found` is
expected here** — you compile ParaSCIP in Phase 4.5; re-run this check afterward
and it should flip to `OK fscip`. Any `FAIL` (not WARN) tells you what's missing.

---

## Phase 2 — Node & CPU visibility check (1 small job, the one you asked about)

Requests the **same 2-node shape** as the real run and confirms PBS actually
hands you 2 distinct nodes, each exposing its CPUs, and that `mpiexec` spreads
ranks across **both** nodes.

```bash
qsub pbs/check_nodes.pbs
# watch it, then read:
cat logs/check_nodes.out
```

**What to verify in `logs/check_nodes.out`:**
- `Distinct node count: 2` — you got two separate nodes.
- The "CPUs VISIBLE ON EACH NODE" section shows **two different hostnames**, each
  with `nproc=` around 125–128. This is the real, on-node CPU count — compare it
  against `usable_cpus_per_node: 125` in `configs/cluster_2node_default.yaml`.
- The "RANK DISTRIBUTION" section shows `4 <nodeA>` and `4 <nodeB>` — i.e. the 8
  MPI ranks split 4-and-4 across the two nodes (not all 8 on one node).
- "CONDA ENV / PACKAGE VISIBLE ON BOTH NODES" shows `highspy ... + nr_slice_milp
  import OK` from **both** hostnames — proves your conda env + `pip install -e .`
  are reachable cluster-wide (shared filesystem). An `IMPORT FAILED` here means the
  env is on node-local storage or wasn't activated.
- "FSCIP BINARY VISIBLE ON BOTH NODES" shows `fscip present` on both (or `fscip
  MISSING` until you've done Phase 4.5 — expected before the ParaSCIP build).
- Final line: `OK 2 nodes allocated and visible`.

**If the per-node CPU count is not 125:** edit `usable_cpus_per_node` in
`configs/cluster_2node_default.yaml` (and re-check that `ranks_per_node ×
threads_per_rank ≤ usable_cpus_per_node`). That file is the single source of
truth — the PBS `select` line, `mpiexec` flags, and `parascip.set` all derive
from it. After editing, also update the `#PBS -l select=...:mpiprocs=...:ompthreads=...`
line in `pbs/run_parascip_2node.pbs` to match.

---

## Phase 3 — Build/compile check (1 small job)

End-to-end smoke test on the tiny toy problem: byte-compiles the package, runs the
unit tests, builds+solves the toy MILP with HiGHS, exports an MPS and confirms the
variable names are present, validates it with SCIP, and (if ParaSCIP is built)
confirms `fscip` launches under `mpiexec`. The fscip step **skips cleanly** until
you've done Phase 4.5 — re-run this check after building ParaSCIP to exercise it.

```bash
qsub pbs/check_build.pbs
cat logs/check_build.out      # ends with "BUILD CHECK PASSED" on success
```

This is the last cheap gate before committing real walltime. If it ends with
`BUILD CHECK PASSED`, the whole pipeline works on this cluster.

> Tip: you can run Phases 1–3 back-to-back: `qsub pbs/check_dependencies.pbs; qsub pbs/check_nodes.pbs; qsub pbs/check_build.pbs` and watch them with `qstat -u $USER`.

---

## Phase 4 — Build the MILP (export the MPS file)

"Building the MILP" = assembling the ~129,600-variable / ~301,600-constraint model
and writing it to MPS (the format ParaSCIP reads). This also applies the variable-
naming fix so the solution can be parsed later.

```bash
conda activate penv
export PYTHONPATH=$PWD/src:$PYTHONPATH

# Target size (400 gNBs, 106 RBs). Takes a couple of minutes / a few GB RAM.
python -m nr_slice_milp.export_mps --config configs/problem_target.yaml --out 5gnr_slice.mps

# Sanity-check the export (should print readable names like x_0_0):
grep -m1 'x_0_0' 5gnr_slice.mps && echo "MPS has named variables — good."
```

You can also use a smaller config first to be quick:
`--config configs/problem_medium.yaml` (200 gNBs) or `configs/problem_toy.yaml` (10 gNBs).

> Note: `pbs/run_parascip_2node.pbs` (Phase 5) **regenerates this MPS itself**, so
> this manual step is mainly for inspection / the SCIP smoke test below. The
> single-node HiGHS baseline builds the model in-process and doesn't need the MPS.

Optional 60-second validation with single-process SCIP before the big run:
```bash
bash pbs/smoke_test.sh 5gnr_slice.mps
```

---

## Phase 4.5 — Build ParaSCIP (one-time, required for the 2-node run)

conda gives you single-node SCIP only; the MPI-parallel `fscip` must be compiled.

```bash
bash scripts/build_parascip.sh          # on uan1; or JOBS=32 in an interactive job
# the script prints the FSCIP_BIN line — add it to your shell:
export FSCIP_BIN=$HOME/scip_install/bin/fscip
$FSCIP_BIN --version

# re-run the dependency check; fscip should now say OK:
qsub pbs/check_dependencies.pbs && sleep 5 && cat logs/check_deps.out
```

If the build doesn't produce a binary, the script prints the UG-Makefile fallback —
paste any error and iterate. The single-node baseline (5a) does **not** need this;
only the 2-node ParaSCIP run (5b) does.

---

## Phase 5 — Solve

### 5a. Single-node HiGHS baseline (needed for the speedup comparison)

```bash
qsub pbs/run_highs_1node.pbs
# produces: logs/results_1node.json  (+ solver log in logs/highs_1node.out)
```

### 5b. Two-node ParaSCIP run (the main event)

```bash
qsub pbs/run_parascip_2node.pbs
# produces: logs/solution.sol, logs/parsed_results.json, logs/parascip_2node.log
```

This job: renders `parascip.set` from the cluster config, exports the MPS, launches
`mpiexec -n 8 --ppn 4 --depth 31 ... fscip`, records the wall time, and parses the
`.sol`. Default walltime is 4 hours and the gap target is 1% (both in
`configs/cluster_2node_default.yaml` → `parascip.set`).

Watch live progress:
```bash
bash scripts/qstat_monitor.sh <jobid>          # PBS-level status
tail -f logs/parascip_2node.log                # solver-level B&B progress
```

> **First real 2-node run:** open `logs/parascip_2node.log` and eyeball the solver
> progress table once. The log parser (`evaluate/parascip_log.py`) auto-detects
> the column layout, but this is the one thing that couldn't be verified without a
> real `fscip` log — confirm the `time / dualbound / primalbound` columns look sane.

### (Optional) Tune the rank/thread layout first

Before the full 4-hour run, you can sweep layouts on the medium problem with a short
time limit (see README §5.1 sweep table). Edit `ranks_per_node`/`threads_per_rank` in
a copy of the cluster config and submit with an override, e.g.:
```bash
CLUSTER_CFG=configs/cluster_2node_default.yaml PROBLEM_CFG=configs/problem_medium.yaml \
    qsub -v CLUSTER_CFG,PROBLEM_CFG pbs/run_parascip_2node.pbs
```

---

## Phase 6 — Evaluate

Once both `logs/results_1node.json` and `logs/parsed_results.json` exist:

```bash
conda activate penv
export PYTHONPATH=$PWD/src:$PYTHONPATH

python -m nr_slice_milp.evaluate.cli \
  --config configs/problem_target.yaml \
  --results 1=logs/results_1node.json \
  --results 2=logs/parsed_results.json \
  --logs 2=logs/parascip_2node.log \
  --out-dir plots/
```

This prints a solution summary (objective, per-slice admission rates, RB utilization,
MIP gap, solve time) and a **speedup / parallel-efficiency** number for 2 nodes vs 1,
and writes PNGs to `plots/`:
- `admission_<label>.png` — per-slice admission rate (solution quality)
- `rb_util_<label>.png` — average RB utilization
- `gap_convergence.png` — MIP gap vs time
- `ub_lb_convergence.png` — upper/lower bound vs time
- `speedup_efficiency.png` — speedup and efficiency vs the 1-node baseline

**How to judge "is it good?":** admission rates as high as possible (URLLC weighted
highest), RB utilization above ~70%, MIP gap at or below 1%, and parallel efficiency
above ~75% (speedup > 1.5× on 2 nodes).

---

## Quick reference — the whole sequence

```bash
# --- one-time setup ---
conda create -n penv -c conda-forge python=3.11 git scip pyscipopt -y
conda activate penv
pip install -e .                                    # highspy + numpy + networkx + matplotlib + pyyaml
bash scripts/build_parascip.sh                      # compile ParaSCIP (fscip) for the 2-node run
export FSCIP_BIN=$HOME/scip_install/bin/fscip       # (the build script prints this)

# Phase 0: login-node checks
qstat -B; qstat -Q; pbsnodes -aSj | head

# Phases 1-3: cheap preflight jobs
qsub pbs/check_dependencies.pbs
qsub pbs/check_nodes.pbs
qsub pbs/check_build.pbs
qstat -u $USER                      # wait for all three, then read logs/check_*.out

# Phase 4: build the MILP
python -m nr_slice_milp.export_mps --config configs/problem_target.yaml --out 5gnr_slice.mps

# Phase 5: solve
qsub pbs/run_highs_1node.pbs
qsub pbs/run_parascip_2node.pbs

# Phase 6: evaluate
python -m nr_slice_milp.evaluate.cli --config configs/problem_target.yaml \
  --results 1=logs/results_1node.json --results 2=logs/parsed_results.json \
  --logs 2=logs/parascip_2node.log --out-dir plots/
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `qsub: ... Job rejected` | Bad resource request for this site | Check `pbsnodes -a` ncpus; adjust `select` |
| `check_nodes` shows 1 node | Site packed both chunks on one node | Add `:place=scatter` to the `select`/`-l place=scatter` |
| per-node `nproc` ≠ 125 | Reserved-CPU count differs here | Edit `usable_cpus_per_node` in the cluster config + the `select` line |
| `srun: command not found` | Used a Slurm launcher | This is PBS Pro — use `mpiexec` (already in the scripts) |
| `fscip: command not found` | PATH/compile issue | `export PATH=$HOME/scip_install/bin:$PATH`; re-run README §4.2 |
| `.sol` parser finds 0 vars | MPS exported without names | Confirm Phase 3 `check_build` shows "variable names present in MPS" |
| Speedup step skipped | A result lacks solve time | Ensure both jobs finished; the ParaSCIP job records it via `--solve-time` |
| Gap never reaches 1% | Hard instance / weak relaxation | Increase walltime, or sweep the rank/thread layout (README §5.1) |

See README.md §8 (verification) and §10 (common issues) for more.

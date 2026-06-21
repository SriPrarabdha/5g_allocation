# 5G NR Slice Manager — MILP on CDOT HPC Cluster
**Target machine:** HPE Cray Shasta, 160 nodes × 128 CPUs/node (125 usable/node, 3 reserved for OS/overhead), PBS Pro scheduler
**Solver stack:** HiGHS (intra-node) + ParaSCIP (inter-node via MPI)
**Goal:** Solve a large-scale network slice admission + RB allocation MILP across 2 nodes

This document describes the **architecture and reasoning** behind the solver. The actual implementation lives in the `src/nr_slice_milp/` package (see §9) — this README is no longer the source of code, it's documentation of why the package is structured the way it is.

> **Running it on the cluster?** Follow [`CLUSTER_RUNBOOK.md`](CLUSTER_RUNBOOK.md) — step-by-step commands to sanity-check the setup, confirm the 2 nodes and their CPUs are visible, then build, solve, and evaluate.

---

## 1. Problem Background

### What is 5G Network Slicing?

A 5G network is divided into logical **network slices**, each tuned for a different service type:

| Slice | Name | Key SLA requirement |
|-------|------|-------------------|
| eMBB | Enhanced Mobile Broadband | High throughput (≥100 Mbps) |
| URLLC | Ultra-Reliable Low Latency | Low latency (≤1 ms), high reliability |
| mMTC | Massive Machine-Type Comms | High connection density, low data rate |

Each **gNB (base station)** has a fixed pool of **Resource Blocks (RBs)** — the fundamental unit of radio spectrum in 5G NR. Each RB is a 12-subcarrier × 1-slot chunk of time-frequency resource.

The **slice manager** decides:
1. Which slices to **admit** at each gNB (binary decision)
2. How many RBs to **assign** to each admitted slice (integer/continuous decision)
3. How to handle **interference** between adjacent gNBs sharing the same RBs

This is inherently a **Mixed Integer Linear Program (MILP)** because admission is binary but RB allocation is continuous/integer.

---

## 2. Mathematical Formulation

### 2.1 Sets and Indices

| Symbol | Description |
|--------|-------------|
| $\mathcal{B}$ | Set of gNBs (base stations), indexed by $b$, $|\mathcal{B}| = N_B$ |
| $\mathcal{S} = \{\text{eMBB}, \text{URLLC}, \text{mMTC}\}$ | Set of slice types, indexed by $s$ |
| $\mathcal{R}$ | Set of resource blocks per gNB, indexed by $r$, $|\mathcal{R}| = N_R$ |
| $\mathcal{E}$ | Set of edges (adjacent gNB pairs) in the interference graph |

### 2.2 Parameters

| Symbol | Description | Typical value | Config location |
|--------|-------------|---------------|------------------|
| $N_R$ | Total RBs available at each gNB | 106 (5G NR 20MHz) | `configs/*.yaml: n_r` |
| $W$ | Bandwidth per RB | 180 kHz | `configs/*.yaml: rb_bandwidth_mhz` |
| $\text{eff}_{b,s}$ | Spectral efficiency for slice $s$ at gNB $b$ (bits/s/Hz) | 1–6 | `network.build_eff` |
| $T_s^{\min}$ | Minimum throughput SLA for slice $s$ | eMBB: 100Mbps, URLLC: 10Mbps, mMTC: 1Mbps | `configs/*.yaml: slices[].t_min_mbps` |
| $\text{RB}_s^{\min}$ | Minimum RBs required to instantiate slice $s$ | eMBB: 20, URLLC: 10, mMTC: 5 | `configs/*.yaml: slices[].rb_min` |
| $\text{RB}_s^{\max}$ | Maximum RBs slice $s$ can use | eMBB: 80, URLLC: 40, mMTC: 30 | `configs/*.yaml: slices[].rb_max` |
| $w_s$ | Revenue weight for admitting slice $s$ | eMBB: 3, URLLC: 5, mMTC: 1 | `configs/*.yaml: slices[].weight` |
| $\alpha_{b,b'}$ | Interference factor between adjacent gNBs $b$ and $b'$ | 0.3–0.8 | `network.build_alpha` |
| $\text{cap}_b$ | Total RB capacity of gNB $b$ (= $N_R$) | 106 | `configs/*.yaml: n_r` |

### 2.3 Decision Variables

| Variable | Type | Description |
|----------|------|-------------|
| $x_{b,s} \in \{0,1\}$ | Binary | 1 if slice $s$ is admitted at gNB $b$ |
| $a_{b,s,r} \in \{0,1\}$ | Binary | 1 if RB $r$ is assigned to slice $s$ at gNB $b$ |
| $t_{b,s} \geq 0$ | Continuous | Throughput (Mbps) allocated to slice $s$ at gNB $b$ |

### 2.4 Objective Function

Maximize total weighted slice admissions:

$$\max \quad \sum_{b \in \mathcal{B}} \sum_{s \in \mathcal{S}} w_s \cdot x_{b,s}$$

### 2.5 Constraints → Implementation Map

Each constraint family is implemented as its own function in `src/nr_slice_milp/constraints.py`, taking the HiGHS model handle and `ProblemConfig`, returning the row count it added.

| # | Name | Formula | Function |
|---|------|---------|----------|
| C1 | RB Exclusivity | $\sum_{s} a_{b,s,r} \leq 1 \ \forall b,r$ | `add_c1_rb_exclusivity` |
| C2 | Total RB Capacity | $\sum_{s,r} a_{b,s,r} \leq \text{cap}_b \ \forall b$ | `add_c2_capacity` |
| C3 | Throughput-RB Linkage | $t_{b,s} \leq \sum_r a_{b,s,r} \cdot W \cdot \text{eff}_{b,s} \ \forall b,s$ | `add_c3_throughput_link` |
| C4 | SLA Throughput Guarantee | $t_{b,s} \geq T_s^{\min} \cdot x_{b,s} \ \forall b,s$ | `add_c4_sla` |
| C5 | Min RB Allocation if Admitted | $\sum_r a_{b,s,r} \geq \text{RB}_s^{\min} \cdot x_{b,s} \ \forall b,s$ | `add_c5_min_rb` |
| C6 | Max RB Allocation | $\sum_r a_{b,s,r} \leq \text{RB}_s^{\max} \cdot x_{b,s} \ \forall b,s$ | `add_c6_max_rb` |
| C7 | RB Allocation only if Admitted | $a_{b,s,r} \leq x_{b,s} \ \forall b,s,r$ | `add_c7_rb_admission_link` |
| C8 | Inter-Cell Interference | $\sum_{s} a_{b,s,r} + \sum_{s} a_{b',s,r} \leq 1 + \mathbb{1}[\alpha_{b,b'} < \alpha^{\text{thresh}}] \ \forall (b,b') \in \mathcal{E}, r$ | `add_c8_interference` |
| C9 | URLLC Dedicated RBs | $a_{b,\text{URLLC},r} + a_{b,\text{eMBB},r} \leq 1 \ \forall b,r$ | `add_c9_urllc_isolation` |

C9 simplifies the real-world "contiguous, isolated RBs" requirement to "URLLC RBs cannot be shared with eMBB on the same gNB" — a reasonable proxy, unchanged from the original prototype.

### 2.6 Problem Size Analysis

For the **toy problem targeting 2 nodes** (`configs/problem_target.yaml`):

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| $N_B$ (gNBs) | 400 | Dense urban scenario |
| $N_R$ (RBs) | 106 | Standard 20 MHz 5G NR |
| $|\mathcal{S}|$ (slices) | 3 | eMBB, URLLC, mMTC |
| $|\mathcal{E}|$ (interference edges) | ~800 | avg degree 4, random geometric graph |

**Variable count:** ~129,600 total (127,200 binary `a_{b,s,r}`, 1,200 binary `x_{b,s}`, 1,200 continuous `t_{b,s}`).

**Constraint count:** ~301,600 total (C7 and C8 are the two largest blocks, 127,200 and 84,800 rows respectively).

This is large enough to be genuinely hard for a single node, making 2-node ParaSCIP worthwhile.

### 2.7 Known Simplifications and Their Status

- **Interference topology is a random geometric graph proxy, not a literal hex grid.** The original prototype named its graph-builder `hex_grid_graph` despite calling `nx.random_geometric_graph(n, radius=0.15, seed=42)` — degree-4ish random geometric graphs and degree-6 hex grids are both reasonable adjacency proxies, and the MILP's difficulty doesn't hinge on which one is used. Renamed to `network.build_interference_graph` for honesty rather than reimplementing an actual hex grid.
- **C8's α-threshold logic is now implemented, not just documented.** The original code applied the conservative `≤1` co-channel bound to *every* interference edge unconditionally, ignoring the documented `𝟙[α_{b,b'} < α^{\text{thresh}}]` relaxation — silently solving a harder, more conservative problem than specified, which directly hurts solution quality (admission rate / RB utilization). `network.build_alpha` now derives $\alpha_{b,b'}$ deterministically from the existing graph node positions (`nx.random_geometric_graph` stores `pos` on each node by construction): `alpha = clip(1 - dist/radius, 0, 1)` — closer gNBs interfere more, no new randomness introduced. It's a physical proxy (closer cells co-channel-interfere more), not a measured/simulated RF propagation model. `cfg.use_alpha_threshold=False` reproduces the original conservative behavior, intended for an A/B comparison of solution quality.
- **ParaSCIP's stdout B&B table format has not been verified against a real run.** `evaluate/parascip_log.py` parses the header row dynamically to locate `time`/`dualbound`/`primalbound` column positions rather than assuming a fixed layout, with a `header_found` flag and warning on fallback — but this still needs to be checked against a real `fscip` log on first cluster access (see §8 Verification).

---

## 3. Package Layout

```
5g-allocation/
├── README.md / CLAUDE.md      # docs (this file + Claude Code guidance)
├── pyproject.toml             # deps: highspy, numpy, networkx, matplotlib, pyyaml
├── src/nr_slice_milp/
│   ├── config.py               # ProblemConfig / SliceParams dataclasses
│   ├── cluster_config.py       # ParascipLayout: MPI rank/thread layout, validate()
│   ├── network.py              # build_interference_graph, build_alpha, build_eff
│   ├── indexing.py             # idx_x/idx_a/idx_t/n_vars + var_name_x/a/t
│   ├── constraints.py          # add_c1_... through add_c9_...
│   ├── model.py                 # build_model(cfg) -> (h, meta)
│   ├── export_mps.py           # assign_variable_names (passColName fix) + write_mps
│   ├── solve_highs.py          # HiGHS solve driver, writes results.json
│   ├── parse_solution.py       # SCIP .sol parser (x_/a_/t_ vars)
│   └── evaluate/
│       ├── parascip_log.py     # header-driven ParaSCIP log parser
│       ├── plots.py            # admission/RB-util/gap/UB-LB/speedup plots
│       ├── speedup.py          # compute_speedup
│       └── cli.py              # entrypoint wiring everything together
├── configs/
│   ├── problem_toy.yaml        # N_B=10, N_R=20 — local sanity check
│   ├── problem_medium.yaml     # N_B=200 — layout sweeps
│   ├── problem_target.yaml     # N_B=400, N_R=106, N_S=3 — the real run
│   └── cluster_2node_default.yaml
├── pbs/
│   ├── run_highs_1node.pbs
│   ├── run_parascip_2node.pbs
│   ├── gen_parascip_set.py     # renders parascip.set from cluster_config
│   ├── check_dependencies.pbs  # compute-node check: modules/deps/binaries/mpiexec
│   ├── check_nodes.pbs         # 2-node check: both nodes + CPUs visible, rank spread
│   ├── check_build.pbs         # compute-node check: compile+pytest+solve+fscip launch
│   └── smoke_test.sh           # 60s `scip -f ... optimize` check
├── scripts/
│   ├── sanity_check.py         # tiny end-to-end run against problem_toy.yaml
│   └── qstat_monitor.sh        # qstat-based PBS job monitor
├── tests/                      # pytest suite, see §8
└── logs/                       # PBS + parascip logs land here
```

---

## 4. Environment Setup on the Cluster

### 4.1 One-Time Setup (run from uan1)

Create a conda env (named `penv` here — the PBS scripts default to this; override
with `CONDA_ENV=...`). Note the Python package you need is **`highspy`** (the binding),
not `highs` (the C++ lib/CLI):

```bash
conda create -n penv -c conda-forge python=3.11 git scip pyscipopt -y
conda activate penv

# Installs nr_slice_milp + its deps: highspy, numpy, networkx, matplotlib, pyyaml.
pip install -e .

python -c "import highspy; print('HiGHS OK:', highspy.__version__)"
which scip   # SCIP CLI comes from conda; used for the MPS smoke test
```

`pip install -e .` is what pulls in `highspy` and the rest — installing the conda
`highs` package alone is **not** enough (that's the C++ library, not the Python
binding). The PBS scripts activate this env via `pbs/env.sh` (edit `CONDA_ENV`
there if you named it differently) and locate `scip`/`fscip` via `$SCIP_BIN`/`$FSCIP_BIN`.

### 4.2 Compile ParaSCIP from Source (required only for the 2-node run)

**The conda `scip`/`pyscipopt` packages give you single-node SCIP only — they do
NOT include the MPI-parallel ParaSCIP (`fscip`) binary.** Multi-node distributed
branch-and-bound requires building the UG framework from source against Cray MPICH.

**Easy path — use the build script** (downloads SCIPOptSuite, builds SoPlex+SCIP+UG
with the Cray MPI compilers, auto-locates the parallel binary, installs it as
`$HOME/scip_install/bin/fscip`):

```bash
bash scripts/build_parascip.sh           # on uan1; or JOBS=32 inside an interactive job
export FSCIP_BIN=$HOME/scip_install/bin/fscip   # the script prints this line
$FSCIP_BIN --version
```

<details><summary>Manual build (what the script does)</summary>

```bash
module load PrgEnv-gnu/8.6.0 cray-mpich/8.1.32   # cc/CC wrap MPI -> UG gets MPI

cd $HOME
wget https://scipopt.org/download/release/scipoptsuite-9.1.0.tgz
tar xzf scipoptsuite-9.1.0.tgz
cd scipoptsuite-9.1.0 && mkdir build && cd build

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=cc \
  -DCMAKE_CXX_COMPILER=CC \
  -DUG=ON \
  -DZIMPL=OFF -DIPOPT=OFF -DPAPILO=OFF -DREADLINE=OFF \
  -DCMAKE_INSTALL_PREFIX=$HOME/scip_install

make -j32 && make install

# Locate whatever parallel binary UG produced (fscip or parascip):
find . $HOME/scip_install -type f \( -name 'fscip*' -o -name 'parascip*' \)
```

If `-DUG=ON` doesn't produce a parallel binary for your SCIPOptSuite version, fall
back to the UG Makefile build (`cd ug && make COMM=mpi ...`) — `scripts/build_parascip.sh`
prints the exact fallback commands. The Cray `CC` wrapper supplies MPI, so no separate
`-DMPI=ON` is needed.

</details>

Then point the PBS scripts at it by exporting `FSCIP_BIN=$HOME/scip_install/bin/fscip`
(or add `$HOME/scip_install/bin` to `PATH`); `pbs/env.sh` picks it up automatically.
The parallel binary may be named `fscip` or `parascip` depending on build flags —
`build_parascip.sh` installs whichever it finds as `fscip`.

### 4.3 Export Problem to MPS Format

```bash
conda activate penv
python -m nr_slice_milp.export_mps --config configs/problem_target.yaml --out 5gnr_slice.mps
```

This calls `export_mps.assign_variable_names` (the `passColName` fix, §6) before `writeModel`, so the exported MPS carries readable `x_/a_/t_` names that `parse_solution.py` can later regex-match in SCIP's `.sol` output.

---

## 5. Running on 2 Nodes

### 5.1 CPU Layout: 2 Nodes × 125 Usable CPUs (250 total)

Only 125 of each node's 128 CPUs are usable (3 reserved for OS/overhead). **Default: 4 MPI ranks/node × 31 threads/rank = 8 total ranks, 248/250 CPUs used**, configured via `configs/cluster_2node_default.yaml` (`ParascipLayout` in `cluster_config.py`):

```yaml
n_nodes: 2
usable_cpus_per_node: 125
ranks_per_node: 4
threads_per_rank: 31
reserve_cpus_per_node: 1
```

**Why this layout:**
- ParaSCIP/FiberSCIP reserve **rank 0 as a non-solving Load Coordinator (LC)**. The original prototype's 4 total ranks ⇒ only 3 actual B&B solver ranks — too thin to get value out of the second node. 8 ranks ⇒ 7 solver ranks, much better tree parallelism across both nodes.
- 31 threads/rank keeps each rank's local LP re-solve fast (every B&B node re-solves an LP relaxation, and the `a_{b,s,r}` block dominates it) — too many thin ranks (16+, <8 threads each) would starve LP-solve and add LC coordination overhead without proportional gains.
- `ParascipLayout.validate()` catches CPU-overshoot bugs before submission — the original script's `4 ranks × 64 threads = 256 CPUs` exceeded the 250 actually available.

This is a **starting default**, not a claimed optimum — actual tuning requires the real cluster. Sweep table to try (all ≤125 cpus/node), on `configs/problem_medium.yaml` with a short time limit before committing to the full target-scale run:

| Layout name | ranks/node | threads/rank | total ranks | solving ranks | total CPUs used |
|---|---|---|---|---|---|
| thin-rank (original, buggy) | 2 | 64 | 4 | 3 | 256 (exceeds 250 — invalid) |
| wide-thread | 2 | 62 | 4 | 3 | 248 |
| **balanced (default)** | 4 | 31 | 8 | 7 | 248 |
| many-rank | 8 | 15 | 16 | 15 | 240 |
| max-rank | 16 | 7 | 32 | 31 | 224 |

### 5.2 PBS Job Script — HiGHS Single Node (baseline)

See `pbs/run_highs_1node.pbs`. Key points vs. the original: `ncpus=125` (not 128), `HIGHS_THREADS=125`, invokes `python -m nr_slice_milp.solve_highs --config configs/problem_target.yaml`.

Submit: `qsub pbs/run_highs_1node.pbs`

### 5.3 PBS Job Script — ParaSCIP 2 Nodes

See `pbs/run_parascip_2node.pbs`. This cluster is **PBS Pro + Cray MPICH (HPE PALS)**, so ParaSCIP is launched with **`mpiexec -n <total_ranks> --ppn <ranks_per_node> --depth <threads_per_rank>`** — *not* `srun` (that's Slurm). The script no longer heredocs `parascip.set` inline — `pbs/gen_parascip_set.py` renders it from `configs/cluster_2node_default.yaml`, and the same config drives the `mpiexec` rank/thread arguments and the `#PBS -l select=...:mpiprocs=...:ompthreads=...` line, so the settings file and the actual MPI launch can't drift out of sync. The script also records the ParaSCIP wall time and passes it to `parse_solution --solve-time` so the evaluation CLI can compute speedup.

Submit: `qsub pbs/run_parascip_2node.pbs`

### 5.4 Solution Parser

`src/nr_slice_milp/parse_solution.py` — extended beyond the original (which only parsed `x_`/`t_` lines) to also parse `a_` variables, enabling RB-utilization reporting from ParaSCIP solutions, not just the HiGHS path.

```bash
python -m nr_slice_milp.parse_solution logs/solution.sol --config configs/problem_target.yaml --out logs/parsed_results.json
```

---

## 6. Bug Fixes Applied During Modularization

1. **HiGHS variable naming.** `h.addVars(...)` was called with no names, so MPS export got generic column names (`C0`, `C1`, ...), and `parse_solution.py`'s `x_<b>_<si>` regex never matched anything. Fixed via `export_mps.assign_variable_names`, calling `h.passColName(idx, name)` for every variable before `writeModel`, using the same naming functions (`indexing.var_name_x/a/t`) that `parse_solution.py`'s regexes are built against.
2. **C8 α-threshold** — see §2.7.
3. **CPU layout** — see §5.1.
4. **`parse_parascip_log` robustness** — header-driven column detection instead of a fixed positional regex; see §2.7 and §8.
5. **Hardcoded `N_B=400`/`N_S=3`** in the original `evaluate.py` — removed; `evaluate/cli.py` derives everything from `ProblemConfig` loaded via `--config`.
6. **`compute_speedup` was defined but never called** in the original `evaluate.py`'s `__main__` — `evaluate/cli.py` now always computes and plots speedup/efficiency when 2+ labeled results are passed.

---

## 7. Evaluation Framework

### 7.1 Metrics

| Metric | How to compute | Target |
|--------|---------------|--------|
| **Solve time** | Wall clock, PBS logs | < 4 hours |
| **Optimality gap** | `(UB - LB) / UB × 100` | < 1% |
| **Slice admission rate** | `admitted[s] / N_B` per slice | Maximize |
| **RB utilization** | `Σ assigned RBs / (N_B × N_R)` | > 70% |
| **SLA violation rate** | Slices admitted but `t < T_min` | 0 (by constraint) |
| **Speedup** | `T_1node / T_2node` | > 1.5× |
| **Parallel efficiency** | `Speedup / num_nodes` | > 75% |
| **B&B nodes explored** | From ParaSCIP log | Track scaling |

### 7.2 Running the Evaluation CLI

```bash
python -m nr_slice_milp.evaluate.cli \
  --config configs/problem_target.yaml \
  --results 1=logs/results_1node.json --results 2=logs/parsed_results.json \
  --logs 1=logs/parascip_1node.log --logs 2=logs/parascip_2node.log \
  --out-dir plots/
```

Produces: per-run admission-quality and RB-utilization plots, gap and UB/LB convergence plots from the logs, and (when 2+ result sets are given) a speedup/efficiency plot.

### 7.3 Quick Sanity Checks Before Full Run

```bash
# 1. Local, no cluster needed — tiny model build+solve sanity check
python scripts/sanity_check.py

# 2. Validate MPS file (after export)
bash pbs/smoke_test.sh 5gnr_slice.mps

# 3. ParascipLayout fits within usable CPUs
python -m nr_slice_milp.cluster_config --field total_cpus_used --cluster-config configs/cluster_2node_default.yaml
```

### 7.4 Cluster Preflight (run on a compute node via qsub, before the 4-hour job)

```bash
qsub pbs/check_dependencies.pbs   # modules, python deps, scip/fscip binaries, mpiexec
qsub pbs/check_build.pbs          # byte-compile + pytest + toy solve + MPS names + fscip launch

bash scripts/qstat_monitor.sh             # watch all your jobs (qstat-based)
bash scripts/qstat_monitor.sh <jobid>     # watch one job in detail
# results land in logs/check_deps.out and logs/check_build.out
```

These two jobs verify the whole toolchain on an actual compute node (where the modules and compiled binaries live) — catching missing dependencies or a broken ParaSCIP compile cheaply, before committing the full walltime budget.

---

## 8. Verification Plan

**Runnable now, locally (no cluster needed):** `pytest tests/` — index bijectivity, per-constraint row counts on a tiny config (via a lightweight fake HiGHS handle, no `highspy` dependency for these tests), interference-graph determinism, alpha derivation, `.sol` round-trip parsing, header-driven log parsing against fixture logs (including a column-reordered fixture), `compute_speedup` math. Plus `scripts/sanity_check.py` if `highspy` is installed.

**Only verifiable on the actual PBS cluster:**
- Real `fscip` stdout table format — diff the first real run's log against the test fixtures before trusting any plot from it.
- Whether 8 ranks × 31 threads is actually the best layout — run the §5.1 sweep table on `problem_medium.yaml` first.
- Real speedup/parallel-efficiency numbers.
- Whether "125 usable CPUs/node" is exactly right for this cluster — verify with `pbsnodes -a`/`qstat -Qf` on first access.
- Solution-quality effect of the α-threshold fix (`use_alpha_threshold=True` vs `False`) — cheap pre-check at `problem_medium.yaml` scale before a full target-scale A/B.

Suggested execution order: smoke test → short ParaSCIP run on `problem_medium.yaml` (validates plumbing + captures a real log) → layout sweep → full 1-node HiGHS baseline + 2-node ParaSCIP run on `problem_target.yaml` → optional α-threshold A/B → `evaluate.cli` over all collected results.

---

## 9. Scaling Experiments to Try

| Experiment | $N_B$ | $N_R$ | Nodes | Expected time |
|-----------|--------|--------|-------|--------------|
| Baseline  | 50     | 50     | 1     | ~2 min |
| Medium    | 200    | 106    | 1     | ~30 min |
| **Target**| **400**| **106**| **2** | **~2–4 hr** |
| Large     | 800    | 106    | 4     | ~4–8 hr |
| Extreme   | 2000   | 106    | 16    | 1 day+ |

The sdflex280 node (1024 CPUs, 32TB RAM) can hold the entire LP relaxation in memory for the extreme case — worth trying for LP-only bounds.

---

## 10. Common Issues and Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `fscip: command not found` | PATH not set | `export PATH=$HOME/scip_install/bin:$PATH` |
| MPI rank mismatch | `mpiexec -n` / `--ppn` inconsistent with PBS `select` | Keep `mpiexec -n` = `select × mpiprocs` and `--ppn` = `mpiprocs`; all driven by `cluster_config.py` / the `select` line |
| `srun: command not found` | Used a Slurm launcher | This is PBS Pro — launch with `mpiexec` (HPE PALS), not `srun` |
| Out of memory | Model too large for RAM | Reduce $N_B$ or use sdflex280 |
| Infeasible solution | Conflicting constraints | Check C4 vs C3: ensure $T_{\min}$ achievable with $\text{RB}_{\max}$ and eff |
| Gap never closes | Weak LP relaxation | Add valid inequalities or tighten big-M in C7 |
| ParaSCIP stalls | Load imbalance across ranks | Tune `ranks_per_node`/`threads_per_rank` in `cluster_config.yaml` |
| `.sol` parser finds nothing | Variable names not assigned before MPS export | Confirm `export_mps.assign_variable_names` ran before `writeModel` |

---

## 11. Planned Extensions

1. **Column Generation** (the `cg` branch hint): generate RB assignment columns on-the-fly instead of the full explicit `a_{b,s,r}` model.
2. **Benders Decomposition**: master handles admission ($x_{b,s}$), per-gNB subproblems handle RB allocation ($a_{b,s,r}$) — parallelizes naturally across 160 nodes.
3. **Warm Starting**: feed a HiGHS LP relaxation solution into ParaSCIP to tighten the B&B tree early.
4. **Publication angle**: empirical scaling curves on a real Cray Shasta system (not a cloud cluster) for a telecom MILP.

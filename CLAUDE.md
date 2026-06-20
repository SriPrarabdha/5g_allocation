# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a research project solving a large-scale **5G NR network slice admission + resource block (RB) allocation MILP** on an HPE Cray Shasta HPC cluster (160 nodes × 128 CPUs/node, **125 usable/node** — 3 reserved for OS/overhead — PBS Pro scheduler). The solver stack uses HiGHS for single-node LP/MILP and ParaSCIP (MPI-parallel SCIP) for multi-node distributed branch-and-bound.

Code is a real installable package under `src/nr_slice_milp/` (not embedded in README.md):
- `src/nr_slice_milp/model.py` — model assembly (`build_model`)
- `src/nr_slice_milp/constraints.py` — C1-C9 constraint builders
- `src/nr_slice_milp/network.py` — interference graph, alpha, spectral efficiency
- `src/nr_slice_milp/indexing.py` — variable indexing and naming
- `src/nr_slice_milp/export_mps.py` — MPS export + HiGHS variable-naming fix
- `src/nr_slice_milp/solve_highs.py` — HiGHS driver
- `src/nr_slice_milp/parse_solution.py` — SCIP `.sol` parser
- `src/nr_slice_milp/evaluate/` — `parascip_log.py`, `plots.py`, `speedup.py`, `cli.py`

See README.md §3 for the full layout and §2.7 for known simplifications (alpha-threshold derivation, interference-graph naming).

## Running the Code

All Python commands require the conda environment to be activated first:
```bash
module load anaconda/3.13.5
conda activate milp_env
pip install -e .   # once, to install nr_slice_milp from pyproject.toml
```

**Build and solve (HiGHS, single node):**
```bash
python -m nr_slice_milp.solve_highs --config configs/problem_target.yaml --results-out results.json
```

**Generate MPS file only (for ParaSCIP):**
```bash
python -m nr_slice_milp.export_mps --config configs/problem_target.yaml --out 5gnr_slice.mps
```

**Quick sanity check with tiny problem (no cluster needed):**
```bash
python scripts/sanity_check.py   # uses configs/problem_toy.yaml (N_B=10, N_R=20)
```

**Validate MPS with SCIP (1-minute limit):**
```bash
bash pbs/smoke_test.sh 5gnr_slice.mps
```

**Submit PBS jobs:**
```bash
qsub pbs/run_highs_1node.pbs      # 1 node, 125 usable CPUs, HiGHS
qsub pbs/run_parascip_2node.pbs   # 2 nodes, 125 usable CPUs/node, ParaSCIP via mpiexec
```

**Parse ParaSCIP solution and evaluate:**
```bash
python -m nr_slice_milp.parse_solution logs/solution.sol --config configs/problem_target.yaml --out logs/parsed_results.json
python -m nr_slice_milp.evaluate.cli --config configs/problem_target.yaml \
  --results 1=results.json --results 2=logs/parsed_results.json \
  --logs 1=logs/parascip_1node.log --logs 2=logs/parascip_2node.log
```

## Architecture

### MILP Formulation
The problem has ~129,600 variables (127,200 binary) and ~301,600 constraints for the target size (400 gNBs, 106 RBs, 3 slices):

- **x_{b,s}** (binary): admission decision for slice s at gNB b
- **a_{b,s,r}** (binary): RB r assigned to slice s at gNB b — the dominant variable count
- **t_{b,s}** (continuous): throughput allocated to slice s at gNB b

Variable index layout (`src/nr_slice_milp/indexing.py`):
```
[x_{b,s}: N_B×N_S] [a_{b,s,r}: N_B×N_S×N_R] [t_{b,s}: N_B×N_S]
```
`idx_x`, `idx_a`, `idx_t` compute flat offsets; `var_name_x/a/t` generate the matching `x_<b>_<si>` / `a_<b>_<si>_<r>` / `t_<b>_<si>` names used both for MPS column naming (`export_mps.assign_variable_names`) and `.sol` parsing (`parse_solution.py`) — single source of truth, no naming drift between the two.

### Constraint structure
Nine constraint families (C1–C9), one function per family in `src/nr_slice_milp/constraints.py`: RB exclusivity, capacity, throughput–RB linkage, SLA, min/max RB bounds, RB-admission linking, inter-cell interference, URLLC isolation from eMBB.

C7 (`a_{b,s,r} <= x_{b,s}`) and C8 (interference) are the two largest blocks (127,200 and `|edges| × N_R` ≈ 84,800 rows respectively). The interference graph is built with `nx.random_geometric_graph` (seed=42) in `network.build_interference_graph`. C8's `alpha_{b,b'}` threshold logic is implemented in `network.build_alpha` (distance-based, derived from the graph's own node positions) — controlled by `ProblemConfig.use_alpha_threshold`.

### Solver path
- **HiGHS** (`highspy`): builds and solves the model in-process; used for single-node baseline and LP relaxation warm-starts.
- **ParaSCIP** (`fscip`): reads MPS export, runs distributed B&B over MPI ranks. Rank/thread layout is configured via `configs/cluster_2node_default.yaml` / `cluster_config.ParascipLayout` — default is 4 ranks/node × 31 threads/rank (8 total ranks, 7 solving after the rank-0 Load Coordinator, 248/250 usable CPUs). See README §5.1 for the reasoning and sweep table.

### Objective
Maximize `Σ w_s · x_{b,s}` (weighted admissions): eMBB=3, URLLC=5, mMTC=1. Passed to HiGHS as negated costs for minimization.

## Cluster Environment

- **Scheduler:** PBS Pro — jobs submitted with `qsub`, logs in `logs/`
- **MPI:** Cray MPICH 8.1.32 launched via `mpiexec` (HPE PALS) inside PBS scripts — **not** `srun` (this is PBS Pro, not Slurm). Jobs submitted with `qsub`, monitored with `qstat` (`scripts/qstat_monitor.sh`)
- **Modules needed:** `PrgEnv-gnu/8.6.0`, `cray-mpich/8.1.32`, `anaconda/3.13.5`
- **ParaSCIP binary:** `$HOME/scip_install/bin/fscip` (compiled from SCIPOptSuite 9.1.0)
- **Thread control:** `export HIGHS_THREADS=125` for single-node HiGHS (125 usable CPUs/node, not 128)

## Key Parameters

| Parameter | Default | Location |
|-----------|---------|----------|
| N_B (gNBs) | 400 | `configs/problem_target.yaml: n_b` |
| N_R (RBs) | 106 | `configs/problem_target.yaml: n_r` |
| MIP gap target | 1% | `configs/cluster_2node_default.yaml: gap` |
| Walltime | 4 hours | PBS `#PBS -l walltime` |
| Interference threshold α | 0.6 | `configs/problem_target.yaml: alpha_thresh` |
| Usable CPUs/node | 125 | `configs/cluster_2node_default.yaml: usable_cpus_per_node` |
| MPI ranks/node | 4 | `configs/cluster_2node_default.yaml: ranks_per_node` |
| Threads/rank | 31 | `configs/cluster_2node_default.yaml: threads_per_rank` |

## Planned Extensions

- **Column generation** (`cg` branch): generate `a_{b,s,r}` columns on-the-fly to avoid the full 127,200-variable explicit model
- **Benders decomposition**: master handles `x_{b,s}` (admission), subproblems handle per-gNB `a_{b,s,r}` — parallelizes naturally across 160 nodes
- **Warm start**: feed HiGHS LP relaxation solution to ParaSCIP to tighten early B&B bounds

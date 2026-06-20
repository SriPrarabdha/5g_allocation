"""Render a real parascip.set file from a ParascipLayout config.

Replaces the original PBS script's inline heredoc, which baked
parallel/maxnthreads and other settings directly into the job script --
that risked silently drifting out of sync with whatever rank/thread
layout was actually requested at launch. Now both mpiexec's --depth
(threads/rank) and this file's parallel/maxnthreads read from the same
cluster_config.yaml.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nr_slice_milp.cluster_config import ParascipLayout


def render_parascip_set(layout: ParascipLayout, out_path: str) -> None:
    lines = [
        "# LP solver: HiGHS",
        "lp/solver = highs",
        "# Number of threads per MPI rank",
        f"parallel/maxnthreads = {layout.threads_per_rank_resolved()}",
        "# B&B tree parallelism",
        "parallel/mode = 1",
        "# Time limit (seconds)",
        f"limits/time = {layout.time_limit_s}",
        "# Gap tolerance",
        f"limits/gap = {layout.gap}",
        "# Node limit per rank",
        f"limits/nodes = {layout.node_limit}",
    ]
    Path(out_path).write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    layout = ParascipLayout.from_yaml(args.cluster_config)
    layout.validate()
    render_parascip_set(layout, args.out)
    print(f"parascip.set written to {args.out} "
          f"({layout.total_ranks} ranks, {layout.solving_ranks} solving, "
          f"{layout.threads_per_rank_resolved()} threads/rank, "
          f"{layout.total_cpus_used()} CPUs total)")


if __name__ == "__main__":
    main()

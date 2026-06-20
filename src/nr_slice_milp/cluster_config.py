"""MPI rank / thread layout for ParaSCIP, kept as a single tunable source
of truth consumed by both the PBS submission script and local validation
(catches CPU-overshoot bugs, e.g. requesting more CPUs/node than are
actually usable, before any cluster submission).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class ParascipLayout:
    n_nodes: int = 2
    usable_cpus_per_node: int = 125
    ranks_per_node: int = 4
    threads_per_rank: int | None = None  # None -> computed from usable_cpus_per_node
    reserve_cpus_per_node: int = 1  # headroom beyond cpus already excluded as "usable"
    gap: float = 0.01
    time_limit_s: int = 14400
    node_limit: int = 1_000_000

    @property
    def total_ranks(self) -> int:
        return self.n_nodes * self.ranks_per_node

    @property
    def solving_ranks(self) -> int:
        # Rank 0 is the ParaSCIP/FiberSCIP Load Coordinator -- it does not
        # run branch-and-bound itself.
        return self.total_ranks - 1

    def threads_per_rank_resolved(self) -> int:
        if self.threads_per_rank is not None:
            return self.threads_per_rank
        return (self.usable_cpus_per_node - self.reserve_cpus_per_node) // self.ranks_per_node

    def total_cpus_used(self) -> int:
        return self.total_ranks * self.threads_per_rank_resolved()

    def validate(self) -> None:
        per_node_used = self.ranks_per_node * self.threads_per_rank_resolved()
        if per_node_used > self.usable_cpus_per_node:
            raise ValueError(
                f"{per_node_used} CPUs/node requested "
                f"({self.ranks_per_node} ranks x {self.threads_per_rank_resolved()} threads) "
                f"exceeds usable_cpus_per_node={self.usable_cpus_per_node}"
            )
        if self.solving_ranks < 1:
            raise ValueError(
                f"total_ranks={self.total_ranks} leaves no solving ranks "
                "after reserving rank 0 as Load Coordinator"
            )

    @classmethod
    def from_yaml(cls, path: str) -> "ParascipLayout":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return cls(**raw)

    def to_yaml(self, path: str) -> None:
        raw = {
            "n_nodes": self.n_nodes,
            "usable_cpus_per_node": self.usable_cpus_per_node,
            "ranks_per_node": self.ranks_per_node,
            "threads_per_rank": self.threads_per_rank,
            "reserve_cpus_per_node": self.reserve_cpus_per_node,
            "gap": self.gap,
            "time_limit_s": self.time_limit_s,
            "node_limit": self.node_limit,
        }
        with open(path, "w") as f:
            yaml.safe_dump(raw, f, sort_keys=False)


DEFAULT_LAYOUT = ParascipLayout()  # 2 nodes, 4 ranks/node, 31 threads/rank


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Query a resolved field from a ParascipLayout YAML config."
    )
    parser.add_argument("--cluster-config", required=True)
    parser.add_argument(
        "--field",
        required=True,
        choices=[
            "ranks_per_node",
            "threads_per_rank_resolved",
            "total_ranks",
            "solving_ranks",
            "total_cpus_used",
        ],
    )
    args = parser.parse_args()

    layout = ParascipLayout.from_yaml(args.cluster_config)
    layout.validate()

    value = getattr(layout, args.field)
    if callable(value):
        value = value()
    sys.stdout.write(str(value) + "\n")


if __name__ == "__main__":
    _main()

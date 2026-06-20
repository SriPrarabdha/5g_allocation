"""Problem-size and model parameters, replacing the old module-level globals.

Every downstream module takes an explicit ProblemConfig instead of reading
bare module variables — this is what lets evaluate/* derive N_B/N_S from
config instead of hardcoding them, and what makes swapping in a tiny
problem size (for local sanity checks) reliable instead of depending on
mutating already-imported module state.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml


@dataclass(frozen=True)
class SliceParams:
    name: str
    t_min_mbps: float
    rb_min: int
    rb_max: int
    weight: float


DEFAULT_SLICES: tuple[SliceParams, ...] = (
    SliceParams("eMBB", 100.0, 20, 80, 3.0),
    SliceParams("URLLC", 10.0, 10, 40, 5.0),
    SliceParams("mMTC", 1.0, 5, 30, 1.0),
)


@dataclass(frozen=True)
class ProblemConfig:
    n_b: int = 400
    n_r: int = 106
    rb_bandwidth_mhz: float = 0.18
    interference_radius: float = 0.15
    interference_seed: int = 42
    eff_seed: int = 42
    eff_low: float = 1.5
    eff_high: float = 6.0
    alpha_thresh: float = 0.6
    use_alpha_threshold: bool = True
    slices: tuple[SliceParams, ...] = field(default_factory=lambda: DEFAULT_SLICES)

    @property
    def n_s(self) -> int:
        return len(self.slices)

    @property
    def slice_names(self) -> list[str]:
        return [s.name for s in self.slices]

    @classmethod
    def from_yaml(cls, path: str) -> "ProblemConfig":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        slices_raw = raw.pop("slices", None)
        slices = (
            tuple(SliceParams(**s) for s in slices_raw)
            if slices_raw is not None
            else DEFAULT_SLICES
        )
        return cls(**raw, slices=slices)

    def to_yaml(self, path: str) -> None:
        raw = {
            "n_b": self.n_b,
            "n_r": self.n_r,
            "rb_bandwidth_mhz": self.rb_bandwidth_mhz,
            "interference_radius": self.interference_radius,
            "interference_seed": self.interference_seed,
            "eff_seed": self.eff_seed,
            "eff_low": self.eff_low,
            "eff_high": self.eff_high,
            "alpha_thresh": self.alpha_thresh,
            "use_alpha_threshold": self.use_alpha_threshold,
            "slices": [
                {
                    "name": s.name,
                    "t_min_mbps": s.t_min_mbps,
                    "rb_min": s.rb_min,
                    "rb_max": s.rb_max,
                    "weight": s.weight,
                }
                for s in self.slices
            ],
        }
        with open(path, "w") as f:
            yaml.safe_dump(raw, f, sort_keys=False)

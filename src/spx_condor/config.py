"""Load the pre-registered config. config.yaml is frozen; never written here.

Amendments (docs/amendments.md) live in overlay files (config-002.yaml, ...)
that contain only the top-level sections they change. `load_config(overlays=[...])`
replaces those sections wholesale, in order; every other section is still read
from config.yaml. An overlay may not introduce a section config.yaml lacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.yaml"


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    chain: tuple[Path, ...] = (CONFIG_PATH,)   # base config followed by the overlays applied

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    @property
    def data(self) -> dict[str, Any]:
        return self.raw["data"]

    @property
    def pricing(self) -> dict[str, Any]:
        return self.raw["pricing"]

    @property
    def entry(self) -> dict[str, Any]:
        return self.raw["entry"]

    @property
    def strikes(self) -> dict[str, Any]:
        return self.raw["strikes"]

    @property
    def exit(self) -> dict[str, Any]:
        return self.raw["exit"]

    @property
    def filter(self) -> dict[str, Any]:
        return self.raw["filter"]

    @property
    def sizing(self) -> dict[str, Any]:
        return self.raw["sizing"]

    @property
    def cash(self) -> dict[str, Any]:
        return self.raw["cash"]

    @property
    def acceptance(self) -> dict[str, Any]:
        return self.raw["acceptance"]


def _resolve(p: Path | str) -> Path:
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p


def load_config(path: Path | str = CONFIG_PATH, overlays: Iterable[Path | str] = ()) -> Config:
    base = _resolve(path)
    with open(base) as fh:
        raw = yaml.safe_load(fh)
    chain = [base]
    for ov in overlays:
        ovp = _resolve(ov)
        with open(ovp) as fh:
            sections = yaml.safe_load(fh) or {}
        unknown = sorted(set(sections) - set(raw))
        if unknown:
            raise ValueError(f"{ovp.name}: overlay introduces sections not in {base.name}: {unknown}")
        for key, value in sections.items():
            raw[key] = value          # whole-section replacement
        chain.append(ovp)
    return Config(raw, tuple(chain))

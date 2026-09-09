"""Load the pre-registered config. config.yaml is frozen; never written here."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.yaml"


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]

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


def load_config(path: Path | str = CONFIG_PATH) -> Config:
    with open(path) as fh:
        return Config(yaml.safe_load(fh))

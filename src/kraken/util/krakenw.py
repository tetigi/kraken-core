"""Provides tools to get information about the current environment controlled by kraken-wrapper."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Mapping


@dataclasses.dataclass
class KrakenwEnv:
    path: Path
    type: str

    @property
    def is_pex(self) -> bool:
        return self.type.startswith("PEX_")

    @classmethod
    def get(cls, environ: Mapping[str, str] | None = None) -> KrakenwEnv | None:
        if environ is None:
            environ = os.environ
        if "_KRAKENW_ENV_TYPE" in environ:
            return cls(Path(environ["_KRAKENW_ENV_PATH"]), environ["_KRAKENW_ENV_TYPE"])
        return None

    def to_env_vars(self) -> dict[str, str]:
        return {
            "_KRAKENW_ENV_PATH": str(self.path.absolute()),
            "_KRAKENW_ENV_TYPE": self.type,
        }

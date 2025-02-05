from __future__ import annotations

import sys
from pathlib import Path


def is_relative_to(apath: Path, bpath: Path) -> bool:
    """Checks if *apath* is a path relative to *bpath*."""

    if sys.version_info[:2] < (3, 9):
        try:
            apath.relative_to(bpath)
            return True
        except ValueError:
            return False
    else:
        return apath.is_relative_to(bpath)


def try_relative_to(apath: Path, bpath: Path | None = None) -> Path:
    try:
        return apath.relative_to(bpath or Path.cwd())
    except ValueError:
        return apath


def with_name(path: Path, name: str) -> Path:
    return path.parent / name

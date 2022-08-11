from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Iterator

import pytest

from kraken.core.context import Context
from kraken.core.project import Project

__version__ = "0.7.5"
logger = logging.getLogger(__name__)


@pytest.fixture(name="kraken_ctx")
def kraken_ctx() -> Iterator[Context]:
    context = Context(Path("build"))
    with context.as_current():
        yield context


@pytest.fixture(name="kraken_project")
def kraken_project(kraken_ctx: Context, path: Path | None = None) -> Iterator[Project]:
    if path is None:
        path = Path(sys._getframe(1).f_code.co_filename)
    kraken_ctx.root_project = Project("test", path.parent, None, kraken_ctx)
    with kraken_ctx.root_project.as_current():
        yield kraken_ctx.root_project

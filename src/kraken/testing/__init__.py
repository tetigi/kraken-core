from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path
from typing import Iterator

import _pytest.fixtures
import pytest

from kraken.core.build_context import BuildContext
from kraken.core.loader.python_script import inject_kraken_api_module_for_project
from kraken.core.project import Project
from kraken.core.task import Task

__version__ = "0.2.17"
logger = logging.getLogger(__name__)


def kraken_ctx() -> BuildContext:
    return BuildContext(Path(".build"))


@pytest.fixture(name="kraken_ctx")
def _kraken_ctx_fixture() -> BuildContext:
    return kraken_ctx()


@contextlib.contextmanager
def kraken_project(kraken_ctx: BuildContext, path: Path | None = None) -> Iterator[Project]:
    if path is None:
        path = Path(sys._getframe(1).f_code.co_filename)
    kraken_ctx.root_project = Project("test", path.parent, None, kraken_ctx)
    with inject_kraken_api_module_for_project(kraken_ctx.root_project, path) as (_api_module, _project_module):
        yield kraken_ctx.root_project


@pytest.fixture(name="kraken_project")
def _kraken_project_fixture(kraken_ctx: BuildContext, request: _pytest.fixtures.FixtureRequest) -> Iterator[Project]:
    with kraken_project(kraken_ctx, request.path) as project:
        yield project


def kraken_execute(ctx: BuildContext, targets: list[Task | str] | str) -> None:
    """Deprecated. Use :meth:`BuildContext.execute()` instead."""

    if isinstance(targets, str):
        targets = [targets]
    ctx.execute(targets, True)

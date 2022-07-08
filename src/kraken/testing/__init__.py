from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import _pytest.fixtures
import pytest

from kraken.core.build_context import BuildContext
from kraken.core.build_graph import BuildGraph
from kraken.core.loader.python_script import inject_kraken_api_module_for_project
from kraken.core.project import Project
from kraken.core.task import Task, TaskResult

__version__ = "0.2.6"
logger = logging.getLogger(__name__)


@pytest.fixture
def kraken_ctx() -> BuildContext:
    return BuildContext(Path(".build"))


@pytest.fixture
def kraken_project(kraken_ctx: BuildContext, request: _pytest.fixtures.FixtureRequest) -> Iterator[Project]:
    kraken_ctx.root_project = Project("test", request.path.parent, None, kraken_ctx)
    with inject_kraken_api_module_for_project(kraken_ctx.root_project, request.path) as (api_module, project_module):
        yield kraken_ctx.root_project


def kraken_execute(ctx: BuildContext, targets: list[Task | str] | str) -> None:
    """A rudimentary but correct implementation for executing the tasks defined in the build context *ctx*. The
    task or tasks to be built must be specified explicitly with the *targets* parameter.

    !!! warning

        This function should only be used for testing. In production, you should rely on the :mod:`kraken.cli`
        package and its executor.
    """

    if isinstance(targets, str):
        targets = [targets]

    ctx.finalize()

    # Resolve string references to task objects.
    targets = targets or []
    tasks = ctx.resolve_tasks([t for t in targets if isinstance(t, str)]) + [
        t for t in targets if not isinstance(t, str)
    ]

    if not tasks:
        raise ValueError("no tasks selected")

    graph = BuildGraph(tasks)
    graph.trim()
    assert graph, "BuildGraph cannot be empty"

    for task in graph.execution_order():
        try:
            if task.is_skippable():
                logger.info("Skip task %s", task.path)
                continue
        except NotImplementedError:
            pass
        try:
            if task.is_up_to_date():
                logger.info("Task %s is up to date", task.path)
                continue
        except NotImplementedError:
            pass
        logger.info("Run task %s", task.path)
        result = task.execute()
        logger.info("Result of task %s is %r", task.path, result)
        if result not in (TaskResult.SUCCEEDED, TaskResult.SKIPPED, TaskResult.UP_TO_DATE):
            raise Exception(f"Task {task} result is {result.name}")

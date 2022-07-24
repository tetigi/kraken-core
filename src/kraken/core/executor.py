""" This module provides the :class:`Executor` class which implements the correct execution of Kraken tasks
from a :class:`TaskGraph` and printing nicely colored status details in the terminal.

Currently, the executor does not execute any tasks in parallel. This could be achieved in the future by using
a :class:`ProcessPoolExecutor` that would also allow us to fully redirect the output of a task such that it
can be captured in its entirety, however it has the drawback that the task object needs to be pickleable. """

from __future__ import annotations

import builtins
import contextlib
import logging
import os
import sys
import traceback
from functools import partial

# from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, AnyStr, Iterator

from termcolor import colored

from kraken.core.graph import TaskGraph
from kraken.core.task import Task, TaskStatus, TaskStatusType

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def replace_stdio(
    stdin: IO[AnyStr] | None = None,
    stdout: IO[AnyStr] | None = None,
    stderr: IO[AnyStr] | None = None,
) -> Iterator[None]:
    """Temporarily replaces the file handles of stdin/sdout/stderr."""

    stdin_save: int | None = None
    stdout_save: int | None = None
    stderr_save: int | None = None

    if stdin is not None:
        stdin_save = os.dup(sys.stdin.fileno())
        os.dup2(stdin.fileno(), sys.stdin.fileno())
    if stdout is not None:
        stdout_save = os.dup(sys.stdout.fileno())
        os.dup2(stdout.fileno(), sys.stdout.fileno())
    if stderr is not None:
        stderr_save = os.dup(sys.stderr.fileno())
        os.dup2(stderr.fileno(), sys.stderr.fileno())

    try:
        yield
    finally:
        if stdin_save is not None:
            os.dup2(stdin_save, sys.stdin.fileno())
        if stdout_save is not None:
            os.dup2(stdout_save, sys.stdout.fileno())
        if stderr_save is not None:
            os.dup2(stderr_save, sys.stderr.fileno())


def _execute_task(task: Task, capture: bool) -> tuple[TaskStatus, str | None]:
    result = TaskStatus.failed("unknown error")
    output = None
    with contextlib.ExitStack() as exit_stack:
        if capture:
            fp = exit_stack.enter_context(NamedTemporaryFile(delete=False))
            exit_stack.enter_context(replace_stdio(None, fp, fp))
            exit_stack.callback(lambda: os.remove(fp.name))
        try:
            execute_result = task.execute()
            if execute_result is None:
                result = TaskStatus.succeeded()
            elif isinstance(execute_result, TaskStatus):
                result = execute_result
            else:
                raise RuntimeError(f"{task} did not return TaskResult, got {execute_result!r} instead")
        except BaseException as exc:
            result = TaskStatus.failed(f"unhandled exception: {exc}")
            traceback.print_exc()
        finally:
            if capture:
                fp.close()
                output = Path(fp.name).read_text()
    return result, output.rstrip() if output is not None else None


COLORS_BY_RESULT = {
    TaskStatusType.PENDING: "magenta",
    TaskStatusType.FAILED: "red",
    TaskStatusType.SKIPPED: "yellow",
    TaskStatusType.SUCCEEDED: "green",
    TaskStatusType.UP_TO_DATE: "green",
}


class Executor:
    def __init__(self, graph: TaskGraph, verbose: bool = False) -> None:
        self.graph = graph
        self.verbose = verbose

    def execute_task(self, task: Task) -> None:
        print = partial(builtins.print, flush=True)
        status = task.prepare() or TaskStatus.pending()
        if status.is_pending():
            print(">", task.path)

            # TODO (@NiklasRosenstein): Transfer values from output properties back to the main process.
            # TODO (@NiklasRosenstein): Until we actually start tasks in paralle, we don't benefit from
            #       using a ProcessPoolExecutor.
            # result = self.pool.submit(_execute_task, task, True).result()
            status, output = _execute_task(task, task.capture and not self.verbose)

            if (status.is_failed() or not task.capture or self.verbose) and output:
                print(output)

        print(
            ">",
            task.path,
            colored(status.type.name, COLORS_BY_RESULT[status.type], attrs=["bold"]),
            end="",
        )
        if status.message:
            print(f" ({status.message})", end="")
        print()

        self.graph.set_status(task, status)

    def execute(self) -> bool:
        while not self.graph.is_complete():
            tasks = list(self.graph.ready())
            if not tasks:
                return False
            for task in tasks:
                self.execute_task(task)
        return True

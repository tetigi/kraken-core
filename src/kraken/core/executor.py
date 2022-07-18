""" This module provides the :class:`Executor` class which implements the correct execution of Kraken tasks
from a :class:`TaskGraph` and printing nicely colored status details in the terminal.

Currently, the executor does not execute any tasks in parallel. This could be achieved in the future by using
a :class:`ProcessPoolExecutor` that would also allow us to fully redirect the output of a task such that it
can be captured in its entirety, however it has the drawback that the task object needs to be pickleable. """

from __future__ import annotations

import contextlib
import dataclasses
import enum
import logging
import os
import sys
import traceback

# from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, AnyStr, Iterator

from termcolor import colored

from kraken.core.graph import TaskGraph
from kraken.core.task import Task, TaskResult

logger = logging.getLogger(__name__)


class TaskStatus(enum.Enum):
    """Base on the task's methods (:meth:`Task.is_skippable` and :meth:`Task.is_up_to_date`), we derive the status
    of the task. This is different from the :class:`TaskResult` in that it represents the state of the task before
    its execution and how the task should be handled accordingly, wheras the :class:`TaskResult` represents the
    result of its execution."""

    SKIPPABLE = enum.auto()  #: The task can be skipped.
    UP_TO_DATE = enum.auto()  #: The task is up to date.
    OUTDATED = enum.auto()  #: The task is outdated.
    QUEUED = enum.auto()  #: The task needs to run, never checks if it is up to date.


def get_task_status(task: Task) -> TaskStatus:
    """Derive the status of a task before it is executed."""

    try:
        if task.is_skippable():
            return TaskStatus.SKIPPABLE
    except NotImplementedError:
        pass
    try:
        if task.is_up_to_date():
            return TaskStatus.UP_TO_DATE
        else:
            return TaskStatus.OUTDATED
    except NotImplementedError:
        return TaskStatus.QUEUED


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


@dataclasses.dataclass
class ExecutionResult:
    status: TaskResult
    message: str | None
    output: str


def _execute_task(task: Task, capture: bool) -> ExecutionResult:
    status = TaskResult.FAILED
    message = "unknown error"
    output = ""
    with contextlib.ExitStack() as exit_stack:
        if capture:
            fp = exit_stack.enter_context(NamedTemporaryFile(delete=False))
            exit_stack.enter_context(replace_stdio(None, fp, fp))
            exit_stack.callback(lambda: os.remove(fp.name))
        try:
            status = task.execute()
            message = ""
        except BaseException as exc:
            status, message = TaskResult.FAILED, f"unhandled exception: {exc}"
            traceback.print_exc()
        finally:
            if capture:
                fp.close()
                output = Path(fp.name).read_text()
    if not isinstance(status, TaskResult):
        raise RuntimeError(f"{task} did not return TaskResult, got {status!r} instead")
    return ExecutionResult(status, message, output.rstrip())


COLORS_BY_RESULT = {
    TaskResult.FAILED: "red",
    TaskResult.SKIPPED: "yellow",
    TaskResult.SUCCEEDED: "green",
    TaskResult.UP_TO_DATE: "green",
}

COLORS_BY_STATUS = {
    TaskStatus.SKIPPABLE: "yellow",
    TaskStatus.UP_TO_DATE: "green",
    TaskStatus.OUTDATED: "red",
    TaskStatus.QUEUED: "magenta",
}


class Executor:
    def __init__(self, graph: TaskGraph, verbose: bool = False) -> None:
        self.graph = graph
        self.verbose = verbose
        self.results: dict[str, ExecutionResult] = {}

    def execute_task(self, task: Task) -> ExecutionResult:
        status = get_task_status(task)
        if status == TaskStatus.SKIPPABLE:
            result = ExecutionResult(TaskResult.SKIPPED, None, "")
        elif status == TaskStatus.UP_TO_DATE:
            result = ExecutionResult(TaskResult.UP_TO_DATE, None, "")
        else:
            print(">", task.path)
            sys.stdout.flush()

            # TODO (@NiklasRosenstein): Transfer values from output properties back to the main process.
            # TODO (@NiklasRosenstein): Until we actually start tasks in paralle, we don't benefit from
            #       using a ProcessPoolExecutor.
            # result = self.pool.submit(_execute_task, task, True).result()
            result = _execute_task(task, task.capture and not self.verbose)

        if (result.status == TaskResult.FAILED or not task.capture or self.verbose) and result.output:
            print(result.output)
            sys.stdout.flush()

        print(
            ">",
            task.path,
            colored(result.status.name, COLORS_BY_RESULT[result.status], attrs=["bold"]),
            end="",
        )
        if result.message:
            print(f" ({result.message})", end="")
        print()
        sys.stdout.flush()

        self.results[task.path] = result
        return result

    def execute(self) -> bool:
        for task in self.graph.execution_order():
            result = self.execute_task(task)
            if result.status == TaskResult.FAILED:
                return False
        return True

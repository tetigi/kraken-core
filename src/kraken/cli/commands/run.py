from __future__ import annotations

import argparse
import builtins
import sys
from functools import partial

from termcolor import colored

from kraken.core import BuildError, Context, Task, TaskGraph

from ..executor import KrakenCliExecutorObserver
from .base import BuildGraphCommand


class RunCommand(BuildGraphCommand):
    class Args(BuildGraphCommand.Args):
        skip_build: bool
        allow_no_tasks: bool
        exclude: list[str] | None
        exclude_subgraph: list[str] | None

    def __init__(self, main_target: str | None = None) -> None:
        super().__init__()
        self._main_target = main_target

    def get_description(self) -> str:
        if self._main_target:
            return f'execute "{self._main_target}" tasks'
        else:
            return "execute one or more kraken tasks"

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-s", "--skip-build", action="store_true", help="just load the project, do not build")
        parser.add_argument("-0", "--allow-no-tasks", action="store_true", help="don't error if no tasks got selected")
        parser.add_argument("-x", "--exclude", action="append", help="exclude one or more tasks")
        parser.add_argument(
            "-X",
            "--exclude-subgraph",
            action="append",
            help="exclude the entire subgraphs of one or more tasks",
        )

    def resolve_tasks(self, args: BuildGraphCommand.Args, context: Context) -> list[Task]:
        if self._main_target:
            targets = [self._main_target] + list(args.targets or [])
            return context.resolve_tasks(targets)
        return super().resolve_tasks(args, context)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:  # type: ignore
        print = partial(builtins.print, flush=True)
        status_code = 0
        observer = KrakenCliExecutorObserver(
            context.resolve_tasks(args.exclude or []),
            context.resolve_tasks(args.exclude_subgraph or []),
        )

        if args.skip_build:
            print(colored("Skipped build due to %s flag" % (colored("-s,--skip-build", attrs=["bold"]),), "blue"))
        else:
            if not graph:
                if args.allow_no_tasks:
                    print(colored("Note: no tasks were selected (--allow-no-tasks)", "blue"), file=sys.stderr)
                    return 0
                else:
                    print(colored("Error: no tasks were selected", "red"), file=sys.stderr)
                    return 1

            try:
                context.execute(graph, observer=observer)
            except BuildError as exc:
                print()
                print(colored("Error: %s" % (exc,), "red"), file=sys.stderr, flush=True)
                status_code = 1

        return status_code

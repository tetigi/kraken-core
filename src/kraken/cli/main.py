from __future__ import annotations

import argparse
import builtins
import contextlib
import dataclasses
import logging
import os
import sys
import textwrap
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

from termcolor import colored

from kraken.cli import serialize
from kraken.cli.executor import status_to_text
from kraken.core import BuildError, Context, GroupTask, Property, Task, TaskGraph
from kraken.util.argparse import propagate_formatter_to_subparser
from kraken.util.helpers import not_none
from kraken.util.term import get_terminal_width

DEFAULT_BUILD_DIR = Path("build")
DEFAULT_PROJECT_DIR = Path(".")
BUILD_STATE_DIR = ".kraken/buildenv"

logger = logging.getLogger(__name__)
print = partial(builtins.print, flush=True)


@dataclasses.dataclass(frozen=True)
class _GlobalOptions:
    verbosity: int
    quietness: int
    build_dir: Path
    project_dir: Path

    @property
    def state_dir(self) -> Path:
        return self.build_dir / BUILD_STATE_DIR

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-v",
            dest="verbosity",
            action="count",
            default=0,
            help="increase the log level (can be specified multiple times)",
        )
        parser.add_argument(
            "-q",
            dest="quietness",
            action="count",
            default=0,
            help="decrease the log level (can be specified multiple times)",
        )
        parser.add_argument(
            "-b",
            "--build-dir",
            metavar="PATH",
            type=Path,
            default=DEFAULT_BUILD_DIR,
            help="the build directory to write to [default: %(default)s]",
        )
        parser.add_argument(
            "-p",
            "--project-dir",
            metavar="PATH",
            type=Path,
            default=DEFAULT_PROJECT_DIR,
            help="the root project directory [default: ./]",
        )

    @classmethod
    def collect(cls, args: argparse.Namespace) -> _GlobalOptions:
        return cls(
            verbosity=args.verbosity,
            quietness=args.quietness,
            build_dir=args.build_dir,
            project_dir=args.project_dir,
        )


@dataclasses.dataclass(frozen=True)
class _GraphOptions:
    tasks: list[str]
    resume: bool
    restart: bool
    no_save: bool

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("tasks", metavar="task", nargs="*", help="one or more tasks to execute")
        parser.add_argument("--resume", action="store_true", help="load previous build state")
        parser.add_argument(
            "--restart",
            choices=("all",),
            help="load previous build state, but discard existing results (requires --resume)",
        )
        parser.add_argument("--no-save", action="store_true", help="do not save the new build state")

    @classmethod
    def collect(cls, args: argparse.Namespace) -> _GraphOptions:
        return cls(
            tasks=args.tasks,
            resume=args.resume,
            restart=args.restart,
            no_save=args.no_save,
        )


@dataclasses.dataclass
class _RunOptions:
    allow_no_tasks: bool
    skip_build: bool
    exclude_tasks: list[str] | None
    exclude_tasks_subgraph: list[str] | None

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("-s", "--skip-build", action="store_true", help="just load the project, do not build")
        parser.add_argument("-0", "--allow-no-tasks", action="store_true", help="don't error if no tasks got selected")
        parser.add_argument("-x", "--exclude", metavar="TASK", action="append", help="exclude one or more tasks")
        parser.add_argument(
            "-X",
            "--exclude-subgraph",
            action="append",
            metavar="TASK",
            help="exclude the entire subgraphs of one or more tasks",
        )

    @classmethod
    def collect(cls, args: argparse.Namespace) -> _RunOptions:
        return cls(
            skip_build=args.skip_build,
            allow_no_tasks=args.allow_no_tasks,
            exclude_tasks=args.exclude,
            exclude_tasks_subgraph=args.exclude_subgraph,
        )


@dataclasses.dataclass
class _VizOptions:
    all: bool
    show: bool

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("-a", "--all", action="store_true", help="include all tasks in the graph")
        parser.add_argument("-s", "--show", action="store_true", help="show the graph in the browser (requires dot)")

    @classmethod
    def collect(cls, args: argparse.Namespace) -> _VizOptions:
        return cls(
            all=args.all,
            show=args.show,
        )


def _get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        formatter_class=lambda prog: argparse.RawDescriptionHelpFormatter(prog, width=120, max_help_position=60),
        description=textwrap.dedent(
            """
            The Kraken build system.

            Kraken focuses on ease of use and simplicity to model complex task orchestration workflows.
            """
        ),
    )
    _GlobalOptions.add_to_parser(parser)

    subparsers = parser.add_subparsers(dest="cmd")

    run = subparsers.add_parser("run", aliases=["r"])
    _GraphOptions.add_to_parser(run)
    _RunOptions.add_to_parser(run)

    query = subparsers.add_parser("query", aliases=["q"])

    query_subparsers = query.add_subparsers(dest="query_cmd")

    ls = query_subparsers.add_parser("ls")
    _GraphOptions.add_to_parser(ls)

    describe = query_subparsers.add_parser("describe", aliases=["d"])
    _GraphOptions.add_to_parser(describe)

    viz = query_subparsers.add_parser("visualize", aliases=["viz", "v"])
    _GraphOptions.add_to_parser(viz)
    _VizOptions.add_to_parser(viz)

    propagate_formatter_to_subparser(parser)
    return parser


def _init_logging(verbosity: int) -> None:
    if verbosity > 1:
        level = logging.DEBUG
    elif verbosity > 0:
        level = logging.INFO
    elif verbosity == 0:
        level = logging.WARNING
    elif verbosity < 0:
        level = logging.ERROR
    else:
        assert False, level
    logging.basicConfig(
        level=level,
        format=f"{colored('%(levelname)-7s', 'magenta')} | {colored('%(name)-24s', 'blue')} | "
        f"{colored('%(message)s', 'cyan')}",
    )


def _load_build_state(
    exit_stack: contextlib.ExitStack,
    global_options: _GlobalOptions,
    graph_options: _GraphOptions,
) -> tuple[Context, TaskGraph]:

    if graph_options.restart and not graph_options.resume:
        raise ValueError("the --restart option requires the --resume flag")

    context: Context | None = None
    if graph_options.resume:
        context, graph = serialize.load_build_state(global_options.state_dir)
        if not graph:
            raise ValueError("cannot --resume without build state")
        if graph and graph_options.restart:
            graph.discard_statuses()

    if context is None:
        context = Context(global_options.build_dir)
        context.load_project(global_options.project_dir)
        context.finalize()
        graph = TaskGraph(context)

    assert graph is not None
    if not graph_options.no_save:
        exit_stack.callback(lambda: serialize.save_build_state(global_options.state_dir, not_none(graph)))

    graph.set_targets(context.resolve_tasks(graph_options.tasks or None))
    return context, graph


def run(
    exit_stack: contextlib.ExitStack,
    global_options: _GlobalOptions,
    graph_options: _GraphOptions,
    run_options: _RunOptions,
) -> None:

    from kraken.cli.executor import KrakenCliExecutorObserver

    context, graph = _load_build_state(
        exit_stack=exit_stack,
        global_options=global_options,
        graph_options=graph_options,
    )

    context.observer = KrakenCliExecutorObserver(
        context.resolve_tasks(run_options.exclude_tasks or []),
        context.resolve_tasks(run_options.exclude_tasks_subgraph or []),
    )

    if run_options.skip_build:
        print("note: skipped build due to -s,--skip-build option.")
        sys.exit(0)
    else:
        if not graph:
            if run_options.allow_no_tasks:
                print("note: no tasks were selected (--allow-no-tasks)", "blue", file=sys.stderr)
                sys.exit(0)
            else:
                print("error: no tasks were selected", file=sys.stderr)
                sys.exit(1)

        try:
            context.execute(graph)
        except BuildError as exc:
            print()
            print("error:", exc, file=sys.stderr)
            sys.exit(1)


def query(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    exit_stack: contextlib.ExitStack,
    global_options: _GlobalOptions,
) -> None:

    global_options = _GlobalOptions.collect(args)
    graph_options = _GraphOptions.collect(args)

    context, graph = _load_build_state(
        exit_stack=exit_stack,
        global_options=global_options,
        graph_options=graph_options,
    )

    if args.query_cmd == "ls":
        ls(graph)
    elif args.query_cmd == "describe":
        describe(graph)
    elif args.query_cmd == "visualize":
        visualize(graph, _VizOptions.collect(args))
    else:
        parser.print_usage()


def ls(graph: TaskGraph) -> None:

    required_tasks = set(graph.tasks(targets_only=True))
    longest_name = max(map(len, (t.path for t in graph.tasks(all=True)))) + 1

    print()
    print(colored("Tasks", "blue", attrs=["bold", "underline"]))
    print()

    width = get_terminal_width(120)

    def _print_task(task: Task) -> None:
        line = [task.path.ljust(longest_name)]
        remaining_width = width - len(line[0])
        if task in required_tasks:
            line[0] = colored(line[0], "green")
        if task.default:
            line[0] = colored(line[0], attrs=["bold"])
        status = graph.get_status(task)
        if status is not None:
            line.append(f"[{status_to_text(status)}]")
            remaining_width -= 2 + len(status_to_text(status, colored=False)) + 1
        description = task.get_description()
        if description:
            remaining_width -= 2
            for part in textwrap.wrap(
                description,
                remaining_width,
                subsequent_indent=(width - remaining_width) * " ",
            ):
                line.append(part)
                line.append("\n")
            line.pop()
        print("  " + " ".join(line))

    def sort_key(task: Task) -> str:
        return task.path

    for task in sorted(graph.tasks(all=True), key=sort_key):
        if isinstance(task, GroupTask):
            continue
        _print_task(task)

    print()
    print(colored("Groups", "blue", attrs=["bold", "underline"]))
    print()

    for task in sorted(graph.tasks(all=True), key=sort_key):
        if not isinstance(task, GroupTask):
            continue
        _print_task(task)

    print()


def describe(graph: TaskGraph) -> None:

    tasks = list(graph.tasks(targets_only=True))
    print("selected", len(tasks), "task(s)")
    print()

    for task in tasks:
        print("Group" if isinstance(task, GroupTask) else "Task", colored(task.path, attrs=["bold", "underline"]))
        print("  Type:", type(task).__module__ + "." + type(task).__name__)
        print("  Type defined in:", colored(sys.modules[type(task).__module__].__file__ or "???", "cyan"))
        print("  Default:", task.default)
        print("  Capture:", task.capture)
        rels = list(task.get_relationships())
        print(colored("  Relationships", attrs=["bold"]), f"({len(rels)})")
        for rel in rels:
            print(
                "".ljust(4),
                colored(rel.other_task.path, "blue"),
                f"before={rel.inverse}, strict={rel.strict}",
            )
        print("  " + colored("Properties", attrs=["bold"]) + f" ({len(type(task).__schema__)})")
        longest_property_name = max(map(len, type(task).__schema__.keys())) if type(task).__schema__ else 0
        for key in type(task).__schema__:
            prop: Property[Any] = getattr(task, key)
            print(
                "".ljust(4),
                (key + ":").ljust(longest_property_name + 1),
                f'{colored(prop.get_or("<unset>"), "blue")}',
            )
        print()


def visualize(graph: TaskGraph, viz_options: _VizOptions) -> None:
    import io

    from nr.io.graphviz.render import render_to_browser
    from nr.io.graphviz.writer import GraphvizWriter

    buffer = io.StringIO()
    writer = GraphvizWriter(buffer if viz_options.show else sys.stdout)
    writer.digraph(fontname="monospace", rankdir="LR")
    writer.set_node_style(style="filled", shape="box")

    style_default_task = {"penwidth": "3"}
    style_selected_task = {"fillcolor": "darkgoldenrod1"}
    style_group_task = {"fillcolor": "dodgerblue"}
    style_goal_task = {"shape": "circle"}

    writer.subgraph("cluster_#legend", label="Legend")
    writer.node("#none", label="will not run")
    writer.node("#default", label="would run by default", **style_default_task)
    writer.node("#selected", label="will run", **style_selected_task)
    writer.node("#group", label="group task", **style_group_task)
    writer.node("#goal", label="goal task", **style_goal_task)
    writer.end()

    writer.subgraph("cluster_#build", label="Build Graph")

    executed_tasks = set(graph.tasks())
    targets = set(graph.tasks(targets_only=True))
    for task in graph.tasks(all=viz_options.all):
        writer.node(
            task.path,
            **(style_default_task if task.default else {}),
            **(
                style_group_task
                if isinstance(task, GroupTask)
                else style_selected_task
                if task in executed_tasks
                else {}
            ),
            **(style_goal_task if task in targets else {}),
        )
        for predecessor in graph.get_predecessors(task, ignore_groups=False):
            writer.edge(predecessor.path, task.path)

    writer.end()
    writer.end()

    if viz_options.show:
        render_to_browser(buffer.getvalue())


def main() -> NoReturn:
    parser = _get_argument_parser()
    args = parser.parse_args()
    global_options = _GlobalOptions.collect(args)
    _init_logging(global_options.verbosity - global_options.quietness)

    with contextlib.ExitStack() as exit_stack:
        if args.cmd == "run":
            run(exit_stack, global_options, _GraphOptions.collect(args), _RunOptions.collect(args))
        elif args.cmd == "query":
            query(parser, args, exit_stack, global_options)
        else:
            parser.print_usage()

    sys.exit(0)


def _entrypoint() -> NoReturn:
    profile_outfile = os.getenv("KRAKEN_PROFILING")
    if profile_outfile:
        import cProfile as profile

        with open(profile_outfile, "w"):
            pass
        prof = profile.Profile()
        try:
            prof.runcall(main)
        finally:
            prof.dump_stats(profile_outfile)
    else:
        main()


if __name__ == "__main__":
    _entrypoint()

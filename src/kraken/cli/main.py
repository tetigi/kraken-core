from __future__ import annotations

import argparse
import builtins
import contextlib
import dataclasses
import logging
import os
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from kraken.core import Context, GroupTask, Property, Task, TaskGraph

DEFAULT_BUILD_DIR = Path("build")
DEFAULT_PROJECT_DIR = Path(".")
BUILD_STATE_DIR = ".kraken/buildenv"

logger = logging.getLogger(__name__)
print = partial(builtins.print, flush=True)


@dataclasses.dataclass(frozen=True)
class _LoggingOptions:
    verbosity: int
    quietness: int

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

    @classmethod
    def collect(cls, args: argparse.Namespace) -> _LoggingOptions:
        return cls(
            verbosity=args.verbosity,
            quietness=args.quietness,
        )


@dataclasses.dataclass(frozen=True)
class _BuildOptions:
    build_dir: Path
    project_dir: Path

    @property
    def state_dir(self) -> Path:
        return self.build_dir / BUILD_STATE_DIR

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
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
    def collect(cls, args: argparse.Namespace) -> _BuildOptions:
        return cls(
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
    import textwrap

    from kraken.util.argparse import propagate_formatter_to_subparser

    parser = argparse.ArgumentParser(
        formatter_class=lambda prog: argparse.RawDescriptionHelpFormatter(prog, width=120, max_help_position=60),
        description=textwrap.dedent(
            """
            The Kraken build system.

            Kraken focuses on ease of use and simplicity to model complex task orchestration workflows.
            """
        ),
    )
    subparsers = parser.add_subparsers(dest="cmd")

    run = subparsers.add_parser("run", aliases=["r"])
    _LoggingOptions.add_to_parser(run)
    _BuildOptions.add_to_parser(run)
    _GraphOptions.add_to_parser(run)
    _RunOptions.add_to_parser(run)

    query = subparsers.add_parser("query", aliases=["q"])
    query_subparsers = query.add_subparsers(dest="query_cmd")

    ls = query_subparsers.add_parser("ls", description="list all tasks and task groups in the build")
    _LoggingOptions.add_to_parser(ls)
    _BuildOptions.add_to_parser(ls)
    _GraphOptions.add_to_parser(ls)

    describe = query_subparsers.add_parser(
        "describe",
        aliases=["d"],
        description="describe one or more tasks in detail",
    )
    _LoggingOptions.add_to_parser(describe)
    _BuildOptions.add_to_parser(describe)
    _GraphOptions.add_to_parser(describe)

    viz = query_subparsers.add_parser("visualize", aliases=["viz", "v"], description="generate a GraphViz of the build")
    _LoggingOptions.add_to_parser(viz)
    _BuildOptions.add_to_parser(viz)
    _GraphOptions.add_to_parser(viz)
    _VizOptions.add_to_parser(viz)

    # This command is used by kraken-wrapper to produce a lock file.
    env = query_subparsers.add_parser("env", description="produce a JSON file of the Python environment distributions")
    _LoggingOptions.add_to_parser(env)

    propagate_formatter_to_subparser(parser)
    return parser


def _init_logging(verbosity: int) -> None:
    from kraken._vendor.termcolor import colored

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
    build_options: _BuildOptions,
    graph_options: _GraphOptions,
) -> tuple[Context, TaskGraph]:
    from kraken.cli import serialize
    from kraken.core import Context, TaskGraph
    from kraken.util.helpers import not_none

    if graph_options.restart and not graph_options.resume:
        raise ValueError("the --restart option requires the --resume flag")

    context: Context | None = None
    if graph_options.resume:
        context, graph = serialize.load_build_state(build_options.state_dir)
        if not graph:
            raise ValueError("cannot --resume without build state")
        if graph and graph_options.restart:
            graph.discard_statuses()

    if context is None:
        context = Context(build_options.build_dir)
        context.load_project(build_options.project_dir)
        context.finalize()
        graph = TaskGraph(context)

    assert graph is not None
    if not graph_options.no_save:
        exit_stack.callback(lambda: serialize.save_build_state(build_options.state_dir, not_none(graph)))

    graph.set_targets(context.resolve_tasks(graph_options.tasks or None))
    return context, graph


def run(
    exit_stack: contextlib.ExitStack,
    build_options: _BuildOptions,
    graph_options: _GraphOptions,
    run_options: _RunOptions,
) -> None:

    from kraken.cli.executor import KrakenCliExecutorObserver
    from kraken.core import BuildError

    context, graph = _load_build_state(
        exit_stack=exit_stack,
        build_options=build_options,
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
) -> None:

    if not args.query_cmd:
        parser.print_usage()
        sys.exit(0)

    if args.query_cmd == "env":
        env()
        sys.exit(0)

    build_options = _BuildOptions.collect(args)
    graph_options = _GraphOptions.collect(args)

    context, graph = _load_build_state(
        exit_stack=exit_stack,
        build_options=build_options,
        graph_options=graph_options,
    )

    if args.query_cmd == "ls":
        ls(graph)
    elif args.query_cmd in ("describe", "d"):
        describe(graph)
    elif args.query_cmd in ("visualize", "viz", "v"):
        visualize(graph, _VizOptions.collect(args))
    else:
        assert False, args.query_cmd


def ls(graph: TaskGraph) -> None:
    import textwrap

    from kraken._vendor.termcolor import colored
    from kraken.cli.executor import status_to_text
    from kraken.core import GroupTask
    from kraken.util.term import get_terminal_width

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
    from kraken._vendor.termcolor import colored

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

    from kraken._vendor.nr.io.graphviz.render import render_to_browser
    from kraken._vendor.nr.io.graphviz.writer import GraphvizWriter

    buffer = io.StringIO()
    writer = GraphvizWriter(buffer if viz_options.show else sys.stdout)
    writer.digraph(fontname="monospace", rankdir="LR")
    writer.set_node_style(style="filled", shape="box")

    style_default = {"penwidth": "3"}
    style_goal = {"fillcolor": "lawngreen"}
    style_select = {"fillcolor": "darkgoldenrod1"}
    style_group = {"shape": "ellipse"}
    style_edge_non_strict = {"style": "dashed"}

    writer.subgraph("cluster_#legend", label="Legend")
    writer.node("#task", label="task")
    writer.node("#group", label="group task", **style_group)
    writer.node("#default", label="would run by default", **style_default)
    writer.node("#selected", label="will run", **style_select)
    writer.node("#goal", label="goal task", **style_goal)
    writer.end()

    writer.subgraph("cluster_#build", label="Build Graph")

    goal_tasks = set(graph.tasks(targets_only=True))
    selected_tasks = set(graph.tasks())

    for task in graph.tasks(all=viz_options.all):
        style = {}
        style.update(style_default if task.default else {})
        style.update(style_group if isinstance(task, GroupTask) else {})
        style.update(style_select if task in selected_tasks else {})
        style.update(style_goal if task in goal_tasks else {})

        writer.node(task.path, **style)
        for predecessor in graph.get_predecessors(task, ignore_groups=False):
            writer.edge(
                predecessor.path,
                task.path,
                **({} if graph.get_edge(predecessor, task).strict else style_edge_non_strict),
            )

    writer.end()
    writer.end()

    if viz_options.show:
        render_to_browser(buffer.getvalue())


def env() -> None:
    import json

    from kraken._vendor.nr.python.environment.distributions import get_distributions

    dists = sorted(get_distributions().values(), key=lambda dist: dist.name)
    print(json.dumps([dist.to_json() for dist in dists], sort_keys=True))


def main() -> NoReturn:
    parser = _get_argument_parser()
    args = parser.parse_args()
    if not args.cmd:
        parser.print_usage()
        sys.exit(0)

    logging_options = _LoggingOptions.collect(args)
    _init_logging(logging_options.verbosity - logging_options.quietness)

    with contextlib.ExitStack() as exit_stack:
        if args.cmd in ("run", "r"):
            run(exit_stack, _BuildOptions.collect(args), _GraphOptions.collect(args), _RunOptions.collect(args))
        elif args.cmd in ("query", "q"):
            query(parser, args, exit_stack)
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

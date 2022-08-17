from __future__ import annotations

import argparse
import builtins
import contextlib
import logging
import os
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from kraken.core import Context, Property, Task, TaskGraph
    from kraken.core.cli.option_sets import BuildOptions, GraphOptions, RunOptions, VizOptions

BUILD_SCRIPT = Path(".kraken.py")
BUILD_SUPPORT_DIRECTORY = "build-support"
logger = logging.getLogger(__name__)
print = partial(builtins.print, flush=True)


def _get_argument_parser(prog: str) -> argparse.ArgumentParser:
    import textwrap

    from kraken.core.cli.option_sets import BuildOptions, GraphOptions, LoggingOptions, RunOptions, VizOptions
    from kraken.core.util.argparse import propagate_formatter_to_subparser

    parser = argparse.ArgumentParser(
        prog,
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
    LoggingOptions.add_to_parser(run)
    BuildOptions.add_to_parser(run)
    GraphOptions.add_to_parser(run)
    RunOptions.add_to_parser(run)

    query = subparsers.add_parser("query", aliases=["q"])
    query_subparsers = query.add_subparsers(dest="query_cmd")

    ls = query_subparsers.add_parser("ls", description="list all tasks and task groups in the build")
    LoggingOptions.add_to_parser(ls)
    BuildOptions.add_to_parser(ls)
    GraphOptions.add_to_parser(ls)

    describe = query_subparsers.add_parser(
        "describe",
        aliases=["d"],
        description="describe one or more tasks in detail",
    )
    LoggingOptions.add_to_parser(describe)
    BuildOptions.add_to_parser(describe)
    GraphOptions.add_to_parser(describe)

    viz = query_subparsers.add_parser("visualize", aliases=["viz", "v"], description="generate a GraphViz of the build")
    LoggingOptions.add_to_parser(viz)
    BuildOptions.add_to_parser(viz)
    GraphOptions.add_to_parser(viz)
    VizOptions.add_to_parser(viz)

    # This command is used by kraken-wrapper to produce a lock file.
    env = query_subparsers.add_parser("env", description="produce a JSON file of the Python environment distributions")
    LoggingOptions.add_to_parser(env)

    propagate_formatter_to_subparser(parser)
    return parser


def _load_build_state(
    exit_stack: contextlib.ExitStack,
    build_options: BuildOptions,
    graph_options: GraphOptions,
) -> tuple[Context, TaskGraph]:
    from kraken.core import Context, TaskGraph
    from kraken.core.cli import serialize
    from kraken.core.util.helpers import not_none

    if graph_options.restart and not graph_options.resume:
        raise ValueError("the --restart option requires the --resume flag")

    # Read the pythonpath from the build script file and add it to sys.path.
    build_script = build_options.project_dir / BUILD_SCRIPT
    if build_script.is_file():
        from kraken.core.util.importing import append_to_sys_path
        from kraken.core.util.requirements import parse_requirements_from_python_script

        with build_script.open() as fp:
            pythonpath = parse_requirements_from_python_script(fp).pythonpath
        if BUILD_SUPPORT_DIRECTORY not in pythonpath:
            pythonpath = (*pythonpath, BUILD_SUPPORT_DIRECTORY)
        exit_stack.enter_context(append_to_sys_path(pythonpath))

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
    build_options: BuildOptions,
    graph_options: GraphOptions,
    run_options: RunOptions,
) -> None:

    from kraken.core import BuildError
    from kraken.core.cli.executor import ColoredDefaultPrintingExecutorObserver

    context, graph = _load_build_state(
        exit_stack=exit_stack,
        build_options=build_options,
        graph_options=graph_options,
    )

    context.observer = ColoredDefaultPrintingExecutorObserver(
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


def ls(graph: TaskGraph) -> None:
    import textwrap

    from termcolor import colored

    from kraken.core import GroupTask
    from kraken.core.cli.executor import status_to_text
    from kraken.core.util.term import get_terminal_width

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
    from termcolor import colored

    from kraken.core import GroupTask

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


def visualize(graph: TaskGraph, viz_options: VizOptions) -> None:
    import io

    from nr.io.graphviz.render import render_to_browser
    from nr.io.graphviz.writer import GraphvizWriter

    from kraken.core import GroupTask

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

    from nr.python.environment.distributions import get_distributions

    dists = sorted(get_distributions().values(), key=lambda dist: dist.name)
    print(json.dumps([dist.to_json() for dist in dists], sort_keys=True))


def main_internal(prog: str, argv: list[str] | None) -> NoReturn:
    from kraken.core.cli.option_sets import BuildOptions, GraphOptions, LoggingOptions, RunOptions, VizOptions

    parser = _get_argument_parser(prog)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if not args.cmd:
        parser.print_usage()
        sys.exit(0)

    if LoggingOptions.available(args):
        LoggingOptions.collect(args).init_logging()

    if args.cmd in ("run", "r"):
        with contextlib.ExitStack() as exit_stack:
            run(exit_stack, BuildOptions.collect(args), GraphOptions.collect(args), RunOptions.collect(args))

    elif args.cmd in ("query", "q"):
        if not args.query_cmd:
            parser.print_usage()
            sys.exit(0)

        if args.query_cmd == "env":
            env()
            sys.exit(0)

        build_options = BuildOptions.collect(args)
        graph_options = GraphOptions.collect(args)

        with contextlib.ExitStack() as exit_stack:
            _context, graph = _load_build_state(
                exit_stack=exit_stack,
                build_options=build_options,
                graph_options=graph_options,
            )

            if args.query_cmd == "ls":
                ls(graph)
            elif args.query_cmd in ("describe", "d"):
                describe(graph)
            elif args.query_cmd in ("visualize", "viz", "v"):
                visualize(graph, VizOptions.collect(args))
            else:
                assert False, args.query_cmd

    else:
        parser.print_usage()

    sys.exit(0)


def main(prog: str = "kraken", argv: list[str] | None = None) -> NoReturn:
    profile_outfile = os.getenv("KRAKEN_PROFILING")
    if profile_outfile:
        import cProfile as profile

        with open(profile_outfile, "w"):  # Make sure the file exists
            pass

        prof = profile.Profile()
        try:
            prof.runcall(main_internal, prog, argv)
        finally:
            prof.dump_stats(profile_outfile)
    else:
        main_internal(prog, argv)


if __name__ == "__main__":
    main()

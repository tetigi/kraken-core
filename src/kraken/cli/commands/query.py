from __future__ import annotations

import argparse
import io
import os
import sys
import textwrap
from typing import Any

from nr.io.graphviz.render import render_to_browser
from nr.io.graphviz.writer import GraphvizWriter
from termcolor import colored

from kraken.core import Context, GroupTask, Property, Task, TaskGraph, TaskStatus, TaskStatusType

from ..executor import COLORS_BY_STATUS, status_to_text
from .base import BuildGraphCommand, print


def get_terminal_width(default: int = 80) -> int:
    """Returns the terminal width through :func:`os.get_terminal_size`, falling back to the `COLUMNS`
    environment variable. If neither is available, return *default*."""

    try:
        terminal_width = os.get_terminal_size().columns
    except OSError:
        try:
            terminal_width = int(os.getenv("COLUMNS", ""))
        except ValueError:
            terminal_width = default
    return terminal_width


class LsCommand(BuildGraphCommand):
    """list all tasks"""

    class Args(BuildGraphCommand.Args):
        default: bool
        all: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument(
            "-d",
            "--default",
            action="store_true",
            help="trim non-default tasks (only without selected targets)",
        )

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: BuildGraphCommand.Args) -> None:
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


class IsUpToDateCommand(BuildGraphCommand):
    """ask if the specified targets are up to date."""

    class Args(BuildGraphCommand.Args):
        is_up_to_date: bool
        legend: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("--legend", action="store_true", help="print out a legend along with the query result")

    def execute(self, args: BuildGraphCommand.Args) -> int | None:  # type: ignore[override]
        args.quiet = True
        return super().execute(args)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:  # type: ignore
        tasks = list(graph.tasks(targets_only=True))
        print(f"querying status of {len(tasks)} task(s)")
        print()

        need_to_run = 0
        up_to_date = 0
        for task in graph.execution_order():
            if task not in tasks:
                continue
            status = task.prepare() or TaskStatus.pending()
            print(" ", task.path, status_to_text(status))
            if status.is_skipped() or status.is_up_to_date():
                up_to_date += 1
            else:
                need_to_run += 1

        print()
        print(colored(f"{up_to_date} task(s) are up to date, need to run {need_to_run} task(s)", attrs=["bold"]))

        if args.legend:
            print()
            print("legend:")
            help_text = {
                TaskStatusType.PENDING: "the task is pending execution",
                TaskStatusType.SKIPPED: "the task can be skipped",
                TaskStatusType.UP_TO_DATE: "the task is up to date",
            }
            for status_type, help in help_text.items():
                print(colored(status_type.name.rjust(12), COLORS_BY_STATUS[status_type]) + ":", help)

        exit_code = 0 if need_to_run == 0 else 1
        print()
        print("exit code:", exit_code)
        sys.exit(exit_code)


class DescribeCommand(BuildGraphCommand):
    """describe one or more tasks in detail"""

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: BuildGraphCommand.Args) -> None:
        tasks = context.resolve_tasks(args.targets)
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


class VizCommand(BuildGraphCommand):
    """GraphViz for the task graph"""

    class Args(BuildGraphCommand.Args):
        all: bool
        show: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-a", "--all", action="store_true", help="include all tasks in the graph")
        parser.add_argument("-s", "--show", action="store_true", help="show the graph in the browser (requires `dot`)")

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> None:  # type: ignore[override]
        buffer = io.StringIO()
        writer = GraphvizWriter(buffer if args.show else sys.stdout)
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
        for task in graph.tasks(all=args.all):
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

        if args.show:
            render_to_browser(buffer.getvalue())

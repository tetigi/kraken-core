from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

DEFAULT_BUILD_DIR = Path("build")
DEFAULT_PROJECT_DIR = Path(".")
BUILD_STATE_DIR = ".kraken/buildenv"


@dataclasses.dataclass(frozen=True)
class LoggingOptions:
    # NOTE (@NiklasRosenstein): This class is considered public API; the kraken-wrapper module uses it.

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

    @staticmethod
    def available(args: argparse.Namespace) -> bool:
        return hasattr(args, "verbosity")

    @classmethod
    def collect(cls, args: argparse.Namespace) -> LoggingOptions:
        return cls(
            verbosity=args.verbosity,
            quietness=args.quietness,
        )

    def init_logging(self, format: str | None = None) -> None:
        import logging

        from termcolor import colored

        verbosity = self.verbosity - self.quietness

        if format is None:
            format = " | ".join(
                (
                    colored("%(levelname)-7s", "magenta"),
                    colored("%(name)-24s", "blue"),
                    colored("%(message)s", "cyan"),
                )
            )

        if verbosity > 1:
            level = logging.DEBUG
        elif verbosity > 0:
            level = logging.INFO
        elif verbosity == 0:
            level = logging.WARNING
        elif verbosity < 0:
            level = logging.ERROR
        else:
            assert False, verbosity

        logging.basicConfig(level=level, format=format)


@dataclasses.dataclass(frozen=True)
class BuildOptions:
    build_dir: Path
    project_dir: Path
    state_dir: Path
    additional_state_dirs: list[Path]
    no_load_project: bool

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
        parser.add_argument(
            "--state-dir",
            metavar="PATH",
            type=Path,
            help=f"specify the main build state directory [default: ${{--build-dir}}/{BUILD_STATE_DIR}]",
        )
        parser.add_argument(
            "--additional-state-dir",
            metavar="PATH",
            type=Path,
            help="specify an additional state directory to load build state from. can be specified multiple times",
        )
        parser.add_argument(
            "--no-load-project",
            action="store_true",
            help="do not load the root project. this is only useful when loading an existing build state",
        )

    @classmethod
    def collect(cls, args: argparse.Namespace) -> BuildOptions:
        return cls(
            build_dir=args.build_dir,
            project_dir=args.project_dir,
            state_dir=args.state_dir or self.build_dir / BUILD_STATE_DIR,
            additional_state_dirs=args.additional_state_dir or [],
            no_load_project=args.no_load_project,
        )


@dataclasses.dataclass(frozen=True)
class GraphOptions:
    tasks: list[str]
    resume: bool
    restart: bool
    no_save: bool
    all: bool

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser, saveable: bool = True) -> None:
        parser.add_argument("tasks", metavar="task", nargs="*", help="one or more tasks to execute")
        parser.add_argument("-a", "--all", action="store_true", help="select all tasks")
        parser.add_argument("--resume", action="store_true", help="load previous build state")
        parser.add_argument(
            "--restart",
            choices=("all",),
            help="load previous build state, but discard existing results (requires --resume)",
        )
        if saveable:
            parser.add_argument("--no-save", action="store_true", help="do not save the new build state")

    @classmethod
    def collect(cls, args: argparse.Namespace) -> GraphOptions:
        return cls(
            tasks=args.tasks,
            resume=args.resume,
            restart=args.restart,
            no_save=getattr(args, "no_save", True),
            all=args.all,
        )


@dataclasses.dataclass(frozen=True)
class RunOptions:
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
    def collect(cls, args: argparse.Namespace) -> RunOptions:
        return cls(
            skip_build=args.skip_build,
            allow_no_tasks=args.allow_no_tasks,
            exclude_tasks=args.exclude,
            exclude_tasks_subgraph=args.exclude_subgraph,
        )


@dataclasses.dataclass(frozen=True)
class VizOptions:
    inactive: bool
    show: bool
    reduce: bool
    reduce_keep_explicit: bool

    @staticmethod
    def add_to_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("-i", "--inactive", action="store_true", help="include inactive tasks in the graph")
        parser.add_argument("-s", "--show", action="store_true", help="show the graph in the browser (requires dot)")
        parser.add_argument("-R", "--reduce", action="store_true", help="fully transitively reduce the graph")
        parser.add_argument(
            "-r",
            "--reduce-keep-explicit",
            action="store_true",
            help="transitively reduce the graph but keep explicit edges",
        )

    @classmethod
    def collect(cls, args: argparse.Namespace) -> VizOptions:
        return cls(
            inactive=args.inactive,
            show=args.show,
            reduce=args.reduce,
            reduce_keep_explicit=args.reduce_keep_explicit,
        )

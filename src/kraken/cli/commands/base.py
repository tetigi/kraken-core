from __future__ import annotations

import argparse
import builtins
import enum
import logging
import os
import shlex
import sys
import uuid
from functools import partial
from pathlib import Path

import dill
from slap.core.cli import Command
from termcolor import colored

from kraken.cli.buildenv.environment import BuildEnvironment
from kraken.cli.buildenv.lockfile import Lockfile
from kraken.cli.buildenv.project import DefaultProjectImpl, ProjectInterface
from kraken.cli.buildenv.requirements import RequirementSpec
from kraken.core import Context, Task, TaskGraph

DEFAULT_BUILD_DIR = Path("build")
DEFAULT_PROJECT_DIR = Path(".")
logger = logging.getLogger(__name__)
print = partial(builtins.print, flush=True)


class InstallSource(enum.Enum):
    REQUIREMENTS = enum.auto()
    LOCKFILE = enum.auto()

    def readable(self) -> str:
        return "requirements" if self == InstallSource.REQUIREMENTS else "lock file"


class InstallResult(enum.Enum):
    UP_TO_DATE = enum.auto()
    INSTALLED = enum.auto()
    UPDATED = enum.auto()
    UPGRADED = enum.auto()

    def readable(self) -> str:
        return " ".join(self.name.split("_")).lower()


class BuildAwareCommand(Command):
    """A build aware command is aware of the build environment and provides the capabilities to dispatch the
    same command to the same command inside the build environment.

    It serves as the base command for all Kraken commands as they either need to dispatch to the build environment
    or manage it."""

    class Args:
        verbose: int
        quiet: bool
        build_dir: Path
        project_dir: Path

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("-v", "--verbose", action="count", help="always show task output and logs", default=0)
        parser.add_argument("-q", "--quiet", action="store_true", help="show less logs")
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

    def in_build_environment(self) -> bool:
        """Returns `True` if we're currently situated inside a build environment."""

        return os.getenv("KRAKEN_MANAGED") == "1"

    def get_build_environment(self, args: Args) -> BuildEnvironment:
        """Returns the handle to manage the build environment."""

        return BuildEnvironment(args.project_dir, args.build_dir / ".kraken" / "venv", args.verbose)

    def get_project_interface(self, args: Args) -> ProjectInterface:
        """Returns the implementation that deals with project specific data such as build requirements and
        lock files on disk."""

        return DefaultProjectImpl(args.project_dir, kraken_cli_develop=os.environ.get("KRAKEN_DEVELOP") == "1")

    def install(
        self,
        build_env: BuildEnvironment,
        project: ProjectInterface,
        upgrade: bool = False,
        reinstall: bool = False,
    ) -> tuple[InstallSource, InstallResult]:
        """Make sure that the build environment exists and the requirements are installed.

        :param build_env: The build environment to ensure is up to date.
        :param project: Implementation that provides access to the requirement spec and lockfile.
        :param upgrade: If set to `True`, ignore the lock file and existing build environment.
        :param reinstall: If set to `True`, ignore the build environment, but use the lock file.
        """

        requirements = project.get_requirement_spec()
        lockfile_path = project.get_lock_file()
        lockfile = Lockfile.from_path(lockfile_path)

        if upgrade and lockfile:
            logger.info("Ignoring lockfile (%s) (upgrade=True)", lockfile_path)
            lockfile = None

        install_required = not build_env.exists()
        if upgrade and build_env.exists():
            logger.info("Ignoring existing build environment (%s) (upgrade=True)", build_env.path)
            install_required = True

        build_env_existed = build_env.exists()
        if not install_required:
            if os.getenv("KRAKEN_REINSTALL_BUILD_ENV") == "1" and build_env.exists():
                logger.info(
                    "Ignoring existing build environment (%s) (KRAKEN_REINSTALL_BUILD_ENV=1)",
                    build_env.path,
                )
                install_required = True
            elif reinstall and build_env.exists():
                logger.info(
                    "Ignoring existing build environment (%s) (reinstall=True)",
                    build_env.path,
                )
                install_required = True

        source: RequirementSpec | Lockfile = requirements
        source_type = InstallSource.REQUIREMENTS

        if lockfile and lockfile.requirements != requirements:
            logger.warning("Lock file (%s) is outdated. Consider updating it with `kraken env upgrade`.", lockfile_path)

        if lockfile:
            logger.info("Using requirements from lock file (%s).", lockfile_path)
            source = lockfile
            source_type = InstallSource.LOCKFILE
            requirements = lockfile.to_pinned_requirement_spec()
        else:
            # TODO (@NiklasRosenstein): Get path to source of requirements from ProjectImpl
            logger.info("Using requirements from project (%s).", project.get_requirements_path())

        if not install_required and build_env.changed(requirements):
            logger.warning("Build environment is outdated.")
            logger.info("  Build environment hashes: %s", ", ".join(build_env.hashes))
            logger.info("  Requirements hash: %s", requirements.to_hash(build_env.hash_algorithm))
            install_required = True

        if install_required:
            logger.info("Creating build environment (%s)", build_env.path)
            build_env.install(requirements)
            build_env.set_hashes(source)
            logger.info(
                "Build environment (%s) installed (hash: %s).",
                build_env.path,
                requirements.to_hash(build_env.hash_algorithm),
            )
            return source_type, (
                InstallResult.UPGRADED
                if build_env_existed and upgrade
                else InstallResult.UPDATED
                if build_env_existed
                else InstallResult.INSTALLED
            )
        else:
            logger.info("Build environment (%s) is up to date.", build_env.path)
            return source_type, InstallResult.UP_TO_DATE

    def dispatch_to_build_environment(self, args: Args) -> int:
        """Dispatch to the build environment."""

        if self.in_build_environment():
            raise RuntimeError("cannot dispatch if we're already inside the build environment")

        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        self.install(build_env, project)

        logger.info(
            "Dispatching command `%s` to build environment (%s)",
            "kraken " + " ".join(map(shlex.quote, sys.argv[1:])),
            build_env.path,
        )

        with build_env.activate():
            os.environ["KRAKEN_MANAGED"] = "1"
            from kraken.cli.__main__ import _main

            try:
                _main()
            except SystemExit as exc:
                return exc.code

    def execute(self, args: Args) -> int | None:
        if args.verbose >= 2:
            level = logging.DEBUG
        elif args.verbose >= 1:
            level = logging.INFO
        elif args.quiet:
            level = logging.ERROR
        else:
            level = logging.WARNING
        logging.basicConfig(
            level=level,
            format=f"{colored('%(levelname)-7s', 'magenta')} | {colored('%(name)-24s', 'blue')} | "
            f"{colored('%(message)s', 'cyan')}",
        )
        return None


class BuildGraphCommand(BuildAwareCommand):
    """Base class for commands that require the fully materialized Kraken build graph."""

    class Args(BuildAwareCommand.Args):
        file: Path | None
        targets: list[str]
        resume: bool
        restart: bool
        no_save: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("targets", metavar="target", nargs="*", help="one or more target to build")
        parser.add_argument("--resume", action="store_true", help="load previous build state")
        parser.add_argument(
            "--restart",
            choices=("all",),
            help="load previous build state, but discard existing results (requires --resume)",
        )
        parser.add_argument("--no-save", action="store_true", help="do not save the new build state")

    def resolve_tasks(self, args: Args, context: Context) -> list[Task]:
        return context.resolve_tasks(args.targets or None)

    def execute(self, args: Args) -> int | None:  # type: ignore[override]
        super().execute(args)

        if args.restart and not args.resume:
            self.get_parser().error("the --restart option requires the --resume flag")

        if not self.in_build_environment():
            return self.dispatch_to_build_environment(args)

        # NOTE (@NiklasRosenstein): If we're inside the build environment that is managed by Kraken, we could
        #       skip this step, but if we're not (e.g. if the user manually sets KRAKEN_MANAGED=1), we still
        #       need to update the path.
        project = self.get_project_interface(args)
        sys.path += [str((args.project_dir / path)) for path in project.get_requirement_spec().pythonpath]

        context: Context | None = None
        graph: TaskGraph | None = None
        state_dir = args.build_dir / ".kraken" / "build-state"

        if args.resume:
            context, graph = load_state(state_dir)
            if not graph:
                print(colored("Error: Cannot --resume with no build state", "red"))
                return 1
            if graph and args.restart:
                graph.discard_statuses()

        if context is None:
            context = Context(args.build_dir)
            context.load_project(None, Path.cwd())
            context.finalize()
            graph = TaskGraph(context)

        assert graph is not None
        targets = self.resolve_tasks(args, context)
        graph.set_targets(targets)

        try:
            return self.execute_with_graph(context, graph, args)
        finally:
            if not args.no_save:
                save_state(state_dir, graph)

    def execute_with_graph(self, context: Context, graph: TaskGraph, args: Args) -> int | None:
        raise NotImplementedError

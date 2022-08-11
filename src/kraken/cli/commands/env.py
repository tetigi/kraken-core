from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from termcolor import colored

from kraken.cli.buildenv.environment import BuildEnvironment
from kraken.cli.buildenv.lockfile import Lockfile
from kraken.cli.buildenv.project import ProjectInterface
from kraken.util.asciitable import AsciiTable

from .base import BuildAwareCommand, print

logger = logging.getLogger(__name__)


class EnvInfoCommand(BuildAwareCommand):
    """provide the info on the build environment"""

    class Args(BuildAwareCommand.Args):
        path: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument(
            "-P",
            "--path",
            action="store_true",
            help="print the path to the build environment, or nothing and return 1 if it does not exist.",
        )

    def execute(self, args: Args) -> int | None:  # type: ignore[override]
        super().execute(args)
        if self.in_build_environment():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")

        build_env = self.get_build_environment(args)
        if args.path:
            if build_env.exists():
                print(build_env.path.absolute())
                return 0
            else:
                return 1

        project = self.get_project_interface(args)
        requirements = project.get_requirement_spec()
        requirements_hash = requirements.to_hash(build_env.hash_algorithm)
        lockfile_path = project.get_lock_file()
        lockfile = Lockfile.from_path(lockfile_path)
        lockfile_hash = lockfile.requirements.to_hash(build_env.hash_algorithm) if lockfile else "-"
        lockfile_pinned_hash = (
            lockfile.to_pinned_requirement_spec().to_hash(build_env.hash_algorithm) if lockfile else "-"
        )

        table = AsciiTable()
        table.headers = ["Source", "Path", f"Hash ({build_env.hash_algorithm})"]
        table.rows.append(["Requirements", str(project.get_requirements_path()), colored(requirements_hash, "cyan")])
        table.rows.append(
            [
                "Lockfile (requirements)",
                str(lockfile_path),
                colored(lockfile_hash, "green" if lockfile_hash == requirements_hash else "red"),
            ]
        )
        table.rows.append(["Lockfile (pinned)", str(lockfile_path), colored(lockfile_pinned_hash, "cyan")])

        good_hashes = (requirements_hash, lockfile_pinned_hash)
        for idx, hash in enumerate(build_env.hashes or ["-"]):
            table.rows.append(
                [
                    "Environment (installed)" if idx == 0 else "*",
                    str(build_env.path) if idx == 0 else "*",
                    colored(hash, "green" if hash in good_hashes and hash != "-" else "red"),
                ]
            )

        table.print()
        return 0


class BaseEnvCommand(BuildAwareCommand):
    def write_lock_file(self, build_env: BuildEnvironment, project: ProjectInterface) -> Path:
        result = build_env.calculate_lockfile(project.get_requirement_spec())
        lockfile_path = project.get_lock_file()
        logger.info("Generating lockfile (%s)", lockfile_path)
        result.lockfile.write_to(lockfile_path)
        build_env.set_hashes(result.lockfile)
        if result.extra_distributions:
            logger.warning(
                "Your build environment (%s) contains %d distributions that are not required. %s",
                len(result.extra_distributions),
                ", ".join(result.extra_distributions),
            )
        return lockfile_path

    def execute(self, args: BuildAwareCommand.Args) -> int | None:
        super().execute(args)
        if self.in_build_environment():
            self.get_parser().error("`kraken env` commands cannot be used inside managed enviroment")
        return None


class EnvInstallCommand(BaseEnvCommand):
    """ensure the build environment is installed"""

    class Args(BaseEnvCommand.Args):
        reinstall: bool

    def init_parser(self, parser: argparse.ArgumentParser) -> None:
        super().init_parser(parser)
        parser.add_argument("--reinstall", action="store_true", help="reinstall the build environment")

    def execute(self, args: Args) -> None:  # type: ignore[override]
        super().execute(args)
        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        source, result = self.install(build_env, project, reinstall=args.reinstall)
        print(f"Build environment {build_env.path} is {result.readable()} with {source.readable()}.")


class EnvUpgradeCommand(BaseEnvCommand):
    """upgrade the build environment and lock file (if it exists)."""

    def execute(self, args: Any) -> None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        source, result = self.install(build_env, project, upgrade=True)
        print(f"Build environment {build_env.path} is {result.readable()} with {source.readable()}.")
        if project.get_lock_file().exists():
            self.write_lock_file(build_env, project)


class EnvLockCommand(BaseEnvCommand):
    """create or update the lock file"""

    def execute(self, args: Any) -> int:
        super().execute(args)
        build_env = self.get_build_environment(args)
        project = self.get_project_interface(args)
        if not build_env.exists():
            print("error: need a build environment to create a lock file.", file=sys.stderr)
            return 1
        if build_env.changed(project.get_requirement_spec()):
            print("error: cannot lock out-of-sync build environment", file=sys.stderr)
            return 2
        lockfile_path = self.write_lock_file(build_env, project)
        print("Lockfile", lockfile_path, "updated.")
        return 0


class EnvRemoveCommand(BaseEnvCommand):
    """remove the build environment"""

    def execute(self, args: BuildAwareCommand.Args) -> int | None:
        super().execute(args)
        build_env = self.get_build_environment(args)
        if build_env.exists():
            build_env.remove()
            print(f"Removed build environment {build_env.path}.")
            return 0
        else:
            print(f"error: build environment {build_env.path} does not exist.")
            return 1

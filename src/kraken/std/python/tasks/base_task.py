from __future__ import annotations

import abc
import logging
import os
import subprocess as sp
from typing import Iterable, MutableMapping

from kraken.core import Project, Task, TaskRelationship, TaskStatus
from nr.python.environment.virtualenv import VirtualEnvInfo, get_current_venv

from kraken.std.python.buildsystem import ManagedEnvironment

from ..settings import python_settings

logger = logging.getLogger(__name__)


class EnvironmentAwareDispatchTask(Task):
    """Base class for tasks that run a subcommand. The command ensures that the command is aware of the
    environment configured in the project settings."""

    def __init__(self, name: str, project: Project) -> None:
        super().__init__(name, project)
        self.settings = python_settings(project)

    def get_relationships(self) -> Iterable[TaskRelationship]:
        from .install_task import InstallTask

        # If a python.install task exists, we may need it.
        for task in (t for t in self.project.tasks().values() if isinstance(t, InstallTask)):
            yield TaskRelationship(task, True, False)

        yield from super().get_relationships()

    @abc.abstractmethod
    def get_execute_command(self) -> list[str] | TaskStatus:
        pass

    def handle_exit_code(self, code: int) -> TaskStatus:
        return TaskStatus.from_exit_code(None, code)

    def activate_managed_environment(self, venv: ManagedEnvironment, environ: MutableMapping[str, str]) -> None:
        active_venv = get_current_venv(environ)
        if active_venv is None or self.settings.always_use_managed_env:
            if not venv.exists():
                logger.warning("Managed environment (%s) does not exist", venv)
                return
            managed_env = VirtualEnvInfo(venv.get_path())
            logger.info("Activating managed environment (%s)", managed_env.path)
            managed_env.activate(environ)
        elif active_venv:
            logger.info("An active virtual environment was found, not activating managed environment")

    def execute(self) -> TaskStatus:
        command = self.get_execute_command()
        if isinstance(command, TaskStatus):
            return command
        env = os.environ.copy()
        if self.settings.build_system and self.settings.build_system.supports_managed_environments():
            self.activate_managed_environment(self.settings.build_system.get_managed_environment(), env)
        logger.info("%s", command)
        result = sp.call(command, cwd=self.project.directory, env=env)
        return self.handle_exit_code(result)

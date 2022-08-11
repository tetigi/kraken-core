""" Implements a loader for Python scripts. These Python scripts have access to importing certain build context
related members from the :mod:`kraken.api` module; note that these members are only available when imported in
the context of a script executed by this loader and not otherwise. """

from __future__ import annotations

import abc
import types
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kraken.core.project import Project


class ProjectLoaderError(Exception):
    def __init__(self, project: Project, message: str) -> None:
        self.project = project
        self.message = message

    def __str__(self) -> str:
        return f"[{self.project.path}] {self.message}"


class ProjectLoader(abc.ABC):
    @abc.abstractmethod
    def load_project(self, project: Project) -> None:
        """
        :param project: The project to load the build script into.
        """


class PythonScriptProjectLoader(ProjectLoader):
    BUILD_SCRIPT = Path(".kraken.py")
    BUILD_SUPPORT_DIRECTORY = "build-support"

    def load_project(self, project: Project) -> None:
        from kraken.util.importing import append_to_sys_path
        from kraken.util.requirements import parse_requirements_from_python_script

        file = project.directory / self.BUILD_SCRIPT
        if not file.is_file():
            raise ProjectLoaderError(project, f"file {file!r} does not exist")

        if project.parent is None:
            # We only support loading the additional python path for the root project.
            with file.open() as fp:
                pythonpath = parse_requirements_from_python_script(fp).pythonpath
            if self.BUILD_SUPPORT_DIRECTORY not in pythonpath:
                pythonpath = (*pythonpath, self.BUILD_SUPPORT_DIRECTORY)
        else:
            pythonpath = ()

        with project.as_current(), append_to_sys_path(pythonpath):
            code = compile(file.read_text(), filename=file, mode="exec")
            module = types.ModuleType(project.path)
            module.__file__ = str(file)
            exec(code, vars(module))

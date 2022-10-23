""" Implements a loader for Python scripts. These Python scripts have access to importing certain build context
related members from the :mod:`kraken.api` module; note that these members are only available when imported in
the context of a script executed by this loader and not otherwise. """

from __future__ import annotations

import abc
from argparse import Namespace
import logging
import re
import types
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kraken.core.project import Project

from craftr.dsl import Closure

logger = logging.getLogger(__name__)


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
    """ The default loader for build scripts of a project. The header of the build script may contain a
    `# ::lang=<lang>` flag, where `<lang>` can be `python` (default) or `dsl`. For any other value,
    a warning will be generated and the default will be used. """

    BUILD_SCRIPT = Path(".kraken.py")

    def load_project(self, project: Project) -> None:
        file = project.directory / self.BUILD_SCRIPT
        if not file.is_file():
            raise ProjectLoaderError(project, f"file {file!r} does not exist")

        code = file.read_text()
        lang_match = re.search(r'^#\s*::\s*dialect\s+(.*)', code, re.MULTILINE)
        lang = lang_match.group(1) if lang_match else 'python'
        if lang not in ('python', 'dsl'):
            logger.warn('Project build script "%s" has an unexpected language marker (# ::dialect %s), falling '
                'back to "python".', file, lang)
            lang = "python"

        with project.as_current():
            if lang == "python":
                code = compile(file.read_text(), filename=file, mode="exec")
                module = types.ModuleType(project.path)
                module.__file__ = str(file)
                exec(code, vars(module))
            elif lang == "dsl":
                ctx = Namespace()
                ctx.project = project
                Closure(None, None, project).run_code(file.read_text(), filename=str(file))
            else:
                assert False, lang

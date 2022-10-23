""" Abstraction of Python build systems such as Poetry and Slap. """


from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from kraken.std.python.pyproject import Pyproject

if TYPE_CHECKING:
    from ..settings import PythonSettings


class PythonBuildSystem(abc.ABC):
    """Abstraction of a Python build system."""

    name: ClassVar[str]

    @abc.abstractmethod
    def supports_managed_environments(self) -> bool:
        """Return `True` if the build system supports managed environments."""

    @abc.abstractmethod
    def get_managed_environment(self) -> ManagedEnvironment:
        """Return a handle for the managed environment.

        :raise NotImplementedError: If :meth:`supports_managed_environment` returns `False`.
        """

    @abc.abstractmethod
    def update_pyproject(self, settings: PythonSettings, pyproject: Pyproject) -> None:
        """A chance to permanently update the Pyproject configuration."""

    @abc.abstractmethod
    def requires_login(self) -> bool:
        """Return True if this build system requires a separate login step (i.e. if the credentials cannot be
        passed at install time to the command-line)."""

    def login(self, settings: PythonSettings) -> None:
        """Log into the Python package indices."""

        raise NotImplementedError

    @abc.abstractmethod
    def build(self, output_directory: Path, as_version: str | None = None) -> list[Path]:
        """Build one or more distributions of the project managed by this build system.

        :param output_directory: The directory where the distributions should be placed.
        :param as_version: A version number for the built distributions.
        """


class ManagedEnvironment(abc.ABC):
    """Abstraction of a managed Python environment."""

    @abc.abstractmethod
    def exists(self) -> bool:
        """Return `True` if the managed environment exists."""

    @abc.abstractmethod
    def get_path(self) -> Path:
        """Return the path to the managed environment.

        :raises RuntimeError: May be raised if the environment does not exist (it may not be possible to
            determine the path of the environment before it exists depending on the build system).
        """

    @abc.abstractmethod
    def install(self, settings: PythonSettings) -> None:
        """Install the managed environment. This should be a no-op if the environment already exists."""


def detect_build_system(project_directory: Path) -> PythonBuildSystem | None:
    """Detect the Python build system used in *project_directory*."""

    pyproject_toml = project_directory / "pyproject.toml"
    if not pyproject_toml.is_file():
        return None

    pyproject_content = pyproject_toml.read_text()

    if "[tool.slap]" in pyproject_content:
        from .slap import SlapPythonBuildSystem

        return SlapPythonBuildSystem(project_directory)

    if "poetry-core" in pyproject_content:
        from .poetry import PoetryPythonBuildSystem

        return PoetryPythonBuildSystem(project_directory)

    return None

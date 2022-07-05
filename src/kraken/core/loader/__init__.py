from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import Callable, Iterable

import pkg_resources

from kraken.core.project import Project

ENTRYPOINT = "kraken.core.loader"

logger = logging.getLogger(__name__)


class BuildScriptLoader(abc.ABC):
    @abc.abstractmethod
    def detect_in_project_directory(self, project_dir: Path) -> Path | None:
        """
        Args:
            project_dir (Path): The directory to search for a build script that can be loaded.
        Returns:
            Path: The path to the file that should be loaded.
            None: If the directory does not contain a file that can be loaded.
        """

    @abc.abstractmethod
    def match_file(self, file: Path) -> bool | Path | None:
        """
        Args:
            file (Path): A file to check if it can be loaded by this loader.
        Returns:
            bool: `True` if the file can be loaded, `False` if not.
            Path: The path to the project directory belonging to the file, if the file can be loaded.
            None: If the file cannot be loaded.
        """

    @abc.abstractmethod
    def load_script(self, file: Path, project: Project) -> None:
        """
        Args:
            file (Path): The build script to load.
            project (Project): The project to load the build script into.
        """


def get_loader_implementations() -> Iterable[BuildScriptLoader]:
    """Iterate over the registered loader implementations."""

    for ep in pkg_resources.iter_entry_points(ENTRYPOINT):
        try:
            factory: Callable[[], BuildScriptLoader] = ep.load()
            yield factory()
        except Exception:
            logger.exception("an unhandled exception occurred while fetching BuildScriptLoader implementation: %s", ep)

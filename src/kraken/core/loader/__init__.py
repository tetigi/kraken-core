from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import Callable, Iterable

import pkg_resources

from kraken.core.project import Project

ENTRYPOINT = "kraken.core.loader"

logger = logging.getLogger(__name__)


class ProjectLoaderError(Exception):
    pass


class ProjectLoader(abc.ABC):
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


def get_loader_implementations() -> Iterable[ProjectLoader]:
    """Iterate over the registered loader implementations."""

    for ep in pkg_resources.iter_entry_points(ENTRYPOINT):
        try:
            factory: Callable[[], ProjectLoader] = ep.load()
            yield factory()
        except Exception:
            logger.exception("an unhandled exception occurred while fetching BuildScriptLoader implementation: %s", ep)


def detect_project_loader(file: Path | None, directory: Path | None) -> tuple[Path, Path, ProjectLoader]:
    """Detects the loader for the given *file* or *directory*. Both may be specified, but at least one must
    present. If only a directory is given, the loader must report the file to load. If only a file is given,
    the loader _may_ report the respective project directory.

    Raises:
        ProjectLoaderError: If the given file and/or directory combination cannot be loaded by any loader.
    """

    if file is None:
        if directory is None:
            raise ValueError("need file or directory")
        for loader in get_loader_implementations():
            file = loader.detect_in_project_directory(directory)
            if file:
                break
        else:
            raise ProjectLoaderError(f'"{directory}" does not look like a Kraken project directory')
    else:
        for loader in get_loader_implementations():
            match = loader.match_file(file)
            if isinstance(match, Path):
                if directory is None:
                    directory = match
                break
            elif match:
                if directory is None:
                    directory = file.parent
                break
        else:
            raise ProjectLoaderError(f'"{file}" is not accepted by any project loader')

    return file, directory, loader

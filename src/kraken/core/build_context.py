from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .project import Project


class BuildContext:
    """This class is the single instance where all components of a build process come together."""

    def __init__(self, build_directory: Path) -> None:
        self.root_project: Optional[Project] = None
        self.build_directory = build_directory

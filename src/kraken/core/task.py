from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .action import Action
    from .project import Project


class Task:
    """Represents a logical unit of work."""

    name: str
    project: Project
    metadata: list[Any]
    dependencies: list[Task]
    dependants: list[Task]
    default: bool

    def __init__(self, action: Optional[Action], name: str, project: Project) -> None:
        self.action = action
        self.name = name
        self.project = project
        self.metadata = []
        self.dependencies = []
        self.dependants = []
        self.default = True

    def execute(self) -> None:
        if self.action is not None:
            self.action.execute()

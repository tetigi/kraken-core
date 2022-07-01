from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from typing_extensions import TypeAlias

if TYPE_CHECKING:
    from .actions import Action
    from .project import Project

AnyTask: TypeAlias = "Task[Action | None]"
T_Action = TypeVar("T_Action", bound="Action | None", covariant=True)


class TaskCaptureMode(enum.Enum):
    """Describes how the output of the task should be captured, if at all."""

    #: The task output should not be captured.
    NONE = enum.auto()

    #: The task output should be captured, but always be shown in the build.
    SEMI = enum.auto()

    #: The task output should be fully captured and not shown (unless the task fails).
    FULL = enum.auto()


@dataclasses.dataclass
class Task(Generic[T_Action]):
    """Represents a logical unit of work."""

    action: T_Action
    name: str
    project: Project
    metadata: list[Any] = dataclasses.field(default_factory=list)
    dependencies: list[AnyTask] = dataclasses.field(default_factory=list)  #: Strict dependencies
    after: list[AnyTask] = dataclasses.field(default_factory=list)  #: Optional dependencies
    before: list[AnyTask] = dataclasses.field(default_factory=list)  #: Optional predecessors
    default: bool = True
    capture: TaskCaptureMode = TaskCaptureMode.FULL

    @property
    def path(self) -> str:
        if self.project.parent is None:
            return f":{self.name}"
        else:
            return f"{self.project.path}:{self.name}"

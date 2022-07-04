from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from typing_extensions import TypeAlias

if TYPE_CHECKING:
    from .action import Action
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

    name: str
    project: Project
    action: T_Action
    metadata: list[Any] = dataclasses.field(default_factory=list)
    dependencies: list[AnyTask] = dataclasses.field(default_factory=list)  #: Strict dependencies
    after: list[AnyTask] = dataclasses.field(default_factory=list)  #: Optional dependencies
    before: list[AnyTask] = dataclasses.field(default_factory=list)  #: Optional predecessors
    default: bool = True
    capture: TaskCaptureMode = TaskCaptureMode.FULL

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path!r})"

    @property
    def path(self) -> str:
        if self.project.parent is None:
            return f":{self.name}"
        else:
            return f"{self.project.path}:{self.name}"

    def finalize(self) -> None:
        """This method is called by :meth:`BuildContext.finalize()`. It gives the task a chance update its
        configuration before the build process is executed. Most commonly, custom task implementations will
        initialize their :attr:`action`, as the delayed action creation is often the main reason to creating
        a Task subclass in the first place."""

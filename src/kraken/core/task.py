from __future__ import annotations

import enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from typing_extensions import TypeAlias

from .property import HasProperties, Property

if TYPE_CHECKING:
    from .action import Action
    from .project import Project

AnyTask: TypeAlias = "Task[Action]"
T_Action = TypeVar("T_Action", bound="Action", covariant=True)


class TaskCaptureMode(enum.Enum):
    """Describes how the output of the task should be captured, if at all."""

    #: The task output should not be captured.
    NONE = enum.auto()

    #: The task output should be captured, but always be shown in the build.
    SEMI = enum.auto()

    #: The task output should be fully captured and not shown (unless the task fails).
    FULL = enum.auto()


class Task(Generic[T_Action], HasProperties):
    """Represents a logical unit of work."""

    name: str
    project: Project
    action: Property[T_Action] = Property()
    metadata: list[Any]
    dependencies: list[AnyTask]  #: Strict dependencies
    after: list[AnyTask]  #: Optional dependencies
    before: list[AnyTask]  #: Optional predecessors
    default: bool = True
    capture: TaskCaptureMode = TaskCaptureMode.FULL

    def __init__(self, name: str, project: Project, action: T_Action | None = None) -> None:
        super().__init__()
        self.name = name
        self.project = project
        self.action.on_set(lambda action: action.task.set(cast(AnyTask, self)))  # type: ignore[misc]
        if action is not None:
            self.action.set(action)
        self.metadata = []
        self.dependencies = []
        self.after = []
        self.before = []

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path!r})"

    @property
    def path(self) -> str:
        if self.project.parent is None:
            return f":{self.name}"
        else:
            return f"{self.project.path}:{self.name}"

    @property
    def build_directory(self) -> Path:
        return self.project.build_directory / self.name

    def finalize(self) -> None:
        """This method is called by :meth:`BuildContext.finalize()`. It gives the task a chance update its
        configuration before the build process is executed. Most commonly, custom task implementations will
        initialize their :attr:`action`, as the delayed action creation is often the main reason to creating
        a Task subclass in the first place.

        If the task generates it's :attr:`action` in this method only, it must also call :meth:`Action.finalize()`.
        """

        from .action import Action

        action = self.action.get_or(None)
        if action is not None and not isinstance(action, Task):
            assert isinstance(action, Action), self
            action.finalize()

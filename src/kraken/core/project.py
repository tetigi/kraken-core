from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional, Type, TypeVar, cast

from .task import Task
from .utils import flatten

if TYPE_CHECKING:
    from .build_context import BuildContext

T_Task = TypeVar("T_Task", bound="Task")


class Project:
    """A project consolidates tasks related to a directory on the filesystem."""

    name: str
    directory: Path
    parent: Optional[Project]
    context: BuildContext

    def __init__(self, name: str, directory: Path, parent: Optional[Project], context: BuildContext) -> None:
        self.name = name
        self.directory = directory
        self.parent = parent
        self.context = context

        # We store all members that can be referenced by a fully qualified name in the same dictionary to ensure
        # we're not accidentally allocating the same name twice.
        self._members: dict[str, Task | Project] = {}

    def __repr__(self) -> str:
        return f"Project({self.path})"

    @property
    def path(self) -> str:
        """Returns the path that uniquely identifies the project in the current build context."""

        if self.parent is None:
            return ":"
        elif self.parent.parent is None:
            return f":{self.name}"
        else:
            return f"{self.parent.path}:{self.name}"

    @property
    def build_directory(self) -> Path:
        """Returns the recommended build directory for the project; this is a directory inside the context
        build directory ammended by the project name."""

        return self.context.build_directory / self.path.replace(":", "/").lstrip("/")

    def tasks(self) -> Mapping[str, Task]:
        return {t.name: t for t in self._members.values() if isinstance(t, Task)}

    def children(self) -> Mapping[str, Project]:
        return {p.name: p for p in self._members.values() if isinstance(p, Project)}

    def resolve_tasks(self, tasks: Iterable[str | Task]) -> list[Task]:
        return list(
            flatten(self.context.resolve_tasks([task], self) if isinstance(task, str) else [task] for task in tasks)
        )

    def add_task(self, task: Task) -> None:
        """Adds a task to the project.

        Raises:
            ValueError: If a member with the same name already exists or if the task's project does not match
        """

        if task.name in self._members:
            raise ValueError(f"{self} already has a member {task.name!r}, cannot add {task}")
        if task.project is not self:
            raise ValueError(f"{task}.project mismatch")
        self._members[task.name] = task

    def add_child(self, project: Project) -> None:
        """Adds a project as a child project.

        Raises:
            ValueError: If a member with the same name already exists or if the project's parent does not match
        """

        if project.name in self._members:
            raise ValueError(f"{self} already has a member {project.name!r}, cannot add {project}")
        if project.parent is not self:
            raise ValueError(f"{project}.parent mismatch")
        self._members[project.name] = project

    def do(
        self,
        name: str,
        task_type: Type[T_Task] = cast(Any, Task),
        default: bool = True,
        capture: bool = True,
    ) -> T_Task:
        """Add a task to the project under the given name, executing the specified action."""

        if name in self._members:
            raise ValueError(f"{self} already has a member {name!r}")

        task = task_type(name, self)
        task.default = default
        task.capture = capture
        self.add_task(task)
        return task

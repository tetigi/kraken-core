from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional, Type, TypeVar, cast, overload

from .task import GroupTask, Task
from .utils import NotSet, flatten

if TYPE_CHECKING:
    from .context import Context

T = TypeVar("T")
T_Task = TypeVar("T_Task", bound="Task")


class Project:
    """A project consolidates tasks related to a directory on the filesystem."""

    name: str
    directory: Path
    parent: Optional[Project]
    context: Context
    metadata: list[Any]  #: A list of arbitrary objects that are usually looked up by type.

    def __init__(self, name: str, directory: Path, parent: Optional[Project], context: Context) -> None:
        self.name = name
        self.directory = directory
        self.parent = parent
        self.context = context
        self.metadata = []

        # We store all members that can be referenced by a fully qualified name in the same dictionary to ensure
        # we're not accidentally allocating the same name twice.
        self._members: dict[str, Task | Project] = {}

        self.group("fmt")
        self.group("lint")
        self.group("build")
        self.group("test")

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
        default: bool | None = None,
        capture: bool | None = None,
        group: str | GroupTask | None = None,
        **kwargs: Any,
    ) -> T_Task:
        """Add a task to the project under the given name, executing the specified action.

        :param name: The name of the task to add.
        :param task_type: The type of task to add.
        :param default: Override :attr:`Task.default`.
        :param capture: Override :attr:`Task.capture`.
        :param group: Add the task to the given group in the project.
        :param kwargs: Any number of properties to set on the task. Unknown properties will be ignored
            with a warning log.
        :return: The created task.
        """

        if name in self._members:
            raise ValueError(f"{self} already has a member {name!r}")

        task = task_type(name, self)
        if default is not None:
            task.default = default
        if capture is not None:
            task.capture = capture
        task.update(**kwargs)
        self.add_task(task)
        if isinstance(group, str):
            group = self.group(group)
        if group is not None:
            group.add(task)
        return task

    def group(self, name: str) -> GroupTask:
        """Create or get a group of the given name. If a task with the given name already exists, it must refer
        to a task of type :class:`GroupTask`, otherwise a :class:`RuntimeError` is raised."""

        task = self.tasks().get(name)
        if task is None:
            task = self.do(name, GroupTask)
        elif not isinstance(task, GroupTask):
            raise RuntimeError(f"{task.path!r} must be a GroupTask, but got {type(task).__name__}")

        return task

    def find_metadata(self, of_type: type[T]) -> T | None:
        """Returns the first entry in the :attr:`metadata` that is of the specified type."""

        return next((x for x in self.metadata if isinstance(x, of_type)), None)

    @overload
    @staticmethod
    def current() -> Project:
        """Returns the current project or raises a :class:`RuntimeError`."""

    @overload
    @staticmethod
    def current(fallback: T) -> Project | T:
        """Returns the current project or *fallback*."""

    @staticmethod
    def current(fallback: T | NotSet = NotSet.Value) -> Project | T:
        try:
            from kraken.api import project

            return project
        except RuntimeError:
            if fallback is not NotSet.Value:
                return fallback
            raise RuntimeError("no current project")

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Generic, Iterator, Optional, Type, TypeVar, Union, cast

if TYPE_CHECKING:
    from .build_context import BuildContext
    from .task import Task

ProjectMember = Union["Project", "Task"]
T_ProjectMember = TypeVar("T_ProjectMember", bound=ProjectMember)


class Project:
    """A project consolidates related tasks."""

    directory: Path
    name: str
    parent: Optional[Project]
    context: BuildContext

    def __init__(self, directory: Path, name: str, parent: Optional[Project], context: BuildContext) -> None:
        self.directory = directory
        self.name = name
        self.parent = parent
        self.context = context

        # We store all members that can be referenced by a fully qualified name in the same
        # dictionary to ensure we're not accidentally allocating the same name twice.
        self._members: dict[str, ProjectMember] = {}

    def __repr__(self) -> str:
        return f'Project(path="{self.path}")'

    @property
    def path(self) -> str:
        if self.parent is None:
            return ":"
        else:
            return f"{self.parent.path}:{self.name}"

    @property
    def members(self) -> ProjectMembers[ProjectMember]:
        """Returns the superset of all members in the project."""

        return ProjectMembers(self, self._members)

    @property
    def tasks(self) -> ProjectTasks:
        return ProjectTasks(self, self._members)

    @property
    def children(self) -> ProjectChildren:
        return ProjectChildren(self, self._members)


class ProjectMembers(Generic[T_ProjectMember]):
    """Container for the members of a project."""

    def __init__(
        self,
        project: "Project",
        members: dict[str, ProjectMember],
    ) -> None:
        self._project = project
        self._members = members

    @staticmethod
    def _type() -> Optional[Type[T_ProjectMember]]:
        return None

    def __iter__(self) -> Iterator[str]:
        _type = self._type()
        for key, value in self._members.items():
            if _type is None or isinstance(value, _type):
                yield key

    def __getitem__(self, name: str) -> T_ProjectMember:
        try:
            member = self._members[name]
        except KeyError:
            raise KeyError(f"project {self._project} has no member {name!r}")
        _type = self._type()
        if _type is not None and not isinstance(member, _type):
            raise KeyError(
                f"project {self._project} member {name!r} is a {type(member).__name__} " f"but not a {_type.__name__}"
            )
        return cast(T_ProjectMember, member)


class ProjectTasks(ProjectMembers["Task"]):
    @staticmethod
    def _type() -> Optional[Type[Task]]:
        from .task import Task

        return Task

    def add(self, task: Task) -> None:
        if task.project is not self._project:
            raise RuntimeError("Task.project does not match")
        if task.name in self._members:
            raise KeyError(f"project {self._project} already has a member {task.name!r}")
        self._members[task.name] = task


class ProjectChildren(ProjectMembers["Project"]):
    @staticmethod
    def _type() -> Optional[Type[Project]]:
        return Project

    def add(self, project: Project) -> None:
        if project.parent is not self._project:
            raise RuntimeError("Project.parent does not match")
        if project.name in self._members:
            raise KeyError(f"project {self._project} already has a member {project.name!r}")
        self._members[project.name] = project

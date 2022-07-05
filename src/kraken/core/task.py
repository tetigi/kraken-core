""" This module provides the :class:`Task` class which represents a unit of work that is configurable through
:class:`Properties <Property>` that represent input/output parameters and are used to construct a dependency
graph."""

from __future__ import annotations

import abc
import dataclasses
import enum
from typing import TYPE_CHECKING, Any, ForwardRef, Iterable, TypeVar

from kraken.core.property import Object, Property

if TYPE_CHECKING:
    from kraken.core.project import Project

T = TypeVar("T")
Project = ForwardRef("Project")  # type: ignore  # noqa: F811  # Allow Task.project annotation to resolve


@dataclasses.dataclass
class TaskRelationship:
    """Represents a relationship to another task."""

    other_task: Task
    strict: bool
    before: bool


class TaskResult(enum.Enum):
    """Represents the possible results that a task can return from its execution."""

    FAILED = enum.auto()
    SUCCEEDED = enum.auto()
    SKIPPED = enum.auto()
    UP_TO_DATE = enum.auto()


class Task(Object):
    """A task is an isolated unit of work that is configured with properties. Every task has some common settings that
    are not treated as properties, such as it's :attr:`name`, :attr:`default` and :attr:`capture` flag. A task is a
    member of a :class:`Project` and can be uniquely identified with a path that is derived from its project and name.
    """

    name: str
    project: Project
    default: bool = False
    capture: bool = True

    def __init__(self, name: str, project: Project) -> None:
        super().__init__()
        self.name = name
        self.project = project

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path})"

    @property
    def path(self) -> str:
        """Returns the path of the task."""

        if self.project.parent is None:
            return f":{self.name}"
        else:
            return f"{self.project.path}:{self.name}"

    def get_relationships(self) -> Iterable[TaskRelationship]:
        """Iterates over the relationships to other tasks based on the property provenance."""

        for key in self.__schema__:
            property: Property[Any] = getattr(self, key)
            for supplier, _ in property.lineage():
                if isinstance(supplier, Property) and isinstance(supplier.owner, Task):
                    yield TaskRelationship(supplier.owner, True, False)

    def is_up_to_date(self) -> bool:
        """Gives the task a chance before it is executed to inform the build executor that it is up to date and does
        not need to be executed. Some tasks may be able to determine this quickly so they can implement this method to
        improve build performance and user information display."""

        return False

    def is_skippable(self) -> bool:
        """Gives the task a chance before it is executed to inform the build executor that the task can be skipped.
        This status is different from :meth:`is_up_to_date` but may lead to the same result, i.e. that the task is not
        executed."""

        return False

    def finalize(self) -> None:
        """This method is called by :meth:`BuildContext.finalize()`. It gives the task a chance update its
        configuration before the build process is executed."""

    @abc.abstractmethod
    def execute(self) -> TaskResult:
        ...

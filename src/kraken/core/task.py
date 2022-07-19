""" This module provides the :class:`Task` class which represents a unit of work that is configurable through
:class:`Properties <Property>` that represent input/output parameters and are used to construct a dependency
graph."""

from __future__ import annotations

import abc
import dataclasses
import enum
import logging
import sys
from typing import TYPE_CHECKING, Any, ForwardRef, Iterable, List, TypeVar

from kraken.core.property import Object, Property

if TYPE_CHECKING:
    from kraken.core.project import Project
else:
    if sys.version_info[:2] == (3, 9):
        # Type hint evaluation tries to fully resolve forward references to a type. In order to allow the property
        # evaluation happening in the Object base class for the Task class, we need to make sure the name "Project"
        # resolves to something valid at runtime.
        Project = ForwardRef("object")
    else:
        Project = ForwardRef("kraken.core.project.Project")  # noqa: F811,E501

T = TypeVar("T")
T_Task = TypeVar("T_Task", bound="Task")


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

    @staticmethod
    def from_exit_code(code: int) -> TaskResult:
        return TaskResult.SUCCEEDED if code == 0 else TaskResult.FAILED


class Task(Object, abc.ABC):
    """A task is an isolated unit of work that is configured with properties. Every task has some common settings that
    are not treated as properties, such as it's :attr:`name`, :attr:`default` and :attr:`capture` flag. A task is a
    member of a :class:`Project` and can be uniquely identified with a path that is derived from its project and name.
    """

    name: str
    project: Project
    default: bool = True
    capture: bool = False
    logger: logging.Logger

    def __init__(self, name: str, project: Project) -> None:
        super().__init__()
        self.name = name
        self.project = project
        self.logger = logging.getLogger(f"{self.path} [{type(self).__module__}.{type(self).__qualname__}]")

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
                if supplier is property:
                    continue
                if isinstance(supplier, Property) and isinstance(supplier.owner, Task) and supplier.owner is not self:
                    yield TaskRelationship(supplier.owner, True, False)

    def is_up_to_date(self) -> bool:
        """Gives the task a chance before it is executed to inform the build executor that it is up to date and does
        not need to be executed. Some tasks may be able to determine this quickly so they can implement this method to
        improve build performance and user information display.

        Raises:
            NotImplementedError: If the task does not support an is-up-to-date check.
        """

        raise NotImplementedError

    def is_skippable(self) -> bool:
        """Gives the task a chance before it is executed to inform the build executor that the task can be skipped.
        This status is different from :meth:`is_up_to_date` but may lead to the same result, i.e. that the task is not
        executed.

        Raises:
            NotImplementedError: If the task does not support an is-skippable check.
        """

        raise NotImplementedError

    def finalize(self) -> None:
        """This method is called by :meth:`Context.finalize()`. It gives the task a chance update its
        configuration before the build process is executed. The default implementation finalizes all non-output
        properties, preventing them to be further mutated."""

        for key in self.__schema__:
            prop: Property[Any] = getattr(self, key)
            if not self.__schema__[key].is_output:
                prop.finalize()

    @abc.abstractmethod
    def execute(self) -> TaskResult:
        raise NotImplementedError

    # Object

    def _warn_non_existent_properties(self, keys: set[str]) -> None:
        self.logger.warning("properties %s cannot be set because they don't exist (task %s)", keys, self.path)


class GroupTask(Task):
    """This task can be used to group tasks under a common name. Ultimately it is just another task that depends on
    the tasks in the group, forcing them to be executed when this task is targeted. Group tasks are not enabled
    by default."""

    tasks: List[Task]

    def __init__(self, name: str, project: Project) -> None:
        super().__init__(name, project)
        self.tasks = []
        self.default = False

    def add(self, tasks: str | Task | Iterable[str | Task]) -> None:
        """Add one or more tasks by name or task object to this group."""

        if isinstance(tasks, (str, Task)):
            tasks = [tasks]

        for task in tasks:
            if isinstance(task, str):
                self.tasks += [
                    t for t in self.project.context.resolve_tasks([task], self.project) if t not in self.tasks
                ]
            elif task not in self.tasks:
                self.tasks.append(task)

    def get_relationships(self) -> Iterable[TaskRelationship]:
        for task in self.tasks:
            yield TaskRelationship(task, True, False)
        yield from super().get_relationships()

    def is_up_to_date(self) -> bool:
        return True

    def execute(self) -> TaskResult:
        return TaskResult.UP_TO_DATE


class VoidTask(Task):
    """This task does nothing and can always be skipped."""

    def is_skippable(self) -> bool:
        return True

    def is_up_to_date(self) -> bool:
        return True

    def execute(self) -> TaskResult:
        return TaskResult.SKIPPED

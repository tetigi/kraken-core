""" This module provides the :class:`Task` class which represents a unit of work that is configurable through
:class:`Properties <Property>` that represent input/output parameters and are used to construct a dependency
graph."""

from __future__ import annotations

import abc
import dataclasses
import enum
from typing import TYPE_CHECKING, Any, ClassVar, ForwardRef, Generic, Iterable, TypeVar, cast

from kraken.core.property import Object, Property

if TYPE_CHECKING:
    from kraken.core.project import Project

T = TypeVar("T")
T_Task = TypeVar("T_Task", bound="Task")
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
                if supplier is property:
                    continue
                if isinstance(supplier, Property) and isinstance(supplier.owner, Task) and supplier.owner is not self:
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
        configuration before the build process is executed. The default implementation finalizes all non-output
        properties, preventing them to be further mutated."""

        for key in self.__schema__:
            prop: Property[Any] = getattr(self, key)
            if not self.__schema__[key].is_output:
                prop.finalize()

    @abc.abstractmethod
    def execute(self) -> TaskResult:
        ...


class task_factory(Generic[T_Task]):
    """Factory functor for task implementations."""

    class Auto:
        pass

    def __init__(
        self,
        task_type: type[T_Task],
        name: str | None | type[Auto] = Auto,
        default: bool = True,
        capture: bool = True,
    ) -> None:
        self._name = name
        self._default = default
        self._capture = capture
        self._task_type = task_type

    def __repr__(self) -> str:
        return f"task_factory({self._task_type.__name__})"

    def __call__(
        self,
        *,
        name: str | None = None,
        default: bool | None = None,
        project: Project | None = None,
        **kwds: Any,
    ) -> T_Task:

        if project is None:
            from kraken.api import project as _current_project

            project = _current_project

        if name is None:
            if self._name is None:
                raise TypeError(f"missing 'name' argument for {self}")
            if self._name is task_factory.Auto:
                name = self._get_task_name(project)
            else:
                name = cast(str, self._name)

        if default is None:
            default = self._default

        task = project.do(name, self._task_type, default, self._capture)
        task.update(**kwds)
        return task

    __counter: ClassVar[dict[Project, dict[str, int]]] = {}

    def _get_task_name(self, project: Project) -> str:
        """Generate a new task name."""

        project_counter = self.__counter.setdefault(project, {})
        next_value = project_counter.get(self._task_type.__name__, 0)
        project_counter[self._task_type.__name__] = next_value + 1
        return f"_{self._task_type.__name__}_{next_value}"

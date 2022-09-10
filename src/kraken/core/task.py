""" This module provides the :class:`Task` class which represents a unit of work that is configurable through
:class:`Properties <Property>` that represent input/output parameters and are used to construct a dependency
graph."""

from __future__ import annotations

import abc
import contextlib
import dataclasses
import enum
import logging
import shlex
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, ForwardRef, Generic, Iterable, List, Optional, Sequence, TypeVar, cast

from kraken.core.base import MetadataContainer
from kraken.core.property import Object, Property
from kraken.core.supplier import Empty, TaskSupplier

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
logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _Relationship(Generic[T]):
    """Represents a relationship to another task."""

    other_task: T
    strict: bool
    inverse: bool


TaskRelationship = _Relationship["Task"]


class TaskStatusType(enum.Enum):
    """Represents the possible statuses that a task can return from its execution."""

    PENDING = enum.auto()  #: The task is pending execution (only to be returned from :meth:`Task.prepare`).
    FAILED = enum.auto()  #: The task failed it's preparation or execution.
    INTERRUPTED = enum.auto()  #: The task was interrupted by the user.
    SUCCEEDED = enum.auto()  #: The task succeeded it's execution (only to be returned from :meth:`Task.execute`).
    STARTED = enum.auto()  #: The task started a background task that needs to be torn down later.
    SKIPPED = enum.auto()  #: The task was skipped (i.e. it is not applicable).
    UP_TO_DATE = enum.auto()  #: The task is up to date and did not run (or not run it's usual logic).

    def is_ok(self) -> bool:
        return not self.is_not_ok()

    def is_not_ok(self) -> bool:
        return self in (TaskStatusType.PENDING, TaskStatusType.FAILED, TaskStatusType.INTERRUPTED)

    def is_pending(self) -> bool:
        return self == TaskStatusType.PENDING

    def is_failed(self) -> bool:
        return self == TaskStatusType.FAILED

    def is_interrupted(self) -> bool:
        return self == TaskStatusType.INTERRUPTED

    def is_succeeded(self) -> bool:
        return self == TaskStatusType.SUCCEEDED

    def is_started(self) -> bool:
        return self == TaskStatusType.STARTED

    def is_skipped(self) -> bool:
        return self == TaskStatusType.SKIPPED

    def is_up_to_date(self) -> bool:
        return self == TaskStatusType.UP_TO_DATE


@dataclasses.dataclass
class TaskStatus:
    """Represents a task status with a message."""

    type: TaskStatusType
    message: str | None

    def is_ok(self) -> bool:
        return self.type.is_ok()

    def is_not_ok(self) -> bool:
        return self.type.is_not_ok()

    def is_pending(self) -> bool:
        return self.type == TaskStatusType.PENDING

    def is_failed(self) -> bool:
        return self.type == TaskStatusType.FAILED

    def is_interrupted(self) -> bool:
        return self.type == TaskStatusType.INTERRUPTED

    def is_succeeded(self) -> bool:
        return self.type == TaskStatusType.SUCCEEDED

    def is_started(self) -> bool:
        return self.type == TaskStatusType.STARTED

    def is_skipped(self) -> bool:
        return self.type == TaskStatusType.SKIPPED

    def is_up_to_date(self) -> bool:
        return self.type == TaskStatusType.UP_TO_DATE

    @staticmethod
    def pending(message: str | None = None) -> TaskStatus:
        return TaskStatus(TaskStatusType.PENDING, message)

    @staticmethod
    def failed(message: str | None = None) -> TaskStatus:
        return TaskStatus(TaskStatusType.FAILED, message)

    @staticmethod
    def interrupted(message: str | None = None) -> TaskStatus:
        return TaskStatus(TaskStatusType.INTERRUPTED, message)

    @staticmethod
    def succeeded(message: str | None = None) -> TaskStatus:
        return TaskStatus(TaskStatusType.SUCCEEDED, message)

    @staticmethod
    def started(message: str | None = None) -> TaskStatus:
        return TaskStatus(TaskStatusType.STARTED, message)

    @staticmethod
    def skipped(message: str | None = None) -> TaskStatus:
        return TaskStatus(TaskStatusType.SKIPPED, message)

    @staticmethod
    def up_to_date(message: str | None = None) -> TaskStatus:
        return TaskStatus(TaskStatusType.UP_TO_DATE, message)

    @staticmethod
    def from_exit_code(command: list[str] | None, code: int) -> TaskStatus:
        return TaskStatus(
            TaskStatusType.SUCCEEDED if code == 0 else TaskStatusType.FAILED,
            None
            if code == 0 or command is None
            else 'command "' + " ".join(map(shlex.quote, command)) + f'" returned exit code {code}',
        )


class Task(MetadataContainer, Object, abc.ABC):
    """A task is an isolated unit of work that is configured with properties. Every task has some common settings that
    are not treated as properties, such as it's :attr:`name`, :attr:`default` and :attr:`capture` flag. A task is a
    member of a :class:`Project` and can be uniquely identified with a path that is derived from its project and name.

    A task can have a relationship to any number of other tasks. Relationships are directional and the direction can
    be inverted. A strict relationship indicates that one task *must* run before the other, while a non-strict
    relationship only dictates the order of tasks if both were to be executed (and prevents the task from being
    executed in parallel).
    """

    name: str
    project: Project
    description: Optional[str] = None
    default: bool = False
    logger: logging.Logger

    def __init__(self, name: str, project: Project) -> None:
        MetadataContainer.__init__(self)
        Object.__init__(self)
        self._capture = False
        self.name = name
        self.project = project
        self.logger = logging.getLogger(f"{self.path} [{type(self).__module__}.{type(self).__qualname__}]")
        self.__relationships: list[_Relationship[str | Task]] = []

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path})"

    @property
    def capture(self) -> bool:
        warnings.warn(
            "The Task.capture attribute will be deprecated in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._capture

    @capture.setter
    def capture(self, value: bool) -> None:
        warnings.warn(
            "The Task.capture attribute will be deprecated in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._capture = value

    @property
    def path(self) -> str:
        """Returns the path of the task."""

        if self.project.parent is None:
            return f":{self.name}"
        else:
            return f"{self.project.path}:{self.name}"

    def add_relationship(
        self,
        task_or_selector: Task | Sequence[Task] | str,
        strict: bool = True,
        inverse: bool = False,
    ) -> None:
        """Add a relationship to this task that will be returned by :meth:`get_relationships`.

        :param task_or_selector: A task, list of tasks or a task selector (wich may expand to multiple tasks)
            to add as a relationship to this task. If a task selector string is specified, it will be evaluated
            lazily when :meth:`get_relationships` is called.
        :param strict: Whether the relationship is strict, i.e. informs a strong dependency in one or the other
            direction. If a relationship is not strict, it informs only order of execution and parallel
            exclusivity.
        :param inverse: Whether to invert the relationship.
        """

        if isinstance(task_or_selector, (Task, str)):
            self.__relationships.append(_Relationship(task_or_selector, strict, inverse))
        elif isinstance(task_or_selector, Sequence):
            for idx, task in enumerate(task_or_selector):
                if not isinstance(task, Task):
                    raise TypeError(
                        f"task_or_selector[{idx}] must be Task | Sequence[Task] | str, got "
                        f"{type(task_or_selector).__name__}"
                    )
            for task in task_or_selector:
                self.__relationships.append(_Relationship(task, strict, inverse))
        else:
            raise TypeError(
                f"task_or_selector argument must be Task | Sequence[Task] | str, got {type(task_or_selector).__name__}"
            )

    def get_relationships(self) -> Iterable[TaskRelationship]:
        """Iterates over the relationships to other tasks based on the property provenance."""

        # Derive dependencies through property lineage.
        for key in self.__schema__:
            property: Property[Any] = getattr(self, key)
            for supplier, _ in property.lineage():
                if supplier is property:
                    continue
                if isinstance(supplier, Property) and isinstance(supplier.owner, Task) and supplier.owner is not self:
                    yield TaskRelationship(supplier.owner, True, False)
                if isinstance(supplier, TaskSupplier):
                    yield TaskRelationship(supplier.get(), True, False)

        # Manually added relationships.
        for rel in self.__relationships:
            if isinstance(rel.other_task, str):
                try:
                    resolved_tasks = self.project.context.resolve_tasks([rel.other_task], relative_to=self.project)
                except ValueError as exc:
                    raise ValueError(f"in task {self.path}: {exc}")
                for task in resolved_tasks:
                    yield TaskRelationship(task, rel.strict, rel.inverse)
            else:
                assert isinstance(rel.other_task, Task)
                yield cast(TaskRelationship, rel)

    def get_description(self) -> str | None:
        """Return the task's description. The default implementation formats the :attr:`description` string with the
        task's properties. Any Path property will be converted to a relative string to assist the reader."""

        class _MappingProxy:
            def __getitem__(_, key: str) -> Any:
                if key not in type(self).__schema__:
                    return f"%({key})s"
                prop = getattr(self, key)
                try:
                    value = prop.get()
                except Empty:
                    return "<empty>"
                else:
                    if isinstance(value, Path):
                        try:
                            value = value.relative_to(Path.cwd())
                        except ValueError:
                            pass
                    return value

        if self.description:
            return self.description % _MappingProxy()
        return None

    def finalize(self) -> None:
        """This method is called by :meth:`Context.finalize()`. It gives the task a chance update its
        configuration before the build process is executed. The default implementation finalizes all non-output
        properties, preventing them to be further mutated."""

        for key in self.__schema__:
            prop: Property[Any] = getattr(self, key)
            if not self.__schema__[key].is_output:
                prop.finalize()

    def prepare(self) -> TaskStatus | None:
        """Called before a task is executed. This is called from the main process to check for example if the task
        is skippable or up to date. The implementation of this method should be quick to determine the task status,
        otherwise it should be done in :meth:`execute`.

        This method should not return :attr:`TaskStatusType.SUCCEEDED` or :attr:`TaskStatusType.FAILED`. If `None`
        is returned, it is assumed that the task is :attr:`TaskStatusType.PENDING`.
        """

        return TaskStatus.pending()

    @abc.abstractmethod
    def execute(self) -> TaskStatus | None:
        """Implements the behaviour of the task. The task can assume that all strict dependencies have been executed
        successfully. Output properties of dependency tasks that are only written by the task's execution are now
        accessible.

        This method should not return :attr:`TaskStatusType.PENDING`. If `None` is returned, it is assumed that the
        task is :attr:`TaskStatusType.SUCCEEDED`.
        """

        raise NotImplementedError

    def teardown(self) -> TaskStatus | None:
        """This method is called only if the task returns :attr:`TaskStatusType.STARTED` from :meth:`execute`. It is
        called if _all_ direct dependants of the task have been executed (whether successfully or not) or if no further
        task execution is queued."""

        return None

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
        """Add one or more tasks by name or task object to this group.

        This is different from adding a task via :meth:`add_relationship` because the task is instead stored in the
        :attr:`tasks` list which can be used to access the members of the task. Relationships for a group task can
        still be used to express relationships between groups or tasks and groups.

        Also note that :meth:`add_relationship` supports lazy evaluation of task selectors, whereas using this method
        to add a task to the group by a selector string requires that the task already exists.
        """

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

    def prepare(self) -> TaskStatus | None:
        return TaskStatus.skipped("is a GroupTask")

    def execute(self) -> TaskStatus | None:
        raise RuntimeError("GroupTask cannot be executed")


class VoidTask(Task):
    """This task does nothing and can always be skipped."""

    skip: Property[bool] = Property.default(True)
    message: Property[str] = Property.default("is a VoidTask")

    def prepare(self) -> TaskStatus | None:
        if self.skip.get():
            return TaskStatus.skipped(self.message.get())
        return TaskStatus.pending()

    def execute(self) -> TaskStatus | None:
        pass


class BackgroundTask(Task):
    """This base class represents a task that starts some process in the background that keeps running which is
    then terminated when all direct dependant tasks are completed and no work is left. A common use case for this
    type of task is to spawn sidecar processes which are relied on by other tasks to be available during their
    execution."""

    @abc.abstractmethod
    def start_background_task(self, exit_stack: contextlib.ExitStack) -> TaskStatus | None:
        """Start some task or process in the background. Use the *exit_stack* to ensure cleanup of your allocated
        resources in case of an unexpected error or when the background task is torn down. Returning not-None and
        not :attr:`TaskStatusType.STARTED`, or causing an exception will immediately close the exit stack."""

        raise NotImplementedError

    def __del__(self) -> None:
        try:
            self.__exit_stack
        except AttributeError:
            pass
        else:
            logger.warning(
                'BackgroundTask.teardown() did not get called on task "%s". This may cause some issues, such '
                "as an error during serialization or zombie processes.",
                self.path,
            )

    # Task

    def execute(self) -> TaskStatus | None:
        self.__exit_stack = contextlib.ExitStack()
        try:
            status = self.start_background_task(self.__exit_stack)
            if status is None:
                status = TaskStatus.started()
            elif not status.is_started():
                self.__exit_stack.close()
            return status
        except BaseException:
            self.__exit_stack.close()
            raise

    def teardown(self) -> None:
        self.__exit_stack.close()
        del self.__exit_stack

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Iterator, Optional, Sequence, TypeVar

from kraken.core.base import Currentable, MetadataContainer
from kraken.core.executor import GraphExecutorObserver

if TYPE_CHECKING:
    from kraken.core.executor import GraphExecutor
    from kraken.core.graph import TaskGraph
    from kraken.core.loader import ProjectLoader
    from kraken.core.project import Project
    from kraken.core.task import Task

T = TypeVar("T")


class Context(MetadataContainer, Currentable["Context"]):
    """This class is the single instance where all components of a build process come together."""

    def __init__(
        self,
        build_directory: Path,
        project_loader: ProjectLoader | None = None,
        executor: GraphExecutor | None = None,
        observer: GraphExecutorObserver | None = None,
    ) -> None:
        """
        :param build_directory: The directory in which all files generated durin the build should be stored.
        :param project_loader: The object to use to load projects from a directory. If not specified, a
            :class:`PythonScriptProjectLoader` will be used.
        :param executor: The executor to use when the graph is executed.
        :param observer: The executro observer to use when the graph is executed.
        """

        from kraken.core.executor.default import (
            DefaultGraphExecutor,
            DefaultPrintingExecutorObserver,
            DefaultTaskExecutor,
        )
        from kraken.core.loader import PythonScriptProjectLoader

        super().__init__()
        self.build_directory = build_directory
        self.project_loader = project_loader or PythonScriptProjectLoader()
        self.executor = executor or DefaultGraphExecutor(DefaultTaskExecutor())
        self.observer = observer or DefaultPrintingExecutorObserver()
        self._finalized: bool = False
        self._root_project: Optional[Project] = None

    @property
    def root_project(self) -> Project:
        assert self._root_project is not None, "Context.root_project is not set"
        return self._root_project

    @root_project.setter
    def root_project(self, project: Project) -> None:
        assert self._root_project is None, "Context.root_project is already set"
        self._root_project = project

    def load_project(
        self,
        directory: Path,
        parent: Project | None = None,
    ) -> Project:
        """Loads a project from a file or directory.

        Args:
            directory: The directory to load the project from.
            parent: The parent project. If no parent is specified, then the :attr:`root_project`
                must not have been initialized yet and the loaded project will be initialize it.
                If the root project is initialized but no parent is specified, an error will be
                raised.
        """

        from kraken.core.project import Project

        project = Project(directory.name, directory, parent, self)
        with self.as_current():
            if self._root_project is None:
                self._root_project = project
            self.project_loader.load_project(project)
        return project

    def iter_projects(self) -> Iterator[Project]:
        """Iterates over all projects in the context."""

        def _recurse(project: Project) -> Iterator[Project]:
            yield project
            for child_project in project.children().values():
                yield from _recurse(child_project)

        yield from _recurse(self.root_project)

    def resolve_tasks(self, targets: list[str] | None, relative_to: Project | None = None) -> list[Task]:
        """Resolve the given project or task references in *targets* relative to the specified project, or by
        default relative to the root project. A target is a colon-separated string that behaves similar to a
        filesystem path to address projects and tasks in the hierarchy. The root project is represented with a
        single colon and cannot be referenced by its name.

        A target that is just a task name will match all tasks of that name."""

        relative_to = relative_to or self.root_project

        if targets is None:
            # Return all default tasks.
            return [task for project in self.iter_projects() for task in project.tasks().values() if task.default]

        tasks: list[Task] = []
        count = 0
        target: str

        def _check_matched() -> None:
            nonlocal count
            if count == len(tasks):
                raise ValueError(f"no tasks matched selector {target!r}")
            count = len(tasks)

        for target in targets:
            optional = target.endswith("?")
            if optional:
                target = target[:-1]
            count = len(tasks)

            if ":" not in target:
                # Select all targets with a name matching the specified target.
                tasks.extend(
                    task for project in self.iter_projects() for task in project.tasks().values() if task.name == target
                )
                if not optional:
                    _check_matched()
                continue

            # Resolve as many components in the project hierarchy as possible.
            project = relative_to
            parts = target.split(":")
            if parts[0] == "":
                project = self.root_project
                parts.pop(0)
            while parts:
                project_children = project.children()
                if parts[0] in project_children.values():
                    project = project_children[parts.pop(0)]
                else:
                    break

            project_tasks = project.tasks()
            if not parts or parts == [""]:
                # The project was selected, add all default tasks.
                tasks.extend(task for task in project_tasks.values() if task.default)
            elif len(parts) == 1:
                # A specific target is selected.
                if parts[0] not in project_tasks:
                    if optional:
                        continue
                    raise ValueError(f"task {target!r} does not exist")
                tasks.append(project_tasks[parts[0]])
            else:
                # Some project in the path does not exist.
                if optional:
                    continue
                raise ValueError(f"project {':'.join(target.split(':')[:-1])} does not exist")

            _check_matched()

        return tasks

    def finalize(self) -> None:
        """Call :meth:`Task.finalize()` on all tasks. This should be called before a graph is created."""

        self._finalized = True
        for project in self.iter_projects():
            for task in project.tasks().values():
                task.finalize()

    def get_build_graph(self, targets: Sequence[str | Task] | None) -> TaskGraph:
        """Returns the :class:`TaskGraph` that contains either all default tasks or the tasks specified with
        the *targets* argument.

        :param targets: A list of targets to resolve and to build the graph from.
        :raise ValueError: If not tasks were selected.
        """

        from kraken.core.graph import TaskGraph

        if targets is None:
            tasks = self.resolve_tasks(None)
        else:
            tasks = self.resolve_tasks([t for t in targets if isinstance(t, str)]) + [
                t for t in targets if not isinstance(t, str)
            ]

        if not tasks:
            raise ValueError("no tasks selected")

        graph = TaskGraph(self)
        graph.set_targets(tasks)

        assert graph, "TaskGraph cannot be empty"
        return graph

    def execute(self, tasks: list[str | Task] | TaskGraph | None = None) -> None:
        """Execute all default tasks or the tasks specified by *targets* using the default executor.
        If :meth:`finalize` was not called already it will be called by this function before the build
        graph is created, unless a build graph is passed in the first place.

        :param tasks: The list of tasks to execute, or the build graph. If none specified, all default
            tasks will be executed.
        :raise BuildError: If any task fails to execute.
        """

        from kraken.core.graph import TaskGraph

        if isinstance(tasks, TaskGraph):
            assert self._finalized, "no, no, this is all wrong. you need to finalize the context first"
            graph = tasks
        else:
            if not self._finalized:
                self.finalize()
            graph = self.get_build_graph(tasks)

        self.executor.execute_graph(graph, self.observer)

        if not graph.is_complete():
            failed_tasks = list(graph.tasks(failed=True))
            if len(failed_tasks) == 1:
                message = f'task "{failed_tasks[0].path}" failed'
            else:
                message = "tasks " + ", ".join(f'"{task.path}"' for task in failed_tasks) + " failed"
            raise BuildError(message)


class BuildError(Exception):
    def __init__(self, failed_tasks: Iterable[str]) -> None:
        self.failed_tasks = set(failed_tasks)

    def __repr__(self) -> str:
        if len(self.failed_tasks) == 1:
            return f'task "{next(iter(self.failed_tasks))}" failed'
        else:
            return "tasks " + ", ".join(f'"{task}"' for task in sorted(self.failed_tasks)) + " failed"

from __future__ import annotations

import dataclasses
from typing import Iterable, Iterator, List, cast

from networkx import DiGraph, restricted_view  # type: ignore[import]

from kraken.core.task import GroupTask, Task, TaskStatus
from kraken.core.utils import not_none


@dataclasses.dataclass
class _Node:
    task: Task
    required: bool


@dataclasses.dataclass
class _Edge:
    strict: bool


class TaskGraph:
    """The task graph is a materialization of the relationships of tasks into a acyclic directed graph.

    The graph is built recursively from one or more tasks of which the relationships are discovered. The set of tasks
    that is passed initially to the graph are considered the "required" tasks and can be later retrieved via the
    :meth:`tasks` by passing `required_only=True`.

    The initial task set from which the graph is built and their dependencies represent the subgraph of interest that
    is usually executed, ignoring all tasks that are not a member of this subgraph. Any such superfluous tasks can be
    removed from the graph using the :meth:`trim` method.

    When a task was executed, the executing client must be set the status of the task using the :meth:`set_status`
    method. This will virtually remove the task from the graph for subsequent queries on the :meth:`execution_order`
    or the :meth:`ready` tasks.

    If a task status is not OK (i.e. :meth:`TaskStatus.is_failed` returns `True`), that task will block it's dependant
    tasks from appearing in the result of :meth:`ready`, which can eventually lead the graph into a "locked" state
    where work is pending but cannot continue because the depending work has failed.
    """

    def __init__(self, tasks: Iterable[Task] = ()) -> None:
        """Create a new build graph from the given task list."""

        # Nodes have the form {'data': _Node} and edges have the form {'data': _Edge}.
        self._digraph = DiGraph()
        self._results: dict[str, TaskStatus] = {}
        self._completed_nodes: set[str] = set()

        self._add_tasks(tasks)

    def __bool__(self) -> bool:
        return len(self._digraph.nodes) > 0

    def __len__(self) -> int:
        return len(self._digraph.nodes)

    # Low level internal API

    def _get_node(self, task_path: str) -> _Node | None:
        data = self._digraph.nodes.get(task_path)
        if data is None:
            return None
        return cast(_Node, data["data"])

    def _add_node(self, task: Task, required: bool) -> None:
        """Internal. Ensures that a node for the given task exists. If *required* is True, it will override the
        existing status."""

        node = self._get_node(task.path) or _Node(task, required)
        node.required = node.required or required
        self._digraph.add_node(task.path, data=node)

    def _get_edge(self, task_a: str, task_b: str) -> _Edge | None:
        data = self._digraph.edges.get((task_a, task_b))
        if data is None:
            return None
        return cast(_Edge, data["data"])

    def _add_edge(self, task_a: str, task_b: str, strict: bool) -> None:
        """Internal. Introduces an edge between two tasks."""

        edge = self._get_edge(task_a, task_b) or _Edge(strict)
        edge.strict = edge.strict or strict
        self._digraph.add_edge(task_a, task_b, data=edge)

    # High level internal API

    def _add_tasks(self, tasks: Iterable[Task], required: bool = True) -> None:
        """Internal. Extends the internal directed graph by the given tasks.

        Args:
            tasks: The tasks to add to the graph.
            required: Whether the tasks added via this function should be marked as required (i.e. they
                will never be ignored by the :meth:`trimmed` method).
        """

        for task in tasks:

            # If a group task is required, we instead mark all tasks that this group depends on as required.
            dependencies_required = isinstance(task, GroupTask)

            self._add_node(task, not dependencies_required)

            # Make sure we have all dependencies tracked in the graph.
            self._add_tasks(
                (rel.other_task for rel in task.get_relationships() if not rel.inverse),
                dependencies_required,
            )

            for rel in task.get_relationships():
                if rel.inverse:
                    # We may not have added this task to the graph yet.
                    self._add_node(rel.other_task, False)

                a, b = (task, rel.other_task) if rel.inverse else (rel.other_task, task)
                self._add_edge(a.path, b.path, rel.strict)

    def _get_restricted_view(self) -> DiGraph:
        """Returns a restricted view of the internal graph that hides all tasks that have a non-failure status."""

        return restricted_view(self._digraph, self._completed_nodes, set())

    # Public API

    def get_predecessors(self, task: Task) -> List[Task]:
        return [not_none(self._get_node(task_path)).task for task_path in self._digraph.predecessors(task.path)]

    def get_successors(self, task: Task) -> List[Task]:
        return [not_none(self._get_node(task_path)).task for task_path in self._digraph.successors(task.path)]

    def trim(self) -> TaskGraph:
        """Removes all tasks from the graph that are not initially required and only connected to any other
        task with an optional dependency."""

        # Find all tasks that are not initially required and only have dependants with an optional dependency.
        weakly_connected_tasks = set()
        for task_path in self._digraph.nodes:
            if not_none(self._get_node(task_path)).required:
                continue
            if not any(
                not_none(self._get_edge(task_path, dependant_task_path)).strict
                for dependant_task_path in self._digraph.successors(task_path)
            ):
                weakly_connected_tasks.add(task_path)

        # Remove the subgraphs that are weakly connected, but keep all required tasks and their subgraphs.
        def _remove_subgraph(task_path: str) -> None:
            if not_none(self._get_node(task_path)).required:
                return
            if task_path not in self._digraph.nodes:
                return
            for successor in list(self._digraph.predecessors(task_path)):
                _remove_subgraph(successor)
            self._digraph.remove_node(task_path)

        for task_path in weakly_connected_tasks:
            if task_path in self._digraph.nodes:
                _remove_subgraph(task_path)

        return self

    def tasks(self, required_only: bool = False, failed: bool = False) -> Iterator[Task]:
        """Returns all tasks in an arbitrary order.

        :param required_only: Return only tasks from the initial task set that the graph was built from.
        :param failed: Return only failed tasks."""

        tasks = (not_none(self._get_node(task_path)).task for task_path in self._digraph.nodes)
        if required_only:
            tasks = (t for t in tasks if not_none(self._get_node(t.path)).required)
        if failed:
            tasks = (t for t in tasks if t.path in self._results and self._results[t.path].is_failed())
        return tasks

    def execution_order(self) -> Iterable[Task]:
        """Returns all tasks in the order they need to be executed."""

        from networkx.algorithms import topological_sort  # type: ignore[import]

        graph = self._get_restricted_view()
        order = topological_sort(graph)
        return (not_none(self._get_node(task_path)).task for task_path in order)

    def set_status(self, task: Task, status: TaskStatus) -> None:
        """Sets the status of a task, marking it as executed."""

        if task.path in self._results:
            raise RuntimeError(f"already have a status for task {task.path!r}")
        self._results[task.path] = status
        if status.is_ok():
            self._completed_nodes.add(task.path)

    def get_status(self, task: Task) -> TaskStatus | None:
        """Return the status of a task."""

        return self._results.get(task.path)

    def is_complete(self) -> bool:
        """Returns `True` if, an only if, all tasks in the graph have a non-failure result."""

        return len(self._completed_nodes) == len(self._digraph.nodes)

    def ready(self) -> Iterable[Task]:
        """Returns all tasks that are ready to be executed. This can be used to constantly query the graph for new
        available tasks as the status of tasks in the graph is updated with :meth:`set_status`. An empty list is
        returned if no tasks are ready. At this point, if no tasks are currently running, :meth:`is_complete` can be
        used to check if the entire task graph was executed successfully."""

        graph = self._get_restricted_view()
        root_set = (node for node in graph.nodes if graph.in_degree(node) == 0 and node not in self._results)
        return (not_none(self._get_node(task_path)).task for task_path in root_set)

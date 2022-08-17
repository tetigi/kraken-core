from __future__ import annotations

import dataclasses
import logging
from typing import Iterable, Iterator, List, cast

from kraken.core._vendor.networkx import DiGraph, restricted_view
from kraken.core.context import Context
from kraken.core.executor import Graph
from kraken.core.task import GroupTask, Task, TaskStatus
from kraken.core.util.helpers import not_none

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _Edge:
    strict: bool


class TaskGraph(Graph):
    """The task graph represents the entirety of a Kraken context's tasks as a directed acyclic graph data structure.

    Internally, it stores three versions of the graph: A full graph, a target subgraph and a ready subgraph. The
    subgraphs are implemented as views on the full graph.

    1. The **full graph** stores the entire build graph of all tasks in the context.
    2. The **target graph** stores only the relevant subgraph with the target tasks as leaf nodes set with
       :meth:`set_targets`.
    3. The **ready graph** excludes all successfully completed tasks from the target graph. This is used to find
       the next set of ready tasks with :meth:`ready`. This graph is not kept in memory but created automatically
       when needed.
    """

    def __init__(self, context: Context) -> None:
        """Create a new build graph from the given task list."""

        self._context = context

        # Nodes have the form {'data': _Node} and edges have the form {'data': _Edge}.
        self._full_graph = DiGraph()

        # Keep track of task execution results.
        self._results: dict[str, TaskStatus] = {}

        # Keep track of the tasks that returned TaskStatus.STARTED. That means the task is a background task, and
        # if the TaskGraph is deserialized from a state file to continue the build, background tasks need to be
        # reset so they start again if another task requires them.
        self._background_tasks: set[str] = set()

        # Here we store all tasks that make up the "initial set", i.e. the ultimate target tasks that are to be
        # executed. We derive the subgraph to execute from this initial set in the :meth:`trim` method by deactivating
        # tasks in :attr:`_inactive_nodes`.
        self._target_tasks: set[str] = set()

        # All deactivated tasks are stored here.
        self._inactive_tasks: set[str] = set()

        # All tasks that have a successful status are stored here.
        self._completed_tasks: set[str] = set()

        # Make sure the build graph is populated with the entire build graph.
        for project in context.iter_projects():
            for task in project.tasks().values():
                if task.path not in self._full_graph.nodes:
                    self._add_task(task)

        # The restricted view is the subgraph that excludes all inactive tasks.
        self._target_graph: DiGraph

        self._update_target_graph()

    def __bool__(self) -> bool:
        return len(self._target_graph.nodes) > 0

    def __len__(self) -> int:
        return len(self._target_graph.nodes)

    # Low level internal API

    def _get_task(self, task_path: str) -> Task | None:
        data = self._full_graph.nodes.get(task_path)
        if data is None:
            return None
        return cast(Task, data["data"])

    def _add_task(self, task: Task) -> None:
        self._full_graph.add_node(task.path, data=task)
        for rel in task.get_relationships():
            if rel.other_task.path not in self._full_graph.nodes:
                self._add_task(rel.other_task)
            a, b = (task, rel.other_task) if rel.inverse else (rel.other_task, task)
            self._add_edge(a.path, b.path, rel.strict)

    def _get_edge(self, task_a: str, task_b: str) -> _Edge | None:
        data = self._full_graph.edges.get((task_a, task_b))
        if data is None:
            return None
        return cast(_Edge, data["data"])

    def _add_edge(self, task_a: str, task_b: str, strict: bool) -> None:
        edge = self._get_edge(task_a, task_b) or _Edge(strict)
        edge.strict = edge.strict or strict
        self._full_graph.add_edge(task_a, task_b, data=edge)

    # High level internal API

    def _update_inactive_tasks(self) -> None:
        """Internal. Updates the inactive tasks that are not required to be executed for the target tasks."""

        def _recurse_task(task_path: str, visited: set[str]) -> None:
            visited.add(task_path)
            for pred in self._full_graph.predecessors(task_path):
                if not_none(self._get_edge(pred, task_path)).strict:
                    _recurse_task(pred, visited)

        active_tasks: set[str] = set()
        for task_path in self._target_tasks:
            _recurse_task(task_path, active_tasks)

        self._inactive_tasks = set(self._full_graph.nodes) - active_tasks
        self._update_target_graph()

    def _update_target_graph(self) -> None:
        """Updates the target graph."""
        self._target_graph = restricted_view(self._full_graph, self._inactive_tasks, set())  # type: ignore[no-untyped-call]  # noqa: 501

    def _get_ready_graph(self) -> DiGraph:
        """Updates the ready graph."""
        return restricted_view(self._target_graph, self._completed_tasks, set())  # type: ignore[no-untyped-call]

    # Public API

    @property
    def context(self) -> Context:
        return self._context

    def get_predecessors(self, task: Task, ignore_groups: bool = False) -> List[Task]:
        """Returns the predecessors of the task in the original full build graph."""

        result = []
        for task in (not_none(self._get_task(task_path)) for task_path in self._full_graph.predecessors(task.path)):
            if ignore_groups and isinstance(task, GroupTask):
                result += task.tasks
            else:
                result.append(task)
        return result

    def get_edge(self, pred: Task, succ: Task) -> _Edge:
        return not_none(self._get_edge(pred.path, succ.path), f"edge does not exist ({pred.path} --> {succ.path})")

    def set_targets(self, tasks: Iterable[Task] | None) -> None:
        """Mark the tasks given with *tasks* as required. All immediate dependencies that are background tasks and
        have already run will be reset to ensure they run again.

        :param tasks: The leaf targets of the target subgraph. If set to None, the entire task graph will be used."""

        self._target_tasks.clear()
        if tasks is not None:
            for task in tasks:
                self._target_tasks.add(task.path)
        self._update_inactive_tasks()
        self._update_target_graph()

        # Reset background tasks.
        reset_tasks: set[str] = set()
        for task in self.tasks(pending=True):
            for pred in self.get_predecessors(task, ignore_groups=True):
                if pred.path in self._background_tasks:
                    self._background_tasks.discard(pred.path)
                    self._completed_tasks.discard(pred.path)
                    self._results.pop(pred.path, None)
                    reset_tasks.add(pred.path)
        if reset_tasks:
            logger.info("Reset the status of %d background task(s): %s", len(reset_tasks), " ".join(reset_tasks))

    def get_status(self, task: Task) -> TaskStatus | None:
        """Return the status of a task."""

        return self._results.get(task.path)

    def update_statuses_from(self, other_graph: TaskGraph) -> None:
        """Merge the results from the *other_graph* into this graph. This is used when multiple separate build states
        are merged into one graph. If the same task has a result in both graphs, the failed result will supersede the
        successful one."""

        for task in self.tasks(all=True):
            status_a = self._results.get(task.path)
            status_b = other_graph._results.get(task.path)
            if status_a is not None and status_b is not None and status_a.type != status_b.type:
                resolved_status: TaskStatus | None = status_a if status_a.is_not_ok() else status_b
            else:
                resolved_status = status_a or status_b
            if resolved_status is not None:
                self.set_status(task, resolved_status, _force=True)

    def discard_statuses(self) -> None:
        """Discard any results from the graph, allowing you to effectively restart the execution of tasks."""

        self._completed_tasks.clear()
        self._results.clear()
        self._update_target_graph()

    def tasks(
        self,
        targets_only: bool = False,
        pending: bool = False,
        failed: bool = False,
        all: bool = False,
    ) -> Iterator[Task]:
        """Returns the tasks in the graph in arbitrary order. By default, only tasks part of the target subgraph
        are returned, but this can be changed with *all*.

        :param targets_only: Return only target tasks (i.e. the leaf nodes of the target subgraph).
        :param pending: Return only pending tasks.
        :param failed: Return only failed tasks.
        :param all: Return from all tasks, not just from the tasks that need to be executed."""

        tasks = (not_none(self._get_task(task_path)) for task_path in self._full_graph)
        if not all:
            tasks = (task for task in tasks if task.path not in self._inactive_tasks)
        if targets_only:
            tasks = (t for t in tasks if t.path in self._target_tasks)
        if pending:
            tasks = (t for t in tasks if t.path not in self._results)
        if failed:
            tasks = (t for t in tasks if t.path in self._results and self._results[t.path].is_failed())
        return tasks

    def execution_order(self, all: bool = False) -> Iterable[Task]:
        """Returns all tasks in the order they need to be executed.

        :param all: Return the execution order of all tasks, not just from the target subgraph."""

        from kraken.core._vendor.networkx.algorithms import topological_sort

        order = topological_sort(self._full_graph if all else self._get_ready_graph())  # type: ignore[no-untyped-call]
        return (not_none(self._get_task(task_path)) for task_path in order)

    # Graph

    def ready(self) -> list[Task]:
        """Returns all tasks that are ready to be executed. This can be used to constantly query the graph for new
        available tasks as the status of tasks in the graph is updated with :meth:`set_status`. An empty list is
        returned if no tasks are ready. At this point, if no tasks are currently running, :meth:`is_complete` can be
        used to check if the entire task graph was executed successfully."""

        ready_graph = self._get_ready_graph()
        root_set = (
            node for node in ready_graph.nodes if ready_graph.in_degree(node) == 0 and node not in self._results
        )
        return [not_none(self._get_task(task_path)) for task_path in root_set]

    def get_successors(self, task: Task, ignore_groups: bool = True) -> list[Task]:
        """Returns the successors of the task in the original full build graph.

        Never returns group tasks."""

        result = []
        for task in (not_none(self._get_task(task_path)) for task_path in self._full_graph.successors(task.path)):
            if ignore_groups and isinstance(task, GroupTask):
                result += task.tasks
            else:
                result.append(task)
        return result

    def set_status(self, task: Task, status: TaskStatus, *, _force: bool = False) -> None:
        """Sets the status of a task, marking it as executed."""

        if not _force and (task.path in self._results and not self._results[task.path].is_started()):
            raise RuntimeError(f"already have a status for task {task.path!r}")
        self._results[task.path] = status
        if status.is_started():
            self._background_tasks.add(task.path)
        if status.is_ok():
            self._completed_tasks.add(task.path)

    def is_complete(self) -> bool:
        """Returns `True` if, an only if, all tasks in the target subgraph have a non-failure result."""

        return set(self._target_graph.nodes).issubset(self._completed_tasks)

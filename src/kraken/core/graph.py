from __future__ import annotations

import dataclasses
import logging
from typing import Iterable, Iterator, List, Sequence, cast

from networkx import DiGraph, restricted_view, transitive_reduction

from kraken.core.context import Context
from kraken.core.executor import Graph
from kraken.core.task import GroupTask, Task, TaskStatus
from kraken.core.util.helpers import not_none

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _Edge:
    strict: bool
    implicit: bool


class TaskGraph(Graph):
    """The task graph represents a Kraken context's tasks as a directed acyclic graph data structure.

    Before a task graph is passed to an executor, it is usually trimmed to contain only the tasks that are
    needed for the successful and complete execution of the desired set of "goal tasks"."""

    def __init__(self, context: Context, populate: bool = True, parent: TaskGraph | None = None) -> None:
        """Create a new build graph from the given task list.

        :param context: The context that the graph belongs to.
        :param populate: If enabled, the task graph will be immediately populated with the tasks in the context.
            The graph can also be later populated with the :meth:`populate` method.
        """

        self._parent = parent
        self._context = context

        # Nodes have the form {'data': _Node} and edges have the form {'data': _Edge}.
        self._digraph = DiGraph()

        # Keep track of task execution results.
        self._results: dict[str, TaskStatus] = {}

        # All tasks that have a successful status are stored here.
        self._completed_tasks: set[str] = set()

        # Keep track of the tasks that returned TaskStatus.STARTED. That means the task is a background task, and
        # if the TaskGraph is deserialized from a state file to continue the build, background tasks need to be
        # reset so they start again if another task requires them.
        self._background_tasks: set[str] = set()

        if populate:
            self.populate()

    def __bool__(self) -> bool:
        return len(self._digraph.nodes) > 0

    def __len__(self) -> int:
        return len(self._digraph.nodes)

    # Low level internal API

    def _get_task(self, task_path: str) -> Task | None:
        data = self._digraph.nodes.get(task_path)
        if data is None:
            return None
        return cast(Task, data["data"])

    def _add_task(self, task: Task) -> None:
        self._digraph.add_node(task.path, data=task)
        for rel in task.get_relationships():
            if rel.other_task.path not in self._digraph.nodes:
                self._add_task(rel.other_task)
            a, b = (task, rel.other_task) if rel.inverse else (rel.other_task, task)
            self._add_edge(a.path, b.path, rel.strict, False)

            # When a group depends on another group, we implicitly create make each member of the downstream group
            # depend on the upstream group.
            if isinstance(task, GroupTask) and isinstance(rel.other_task, GroupTask):
                upstream, downstream = (task, rel.other_task) if rel.inverse else (rel.other_task, task)
                for member in downstream.tasks:
                    self._add_edge(upstream.path, member.path, rel.strict, True)

    def _get_edge(self, task_a: str, task_b: str) -> _Edge | None:
        data = self._digraph.edges.get((task_a, task_b)) or self._digraph.edges.get((task_a, task_b))
        if data is None:
            return None
        return cast(_Edge, data["data"])

    def _add_edge(self, task_a: str, task_b: str, strict: bool, implicit: bool, graph: DiGraph | None = None) -> None:
        graph = graph or self._digraph
        edge = self._get_edge(task_a, task_b) or _Edge(strict, implicit)
        edge.strict = edge.strict or strict
        edge.implicit = edge.implicit and implicit
        graph.add_edge(task_a, task_b, data=edge)

    # High level internal API

    def _get_required_tasks(self, goals: Iterable[Task]) -> set[str]:
        """Internal. Return the set of tasks that are required transitively from the goal tasks."""

        def _recurse_task(task_path: str, visited: set[str]) -> None:
            visited.add(task_path)
            for pred in self._digraph.predecessors(task_path):
                if not_none(self._get_edge(pred, task_path)).strict:
                    _recurse_task(pred, visited)

        active_tasks: set[str] = set()
        for task in goals:
            _recurse_task(task.path, active_tasks)

        return active_tasks

    def _remove_nodes_keep_transitive_edges(self, nodes: Iterable[str]) -> None:
        """Internal. Remove nodes from the graph, but ensure that transitive dependencies are kept in tact."""

        for task_path in nodes:
            for in_task_path in self._digraph.predecessors(task_path):
                in_edge = not_none(self._get_edge(in_task_path, task_path))
                for out_task_path in self._digraph.successors(task_path):
                    out_edge = not_none(self._get_edge(task_path, out_task_path))
                    self._add_edge(
                        in_task_path,
                        out_task_path,
                        strict=in_edge.strict or out_edge.strict,
                        implicit=in_edge.implicit and out_edge.implicit,
                    )
            self._digraph.remove_node(task_path)

    def _get_ready_graph(self) -> DiGraph:
        """Updates the ready graph."""
        return restricted_view(self._digraph, self._completed_tasks, set())

    # Public API

    @property
    def context(self) -> Context:
        return self._context

    @property
    def parent(self) -> TaskGraph | None:
        return self._parent

    @property
    def root(self) -> TaskGraph:
        if self._parent:
            return self._parent.root
        return self

    def get_edge(self, pred: Task, succ: Task) -> _Edge:
        return not_none(self._get_edge(pred.path, succ.path), f"edge does not exist ({pred.path} --> {succ.path})")

    def get_predecessors(self, task: Task, ignore_groups: bool = False) -> List[Task]:
        """Returns the predecessors of the task in the original full build graph."""

        result = []
        for task in (not_none(self._get_task(task_path)) for task_path in self._digraph.predecessors(task.path)):
            if ignore_groups and isinstance(task, GroupTask):
                result += task.tasks
            else:
                result.append(task)
        return result

    def get_status(self, task: Task) -> TaskStatus | None:
        """Return the status of a task."""

        return self._results.get(task.path)

    def populate(self, goals: Iterable[Task] | None = None) -> None:
        """Populate the graph with the tasks from the context. This need only be called if the graph was
        not initially populated in the constructor."""

        if goals is None:
            for project in self.context.iter_projects():
                for task in project.tasks().values():
                    if task.path not in self._digraph.nodes:
                        self._add_task(task)
        else:
            for task in goals:
                if task.path not in self._digraph.nodes:
                    self._add_task(task)

    def trim(self, goals: Sequence[Task]) -> TaskGraph:
        """Returns a copy of the graph that is trimmed to execute only *goals* and their strict dependencies."""

        graph = TaskGraph(self.context, populate=False, parent=self)
        graph.populate(goals)

        unrequired_tasks = set(graph._digraph.nodes) - graph._get_required_tasks(goals)
        graph._remove_nodes_keep_transitive_edges(unrequired_tasks)

        return graph

    def reduce(self, keep_explicit: bool = False) -> TaskGraph:
        """Return a copy of the task graph that has been transitively reduced.

        :param keep_explicit: Keep non-implicit edges in tact."""

        digraph = self._digraph
        reduced_graph = transitive_reduction(digraph)
        reduced_graph.add_nodes_from(digraph.nodes(data=True))
        reduced_graph.add_edges_from(
            (u, v, digraph.edges[u, v])
            for u, v in digraph.edges
            if (keep_explicit and not digraph.edges[u, v]["data"].implicit) or (u, v) in reduced_graph.edges
        )

        graph = TaskGraph(self.context, populate=False, parent=self)
        graph._digraph = reduced_graph
        graph.results_from(self)

        return graph

    def results_from(self, other: TaskGraph) -> None:
        """Merge the results from the *other* graph into this graph. Only takes the results of tasks that are
        known to the graph. If the same task has a result in both graphs, and one task result is not successful,
        the not successful result is preferred."""

        for task in self.tasks():
            status_a = self._results.get(task.path)
            status_b = other._results.get(task.path)
            if status_a is not None and status_b is not None and status_a.type != status_b.type:
                resolved_status: TaskStatus | None = status_a if status_a.is_not_ok() else status_b
            else:
                resolved_status = status_a or status_b
            if resolved_status is not None:
                # NOTE: This will already take care of updating :attr:`_background_tasks`.
                self.set_status(task, resolved_status, _force=True)

    def resume(self) -> None:
        """Reset the result of all background tasks that are required by any pending tasks. This needs to be
        called when a build graph is resumed in a secondary execution to ensure that background tasks are active
        for the tasks that require them."""

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

    def restart(self) -> None:
        """Discard the results of all tasks."""

        self._results.clear()
        self._completed_tasks.clear()
        self._background_tasks.clear()

    def tasks(
        self,
        goals: bool = False,
        pending: bool = False,
        failed: bool = False,
    ) -> Iterator[Task]:
        """Returns the tasks in the graph in arbitrary order.

        :param goals: Return only goal tasks (i.e. leaf nodes).
        :param pending: Return only pending tasks.
        :param failed: Return only failed tasks.
        :param all: Return from all tasks, not just from the tasks that need to be executed."""

        tasks = (not_none(self._get_task(task_path)) for task_path in self._digraph)
        if goals:
            tasks = (t for t in tasks if self._digraph.out_degree(t.path) == 0)
        if pending:
            tasks = (t for t in tasks if t.path not in self._results)
        if failed:
            tasks = (t for t in tasks if t.path in self._results and self._results[t.path].is_failed())
        return tasks

    def execution_order(self, all: bool = False) -> Iterable[Task]:
        """Returns all tasks in the order they need to be executed.

        :param all: Return the execution order of all tasks, not just from the target subgraph."""

        from networkx.algorithms import topological_sort

        order = topological_sort(self._digraph if all else self._get_ready_graph())
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
        for task in (not_none(self._get_task(task_path)) for task_path in self._digraph.successors(task.path)):
            if ignore_groups and isinstance(task, GroupTask):
                result += task.tasks
            else:
                result.append(task)
        return result

    def get_task(self, task_path: str) -> Task:
        return not_none(self._get_task(task_path))

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

        return set(self._digraph.nodes).issubset(self._completed_tasks)

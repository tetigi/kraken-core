from __future__ import annotations

import dataclasses
from typing import Iterable, List, cast

from networkx import DiGraph  # type: ignore[import]

from kraken.core.task import GroupTask, Task
from kraken.core.utils import not_none


@dataclasses.dataclass
class _Node:
    task: Task
    required: bool


@dataclasses.dataclass
class _Edge:
    strict: bool


class TaskGraph:
    """Represents the build graph."""

    def __init__(self, tasks: Iterable[Task] = ()) -> None:
        """Create a new build graph from the given task list."""

        # Nodes have the form {'data': _Node} and edges have the form {'data': _Edge}.
        self._digraph = DiGraph()
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
                (rel.other_task for rel in task.get_relationships() if not rel.before),
                dependencies_required,
            )

            for rel in task.get_relationships():
                if rel.before:
                    # We may not have added this task to the graph yet.
                    self._add_node(rel.other_task, False)

                a, b = (task, rel.other_task) if rel.before else (rel.other_task, task)
                self._add_edge(a.path, b.path, rel.strict)

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

    def tasks(self, required_only: bool = False) -> Iterable[Task]:
        """Returns all tasks in an arbitrary order."""

        tasks = (not_none(self._get_node(task_path)).task for task_path in self._digraph.nodes)
        if required_only:
            tasks = (t for t in tasks if not_none(self._get_node(t.path)).required)
        return tasks

    def execution_order(self) -> Iterable[Task]:
        from networkx.algorithms import topological_sort  # type: ignore[import]

        order = topological_sort(self._digraph)
        return (not_none(self._get_node(task_path)).task for task_path in order)

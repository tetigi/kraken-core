from kraken.core.graph import TaskGraph
from kraken.core.project import Project
from kraken.core.task import TaskStatus, VoidTask


def test__TaskGraph__trim_tasks(kraken_project: Project) -> None:
    """Tests if :meth:`TaskGraph.trim` works as expected with group tasks."""

    task_a = kraken_project.do("a", VoidTask)
    task_b = kraken_project.do("b", VoidTask)

    group = kraken_project.group("g")
    group.add([task_a, task_b])

    graph = TaskGraph([group])
    assert list(graph.tasks()) == [group, task_a, task_b]

    graph.trim()
    assert list(graph.tasks()) == [task_a, task_b]


def test__TaskGraph__ready_on_successful_completion(kraken_project: Project) -> None:
    """Tests if :meth:`TaskGraph.ready` and :meth:`TaskGraph.is_complete` work as expected.

    ```
    A -----> B -----> C
    ```
    """

    task_a = kraken_project.do("a", VoidTask)
    task_b = kraken_project.do("b", VoidTask)
    task_c = kraken_project.do("c", VoidTask)

    task_c.add_relationship(task_b)
    task_b.add_relationship(task_a)

    graph = TaskGraph([task_c])
    assert list(graph.tasks()) == [task_c, task_b, task_a]
    assert list(graph.execution_order()) == [task_a, task_b, task_c]

    # Complete tasks one by one.
    remainder = [task_a, task_b, task_c]
    while remainder:
        assert list(graph.execution_order()) == remainder
        task = remainder.pop(0)
        assert not graph.is_complete()
        assert list(graph.ready()) == [task]
        graph.set_status(task, TaskStatus.succeeded())

    assert graph.is_complete()
    assert list(graph.ready()) == []


def test__TaskGraph__ready_on_failure(kraken_project: Project) -> None:
    """This test tests if the task delivers the correct ready tasks if a task in the graph fails.

    ```
    A        B
    |        |
    v        v
    C -----> D
    ```

    If A succeeds but B fails, C would still be executable, but D stays dormant.
    """

    task_a = kraken_project.do("a", VoidTask)
    task_b = kraken_project.do("b", VoidTask)
    task_c = kraken_project.do("c", VoidTask)
    task_d = kraken_project.do("d", VoidTask)

    task_d.add_relationship(task_b)
    task_d.add_relationship(task_c)
    task_c.add_relationship(task_a)

    graph = TaskGraph([task_d])
    assert list(graph.tasks()) == [task_d, task_b, task_c, task_a]
    assert list(graph.execution_order()) == [task_b, task_a, task_c, task_d]
    assert list(graph.ready()) == [task_b, task_a]

    graph.set_status(task_b, TaskStatus.failed())
    assert list(graph.ready()) == [task_a]

    graph.set_status(task_a, TaskStatus.succeeded())
    assert list(graph.ready()) == [task_c]

    # D cannot continue because B has failed.
    graph.set_status(task_c, TaskStatus.succeeded())
    assert list(graph.ready()) == []
    assert not graph.is_complete()

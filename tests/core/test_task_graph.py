import pytest

from kraken.core.graph import TaskGraph
from kraken.core.project import Project
from kraken.core.task import TaskStatus, VoidTask


def test__TaskGraph__populate(kraken_project: Project) -> None:
    task_a = kraken_project.do("a", VoidTask, group="g")
    task_b = kraken_project.do("b", VoidTask, group="g")
    group = kraken_project.group("g")

    graph = TaskGraph(kraken_project.context, False)
    graph.populate([group])

    assert set(graph.tasks()) == {group, task_a, task_b}
    assert set(graph.tasks(goals=True)) == {group}


def test__TaskGraph__trim(kraken_project: Project) -> None:
    task_a = kraken_project.do("a", VoidTask, group="g")
    task_b = kraken_project.do("b", VoidTask, group="g")
    group = kraken_project.group("g")

    graph = TaskGraph(kraken_project.context).trim([group])

    assert set(graph.tasks()) == {group, task_a, task_b}
    assert set(graph.tasks(goals=True)) == {group}

    # Trimming should have the same result as a fresh populate.
    fresh_graph = TaskGraph(kraken_project.context, populate=False)
    fresh_graph.populate([group])
    assert fresh_graph._digraph.nodes == graph._digraph.nodes
    assert fresh_graph._digraph.edges == graph._digraph.edges


def test__TaskGraph__trim_with_nested_groups(kraken_project: Project) -> None:
    task_a = kraken_project.do("a", VoidTask, group="g1")
    task_b = kraken_project.do("b", VoidTask, group="g2")
    group_1 = kraken_project.group("g1")
    group_2 = kraken_project.group("g2")
    group_1.add(group_2)

    graph = TaskGraph(kraken_project.context).trim([group_1, group_2])

    assert set(graph.tasks()) == {group_2, group_1, task_a, task_b}
    assert set(graph.tasks(goals=True)) == {group_1}

    # Trimming should have the same result as a fresh populate.
    fresh_graph = TaskGraph(kraken_project.context, populate=False)
    fresh_graph.populate([group_1])
    assert fresh_graph._digraph.nodes == graph._digraph.nodes
    assert fresh_graph._digraph.edges == graph._digraph.edges


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

    graph = TaskGraph(kraken_project.context).trim([task_c])

    assert set(graph.tasks()) == {task_c, task_b, task_a}
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

    graph = TaskGraph(kraken_project.context).trim([task_d])
    assert set(graph.tasks()) == {task_d, task_b, task_c, task_a}
    assert list(graph.execution_order()) in ([task_a, task_b, task_c, task_d], [task_b, task_a, task_c, task_d])
    assert set(graph.ready()) == {task_a, task_b}

    # After B fails we can still run A.
    graph.set_status(task_b, TaskStatus.failed())
    assert list(graph.ready()) == [task_a]

    # After A is successful we can still run C.
    graph.set_status(task_a, TaskStatus.succeeded())
    assert list(graph.ready()) == [task_c]

    # D cannot continue because B has failed.
    graph.set_status(task_c, TaskStatus.succeeded())
    assert list(graph.ready()) == []
    assert not graph.is_complete()


def test__TaskGraph__ready_2(kraken_project: Project) -> None:
    """
    ```
    pythonBuild -----> pythonPublish -----> publish (group)
     \\-----> build (group)
    ```
    """

    pythonBuild = kraken_project.do("pythonBuild", VoidTask, group="build")
    pythonPublish = kraken_project.do("pythonPublish", VoidTask, group="publish")
    pythonPublish.add_relationship(pythonBuild)

    publish = kraken_project.group("publish")
    graph = TaskGraph(kraken_project.context).trim([publish])
    assert list(graph.ready()) == [pythonBuild]


def test__TaskGraph__correct_execution_order_on_optional_intermediate_task(kraken_project: Project) -> None:
    """Test that the TaskGraph produces the correct order in a scenario where two tasks that need to be
    executed have another that does not need to be executed in between.

    ```
    pythonInstall --------------------------> pytest
    \\---> jtd.python ===> gen ---> (X) build - - ->/
    ```

    The expected order here is that the `pytest` task can only run after `gen`. It is important to note that
    the `pytest` task only depends optionally on the `build` task, otherwise of course running `pytest` would
    require that `build` is executed as well.

    Legend:

    * `- ->`: optional dependency
    * `--->`: strict dependency
    * `===>`: member of group
    """

    python_install = kraken_project.do("pythonInstall", VoidTask)
    jtd_python = kraken_project.do("jtd.python", VoidTask, group="gen")
    gen = kraken_project.group("gen")
    build = kraken_project.group("build")
    pytest = kraken_project.do("pytest", VoidTask)

    pytest.add_relationship(python_install)
    pytest.add_relationship(build, strict=False)
    build.add_relationship(gen)
    jtd_python.add_relationship(python_install)

    graph = TaskGraph(kraken_project.context)

    assert list(graph.trim([pytest, gen]).execution_order()) == [python_install, jtd_python, gen, pytest]

    assert list(graph.trim([pytest, build]).execution_order()) == [python_install, jtd_python, gen, build, pytest]


@pytest.mark.parametrize("inverse", [False, True])
def test__TaskGraph__test_inverse_group_relationship(kraken_project: Project, inverse: bool) -> None:
    """Tests that the dependency propagation between members of task groups works as expected.

    Consider two groups A and B. When B depends on A, the task graph automatically expands that dependency
    to the members of B such that each depend on the members of A. This fact is stored on the edge using
    the "implicit" marker (i.e. the relationship between the tasks was not explicit using direct task
    relationships).

    :param inverse: Whether the relationship between the groups should be expressed using an inverse relationship.
        `A -> B` should yield the same result as `B <- A`.
    """

    from kraken.core.graph import _Edge

    a = kraken_project.group("a")
    b = kraken_project.group("b")
    ta1 = kraken_project.do("ta1", VoidTask, group=a)
    ta2 = kraken_project.do("ta2", VoidTask, group=a)
    tb1 = kraken_project.do("tb1", VoidTask, group=b)

    if inverse:
        a.add_relationship(b, inverse=True)
    else:
        b.add_relationship(a)

    graph = TaskGraph(kraken_project.context)
    assert graph.get_edge(ta1, a) == _Edge(True, False)
    assert graph.get_edge(ta2, a) == _Edge(True, False)
    assert graph.get_edge(tb1, b) == _Edge(True, False)
    assert graph.get_edge(a, b) == _Edge(True, False)

    # Implicit propagated edges.
    assert graph.get_edge(a, tb1) == _Edge(True, True)

    assert list(graph.trim([b]).execution_order()) == [ta1, ta2, a, tb1, b]

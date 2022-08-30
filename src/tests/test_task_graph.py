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

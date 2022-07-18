from kraken.core.graph import TaskGraph
from kraken.core.project import Project
from kraken.core.task import VoidTask


def test_task_graph_with_group(kraken_project: Project) -> None:
    task_a = kraken_project.do("a", VoidTask)
    task_b = kraken_project.do("b", VoidTask)
    group = kraken_project.group("g")
    group.add([task_a, task_b])
    graph = TaskGraph([group])
    assert list(graph.tasks()) == [group, task_a, task_b]
    graph.trim()
    assert list(graph.tasks()) == [task_a, task_b]

from kraken.core.action import Action
from kraken.core.project import Project
from kraken.core.task import Task


def test_task_action_property_separation(project: Project) -> None:
    """This test ensures that the :attr:`Task.action` property object is a separate instance from the one
    that should be created automatically when a Task object is instantiated."""

    task1 = Task[Action]("foo", project, None)
    assert Task.action is not task1.action  # type: ignore[misc]
    task2 = Task[Action]("foo", project, None)
    assert Task.action is not task2.action  # type: ignore[misc]
    assert task1.action is not task2.action

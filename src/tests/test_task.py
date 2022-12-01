from pytest import raises

from kraken.core.project import Project
from kraken.core.property import Property
from kraken.core.task import Task, TaskRelationship


def test__Task__get_relationships_lineage_through_properties(kraken_project: Project) -> None:
    class MyTask(Task):
        prop: Property[str]

        def execute(self) -> None:
            raise NotImplementedError

    t1 = kraken_project.do("t1", MyTask)
    t1.prop.set("Hello, World")

    t2 = kraken_project.do("t2", MyTask)
    t2.prop.set(t1.prop)

    assert list(t2.get_relationships()) == [TaskRelationship(t1, True, False)]


def test__Task__new_style_type_hints_can_be_runtime_introspected_in_all_Python_versions(
    kraken_project: Project,
) -> None:
    """This is a feature of `typeapi ^1.3.0`."""

    class MyTask(Task):
        a: Property["list[str]"]  # type: ignore[misc]  # Mypy will complain in older Python versions even if this is not a runtime error  # noqa: E501
        b: Property["int | str"]

        def execute(self) -> None:
            raise NotImplementedError

    t1 = kraken_project.do("t1", MyTask)
    t1.a.set(["a", "b"])
    t1.b.set(42)
    t1.b.set("foo")

    with raises(TypeError) as excinfo:
        t1.a.set(("a", "b"))  # type: ignore[arg-type]
    assert str(excinfo.value) == "Property(MyTask(:t1).a): expected list, got tuple"
    with raises(TypeError) as excinfo:
        t1.b.set(42.0)  # type: ignore[arg-type]
    assert str(excinfo.value) == "Property(MyTask(:t1).b): expected int, got float\nexpected str, got float"

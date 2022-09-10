from dataclasses import dataclass

from kraken.core.project import Project
from kraken.core.property import Property
from kraken.core.task import Task, VoidTask


@dataclass
class MyDescriptor:
    name: str


def test__Project__resolve_outputs__can_find_dataclass_in_metadata(kraken_project: Project) -> None:
    kraken_project.do("carrier", VoidTask).metadata.append(MyDescriptor("foobar"))
    assert kraken_project.resolve_outputs(":carrier", MyDescriptor) == [MyDescriptor("foobar")]


def test__Project__resolve_outputs__can_find_dataclass_in_properties(kraken_project: Project) -> None:
    class MyTask(Task):
        out_prop: Property[MyDescriptor] = Property.output()

        def execute(self) -> None:
            ...

    kraken_project.do("carrier", MyTask, out_prop=MyDescriptor("foobar"))
    assert kraken_project.resolve_outputs(":carrier", MyDescriptor) == [MyDescriptor("foobar")]


def test__Project__resolve_outputs__can_not_find_input_property(kraken_project: Project) -> None:
    class MyTask(Task):
        out_prop: Property[MyDescriptor]

        def execute(self) -> None:
            ...

    kraken_project.do("carrier", MyTask, out_prop=MyDescriptor("foobar"))
    assert kraken_project.resolve_outputs(":carrier", MyDescriptor) == []


def test__Project__resolve_outputs_supplier(kraken_project: Project) -> None:
    class MyTask(Task):
        out_prop: Property[MyDescriptor] = Property.output()

        def execute(self) -> None:
            ...

    kraken_project.do("carrier", MyTask, out_prop=MyDescriptor("foobar"))
    assert kraken_project.resolve_outputs_supplier(":carrier", MyDescriptor).get() == [MyDescriptor("foobar")]

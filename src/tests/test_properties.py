from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Union

from kraken.core.property import Object, Property


def test__Property_value_adapter_order_is_semantically_revelant() -> None:
    """Tests that a `str | Path` and `Path | str` property behave differently."""

    prop1: Property[Union[str, Path]] = Property(Object(), "prop1", (str, Path))
    prop1.set("foo/bar")
    assert prop1.get() == "foo/bar"

    prop2: Property[Union[Path, str]] = Property(Object(), "prop2", (Path, str))
    prop2.set("foo/bar")
    assert prop2.get() == Path("foo/bar")

    prop2.setmap(lambda s: Path(str(s).upper()))
    assert prop2.get() == Path("FOO/BAR")


def test__Property_default() -> None:
    """Tests that property defaults work as expected."""

    a_value = ["abc"]

    class MyObj(Object):
        a: Property[List[str]] = Property.config(default=a_value)
        b: Property[int] = Property.config(default_factory=lambda: 42)
        c: Property[str]

    obj = MyObj()
    assert obj.a.get() == a_value
    assert obj.a.get() is not a_value  # Copied
    assert obj.b.get() == 42
    assert obj.c.is_empty()


def test__Property_default_factory_with_subclass() -> None:
    """Tests that property default factory works with a subclass (a known previous semantic failure case)."""

    class MyObj(Object):
        b: Property[Dict[str, str]] = Property.default_factory(dict)

    class SubObj(MyObj):
        pass

    obj = MyObj()
    assert obj.b.get() == {}

    subobj = SubObj()
    assert subobj.b.get() == {}

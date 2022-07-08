from __future__ import annotations

from pathlib import Path

from kraken.core.property import Object, Property


def test__Property_value_adapter_order_is_semantically_revelant() -> None:
    """Tests that a `str | Path` and `Path | str` property behave differently."""

    prop1: Property[str | Path] = Property(Object(), "prop1", (str, Path))
    prop1.set("foo/bar")
    assert prop1.get() == "foo/bar"

    prop2: Property[Path | str] = Property(Object(), "prop2", (Path, str))
    prop2.set("foo/bar")
    assert prop2.get() == Path("foo/bar")

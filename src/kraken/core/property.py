from __future__ import annotations

import weakref
from typing import Any, Callable, Generic, TypeVar, cast

from kraken.core.utils import NotSet, not_none

# import typeapi


T = TypeVar("T")
U = TypeVar("U")


class Property(Generic[T]):
    def __init__(self, owner: Any | None = None, name: str | None = None, value: T | NotSet = NotSet.Value) -> None:
        self._owner = None if owner is None else weakref.ref(owner)
        self.name = name
        self.value = value
        self._on_set: list[Callable[[T], Any]] = []

    def __bool__(self) -> bool:
        return self.value is not NotSet.Value

    def __repr__(self) -> str:
        if self._owner is None:
            return f"Property(unbound {self.name!r})"
        else:
            return f"Property({self._owner()!r}.{self.name!r})"

    @property
    def owner(self) -> Any | None:
        return None if self._owner is None else not_none(self._owner())

    def get(self) -> T:
        if self.value is NotSet:
            raise ValueError(f"{self!r} is not set")
        return cast(T, self.value)

    def get_or(self, fallback: U) -> T | U:
        if self.value is NotSet:
            return fallback
        return cast(T, self.value)

    def set(self, value: T) -> None:
        self.value = value
        for callback in self._on_set:
            callback(value)

    def clear(self) -> None:
        self.value = NotSet.Value

    def on_set(self, callback: Callable[[T], Any]) -> None:
        self._on_set.append(callback)


class HasProperties:
    """Base class for classes that declare properties as annotations."""

    def __init__(self) -> None:
        for key, value in vars(self).items():
            if isinstance(value, Property):
                print("@@ init", key)
                setattr(self, key, Property(self, key, value.get_or(NotSet.Value)))
        # TODO (@NiklasRosenstein): Have typeapi evaluate if TYPE_CHECKING blocks.
        # for key, value in typeapi.get_annotations(type(self)).items():
        for key, value in type(self).__annotations__.items():
            # if isinstance(value, str):
            #     continue  # We do not support initializing annotations as strings
            # hint = typeapi.of(value)
            # if isinstance(hint, typeapi.Type) and hint.type == Property:
            if isinstance(value, str) and "Property[" in value:
                setattr(self, key, Property(self, key))

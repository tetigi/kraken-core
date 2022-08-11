from __future__ import annotations

import contextlib
import importlib
import sys
from typing import Iterable, Iterator, TypeVar, overload

T = TypeVar("T")


@overload
def import_class(fqn: str) -> type:
    ...


@overload
def import_class(fqn: str, base_type: type[T]) -> type[T]:
    ...


def import_class(fqn: str, base_type: type[T] | None = None) -> type[T]:
    mod_name, cls_name = fqn.rpartition(".")[::2]
    module = importlib.import_module(mod_name)
    cls = getattr(module, cls_name)
    if not isinstance(cls, type):
        raise TypeError(f"expected type object at {fqn!r}, got {type(cls).__name__}")
    if base_type is not None and not issubclass(cls, base_type):
        raise TypeError(f"expected subclass of {base_type} at {fqn!r}, got {cls}")
    return cls


@contextlib.contextmanager
def append_to_sys_path(path: Iterable[str]) -> Iterator[None]:
    """Temporarily append to `sys.path`."""

    prev_path = sys.path[:]
    try:
        sys.path += path
        yield
    finally:
        sys.path[:] = prev_path

from __future__ import annotations

import enum
from typing import Iterable, TypeVar

T = TypeVar("T")


def flatten(it: Iterable[Iterable[T]]) -> Iterable[T]:
    for item in it:
        yield from item


def not_none(v: T | None) -> T:
    if v is None:
        raise RuntimeError("expected not-None")
    return v


class NotSet(enum.Enum):
    Value = 1

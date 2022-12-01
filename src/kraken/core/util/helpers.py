from __future__ import annotations

from typing import Iterable, TypeVar

from nr.stream import NotSet  # For backwards compatibility with kraken-core<=0.10.13

__all__ = [
    "flatten",
    "not_none",
    "NotSet",
]

T = TypeVar("T")


def flatten(it: Iterable[Iterable[T]]) -> Iterable[T]:
    for item in it:
        yield from item


def not_none(v: T | None, message: str = "expected not-None") -> T:
    if v is None:
        raise RuntimeError(message)
    return v

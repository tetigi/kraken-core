from typing import Iterable, TypeVar

T = TypeVar("T")


def flatten(it: Iterable[Iterable[T]]) -> Iterable[T]:
    for item in it:
        yield from item

from __future__ import annotations

from typing import Dict, Iterable, Iterator, Mapping, TypeVar, cast

K = TypeVar("K")
V = TypeVar("V")


class FrozenDict(Mapping[K, V]):
    """A hashable, immutable dictionary."""

    def __init__(self, *item: Mapping[K, V] | Iterable[tuple[K, V]], **kwargs: V) -> None:
        assert len(item) <= 1, "expected 0 or 1 positional argument"
        self._data = dict(item[0]) if item else {}
        self._data.update(cast(Dict[K, V], kwargs))
        self._hash = hash(tuple(self._data.items()))

    def __repr__(self) -> str:
        return f"FrozenDict({self._data})"

    def __getitem__(self, __k: K) -> V:
        return self._data[__k]

    def __iter__(self) -> Iterator[K]:
        return iter(self._data.keys())

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        return self._hash

from __future__ import annotations

from typing_extensions import Protocol


class SupportsLen(Protocol):
    def __len__(self) -> int:
        ...


def pluralize(word: str, count: int | SupportsLen) -> str:
    if not isinstance(count, int):
        count = len(count)
    return word if count == 1 else f"{word}s"

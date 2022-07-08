from __future__ import annotations

import contextlib
import enum
import os
import tempfile
from pathlib import Path
from typing import IO, AnyStr, BinaryIO, ContextManager, Iterable, Iterator, TextIO, TypeVar, overload

from typing_extensions import Literal

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


@overload
def atomic_file_swap(
    path: str | Path,
    mode: Literal["w"],
    always_revert: bool = ...,
) -> ContextManager[TextIO]:
    ...


@overload
def atomic_file_swap(
    path: str | Path,
    mode: Literal["wb"],
    always_revert: bool = ...,
) -> ContextManager[BinaryIO]:
    ...


@contextlib.contextmanager  # type: ignore
def atomic_file_swap(
    path: str | Path,
    mode: Literal["w", "wb"],
    always_revert: bool = False,
) -> Iterator[IO[AnyStr]]:
    """Performs an atomic write to a file while temporarily moving the original file to a different random location.

    Args:
        path: The path to replace.
        mode: The open mode for the file (text or binary).
        always_revert: If enabled, swap the old file back into place even if the with context has no errors.
    """

    path = Path(path)

    with contextlib.ExitStack() as exit_stack:
        if path.is_file():
            old = exit_stack.enter_context(
                tempfile.NamedTemporaryFile(
                    mode,
                    prefix=path.stem + "~",
                    suffix="~" + path.suffix,
                    dir=path.parent,
                )
            )
            old.close()
            os.rename(path, old.name)

            def _revert() -> None:
                assert isinstance(path, Path)
                if path.is_file():
                    path.unlink()
                os.rename(old.name, path)

        else:

            def _revert() -> None:
                assert isinstance(path, Path)
                if path.is_file():
                    path.unlink()

        try:
            with path.open(mode) as new:
                yield new
        except BaseException:
            _revert()
            raise
        else:
            if always_revert:
                _revert()
            else:
                os.remove(old.name)

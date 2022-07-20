from __future__ import annotations

import contextlib
import enum
import importlib
import os
import shutil
import sys
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
    create_dirs: bool = ...,
) -> ContextManager[TextIO]:
    ...


@overload
def atomic_file_swap(
    path: str | Path,
    mode: Literal["wb"],
    always_revert: bool = ...,
    create_dirs: bool = ...,
) -> ContextManager[BinaryIO]:
    ...


@contextlib.contextmanager  # type: ignore
def atomic_file_swap(
    path: str | Path,
    mode: Literal["w", "wb"],
    always_revert: bool = False,
    create_dirs: bool = False,
) -> Iterator[IO[AnyStr]]:
    """Performs an atomic write to a file while temporarily moving the original file to a different random location.

    Args:
        path: The path to replace.
        mode: The open mode for the file (text or binary).
        always_revert: If enabled, swap the old file back into place even if the with context has no errors.
        create_dirs: If the file does not exist, and neither do its parent directories, create the directories.
            The directory will be removed if the operation is reverted.
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
        else:
            old = None

        def _revert() -> None:
            assert isinstance(path, Path)
            if path.is_file():
                path.unlink()
            if old is not None:
                os.rename(old.name, path)

        if not path.parent.is_dir() and create_dirs:
            path.parent.mkdir(exist_ok=True)
            _old_revert = _revert

            def _revert() -> None:
                assert isinstance(path, Path)
                try:
                    shutil.rmtree(path.parent)
                finally:
                    _old_revert()

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
                if old is not None:
                    os.remove(old.name)


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


def get_terminal_width(default: int = 80) -> int:
    """Returns the terminal width through :func:`os.get_terminal_size`, falling back to the `COLUMNS`
    environment variable. If neither is available, return *default*."""

    try:
        terminal_width = os.get_terminal_size().columns
    except OSError:
        try:
            terminal_width = int(os.getenv("COLUMNS", ""))
        except ValueError:
            terminal_width = default
    return terminal_width


def is_relative_to(apath: Path, bpath: Path) -> bool:
    """Checks if *apath* is a path relative to *bpath*."""

    if sys.version_info[:2] < (3, 9):
        try:
            apath.relative_to(bpath)
            return True
        except ValueError:
            return False
    else:
        return apath.is_relative_to(bpath)

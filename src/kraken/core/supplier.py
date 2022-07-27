""" This module provides provides the :class:`Supplier` interface which is used to represent values that can be
calculated lazily and track provenance of such computations. """

from __future__ import annotations

import abc
from typing import Any, Callable, Generic, Iterable, Sequence, TypeVar

from kraken.core.utils import NotSet

T = TypeVar("T")
U = TypeVar("U")


class Empty(Exception):
    """Raised when a supplier cannot provide a value."""

    def __init__(self, supplier: Supplier[Any], message: str | None = None) -> None:
        self.supplier = supplier
        self.message = message

    def __str__(self) -> str:
        if self.message:
            return f"{self.message} ({self.supplier})"
        else:
            return str(self.supplier)


class Supplier(Generic[T], abc.ABC):
    """Base class for value suppliers."""

    @abc.abstractmethod
    def derived_from(self) -> Iterable[Supplier[Any]]:
        """Return an iterable that yields all suppliers that this supplier is derived from."""

    @abc.abstractmethod
    def get(self) -> T:
        """Return the value of the supplier. Depending on the implemenmtation, this may defer to other suppliers."""

    def get_or(self, fallback: U) -> T | U:
        """Return the value of the supplier, or the *fallback* value if the supplier is empty."""
        try:
            return self.get()
        except Empty:
            return fallback

    def get_or_raise(self, get_exception: Callable[[], Exception]) -> T:
        """Return the value of the supplier, or raise the exception provided by *get_exception* if empty."""
        try:
            return self.get()
        except Empty:
            raise get_exception()

    def is_empty(self) -> bool:
        """Returns `True` if the supplier is empty."""
        try:
            self.get()
        except Empty:
            return True
        else:
            return False

    def is_filled(self) -> bool:
        """Returns `True` if the supplier is not empty."""
        return not self.is_empty()

    def is_void(self) -> bool:
        return False

    def map(self, func: Callable[[T], U]) -> Supplier[U]:
        """Maps *func* over the value in the supplier."""

        return _SupplierMap(func, self)

    def once(self) -> Supplier[T]:
        """Cache the value forever once :attr:`get` is called."""

        return _SupplierOnce(self)

    def lineage(self) -> Iterable[tuple[Supplier[Any], list[Supplier[Any]]]]:
        """Iterates over all suppliers in the lineage.

        Yields:
            A supplier and the suppliers it is derived from.
        """

        stack: list[Supplier[Any]] = [self]
        while stack:
            current = stack.pop(0)
            derived_from = list(current.derived_from())
            yield current, derived_from
            stack += derived_from

    @staticmethod
    def of(value: T, derived_from: Sequence[Supplier[Any]] = ()) -> Supplier[T]:
        return _SupplierOf(value, derived_from)

    @staticmethod
    def of_callable(func: Callable[[], T], derived_from: Sequence[Supplier[Any]] = ()) -> Supplier[T]:
        return _SupplierOfCallable(func, derived_from)

    @staticmethod
    def void(from_exc: Exception | None = None, derived_from: Sequence[Supplier[Any]] = ()) -> Supplier[T]:
        """Returns a supplier that always raises :class:`Empty`."""

        return _SupplierVoid(from_exc, derived_from)


class _SupplierMap(Supplier[U], Generic[T, U]):
    def __init__(self, func: Callable[[T], U], value: Supplier[T]) -> None:
        self._func = func
        self._value = value

    def derived_from(self) -> Iterable[Supplier[Any]]:
        yield self._value

    def get(self) -> U:
        try:
            return self._func(self._value.get())
        except Empty:
            raise Empty(self)


class _SupplierOnce(Supplier[T]):
    _value: T | NotSet = NotSet.Value
    _empty: Empty | None = None

    def __init__(self, delegate: Supplier[T]) -> None:
        self._delegate = delegate

    def derived_from(self) -> Iterable[Supplier[Any]]:
        yield self._delegate

    def get(self) -> T:
        if self._empty is not None:
            raise Empty(self) from self._empty
        if self._value is NotSet.Value:
            try:
                self._value = self._delegate.get()
            except Empty as exc:
                self._empty = exc
                raise Empty(self) from exc
        return self._value


class _SupplierOfCallable(Supplier[T]):
    def __init__(self, func: Callable[[], T], derived_from: Sequence[Supplier[Any]]) -> None:
        self._func = func
        self._derived_from = derived_from

    def derived_from(self) -> Iterable[Supplier[Any]]:
        return self._derived_from

    def get(self) -> T:
        return self._func()


class _SupplierOf(Supplier[T]):
    def __init__(self, value: T, derived_from: Sequence[Supplier[Any]]) -> None:
        self._value = value
        self._derived_from = derived_from

    def derived_from(self) -> Iterable[Supplier[Any]]:
        return self._derived_from

    def get(self) -> T:
        return self._value


class _SupplierVoid(Supplier[T]):
    def __init__(self, from_exc: Exception | None, derived_from: Sequence[Supplier[Any]]) -> None:
        self._from_exc = from_exc
        self._derived_from = derived_from

    def derived_from(self) -> Iterable[Supplier[Any]]:
        return self._derived_from

    def get(self) -> T:
        raise Empty(self) from self._from_exc

    def is_void(self) -> bool:
        return True

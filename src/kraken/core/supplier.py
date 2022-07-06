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

    def __init__(self, supplier: Supplier[Any]) -> None:
        self.supplier = supplier


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

        this = self

        class SupplierMap(Supplier[U]):
            def derived_from(self) -> Iterable[Supplier[Any]]:
                yield this

            def get(self) -> U:
                try:
                    return func(this.get())
                except Empty:
                    raise Empty(self)

        return SupplierMap()

    def once(self) -> Supplier[T]:
        """Cache the value forever once :attr:`get` is called."""

        this = self

        class SupplierOnce(Supplier[T]):
            _value: T | NotSet = NotSet.Value
            _empty: Empty | None = None

            def derived_from(self) -> Iterable[Supplier[Any]]:
                yield this

            def get(self) -> T:
                if self._empty is not None:
                    raise Empty(self) from self._empty
                if self._value is NotSet.Value:
                    try:
                        self._value = this.get()
                    except Empty as exc:
                        self._empty = exc
                        raise Empty(self) from exc
                return self._value

        return SupplierOnce()

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
        class SupplierOf(Supplier[T]):
            def derived_from(self) -> Iterable[Supplier[Any]]:
                return derived_from

            def get(self) -> T:
                return value

        return SupplierOf()

    @staticmethod
    def of_callable(func: Callable[[], T], derived_from: Sequence[Supplier[Any]] = ()) -> Supplier[T]:
        class SupplierOfCallable(Supplier[T]):
            def derived_from(self) -> Iterable[Supplier[Any]]:
                return derived_from

            def get(self) -> T:
                return func()

        return SupplierOfCallable()

    @staticmethod
    def void(from_exc: Exception | None = None, derived_from: Sequence[Supplier[Any]] = ()) -> Supplier[T]:
        """Returns a supplier that always raises :class:`Empty`."""

        class SupplierVoid(Supplier[T]):
            def derived_from(self) -> Iterable[Supplier[Any]]:
                return derived_from

            def get(self) -> T:
                raise Empty(self) from from_exc

            def is_void(self) -> bool:
                return True

        return SupplierVoid()

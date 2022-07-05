from __future__ import annotations

import dataclasses
import warnings
from typing import Any, ClassVar, Iterable, Mapping, TypeVar

import typeapi

from kraken.core.supplier import Empty, Supplier
from kraken.core.utils import NotSet

T = TypeVar("T")


def output() -> Any:
    """Assign the result of this function as a default value to a property on the class level of an :class:`Object`
    subclass to mark it as an output property. This is an alternative to using the :class:`typing.Annotated` type
    hint.

    .. code:: Example

        from kraken.core.property import Object, Property, output

        class MyObj(Object):
            a: Property[int] = output()
    """

    return Output()


class Output:
    """Used to annotate properties, to mark them as computed outputs.

    .. code:: Example

        from kraken.core.property import Object, Property, output
        from typing_extensions import Annotated

        class MyObj(Object):
            a: Annotated[Property[int], Output]
    """


@dataclasses.dataclass
class PropertyDescriptor:
    name: str
    default: Any | NotSet
    is_output: bool


class Property(Supplier[T]):
    """A property represents an input or output parameter of an :class:`Object`."""

    def __init__(self, owner: Object, name: str) -> None:
        self.owner = owner
        self.name = name
        self._value: Supplier[T] = Supplier.void()
        self._finalized = False

    def __repr__(self) -> str:
        return f"Property({self.owner}.{self.name})"

    def derived_from(self) -> Iterable[Supplier[Any]]:
        yield self._value
        yield from self._value.derived_from()

    def get(self) -> T:
        try:
            return self._value.get()
        except Empty:
            raise Empty(self)

    def set(self, value: T | Supplier[T]) -> None:
        if self._finalized:
            raise RuntimeError(f"{self} is finalized")
        if not isinstance(value, Supplier):
            value = Supplier.of(value)
        self._value = value

    def setdefault(self, value: T | Supplier[T]) -> T:
        if self._finalized:
            raise RuntimeError(f"{self} is finalized")
        if self._value.is_void():
            self.set(value)
        return self.get()

    def setfinal(self, value: T | Supplier[T]) -> None:
        self.set(value)
        self.finalize()

    def finalize(self) -> None:
        """Prevent further modification of the value in the property."""

        if not self._finalized:
            self._finalized = True
            # TODO (@NiklasRosenstein): Materializing the property value now will prevent it from being
            #       bound later in the build, e.g. if an input property takes the value of an output property.
            # derived_from = list(self.derived_from())
            # try:
            #     self._value = Supplier.of(self.get(), derived_from)
            # except Empty as exc:
            #     self._value = Supplier.void(exc, derived_from)


class Object:
    """Base class. An object's schema is declared as annotations linking to properties."""

    __schema__: ClassVar[Mapping[str, PropertyDescriptor]] = {}

    def __init_subclass__(cls) -> None:
        """Initializes the :attr:`__schema__` by introspecting the class annotations."""

        schema: dict[str, PropertyDescriptor] = {}
        base: type[Object]
        for base in cls.__bases__:
            schema.update(base.__schema__)

        for key, hint in typeapi.get_annotations(cls).items():
            hint = typeapi.of(hint)
            is_output = False

            # Unwrap annotatations.
            if isinstance(hint, typeapi.Annotated):
                is_output = Output in hint.metadata
                if any(isinstance(x, Output) for x in hint.metadata):
                    warnings.warn(
                        f"Type hint for {cls.__name__}.{key} is annotated with 'Output' instance. You should pass"
                        "the 'Output' class directly as an annotation instead. The property will still be considered "
                        "an output property.",
                        UserWarning,
                    )
                    is_output = True
                hint = hint.wrapped

            # Check if :func:`output()` was used to indicate that the property is an output property.
            if hasattr(cls, key) and isinstance(getattr(cls, key), Output):
                is_output = True
                delattr(cls, key)

            # Is the hint pointing to a Property type?
            if isinstance(hint, typeapi.Type) and hint.type == Property:
                schema[key] = PropertyDescriptor(key, NotSet.Value, is_output)

            # The attribute is annotated as an output but not actually typed as a property?
            elif is_output:
                raise RuntimeError(
                    f"Type hint for {cls.__name__}.{key} is annotated as an 'Output' property, but not actually "
                    "typed as a 'Property'."
                )

            cls.__schema__ = schema

    def __init__(self) -> None:
        """Creates :class:`Properties <Property>` for every property defined in the object's schema."""

        for key, desc in self.__schema__.items():
            setattr(self, key, Property(self, key))

    def update(self, _raise: bool = False, **property_values: Any) -> None:
        """Assign the properties in *property_values* to the properties of the given :class:`Object`. Raises a
        :class:`ValueError` if any of the properties in *property_values* are not in the objects' schema and if
        *_raise* is set to `True`. Prints a warning otherwise."""

        additional_keys = property_values.keys() - self.__schema__.keys()
        if additional_keys and _raise:
            raise ValueError(f"{type(self).__name__} does not have these properties: {additional_keys}")
        if additional_keys:
            warnings.warn(f"{type(self).__name__} does not have these properties: {additional_keys}", UserWarning)

        for key in property_values.keys() - additional_keys:
            prop: Property[Any] = getattr(self, key)
            prop.set(property_values[key])

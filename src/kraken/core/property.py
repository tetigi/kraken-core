from __future__ import annotations

import collections.abc
import copy
import dataclasses
import warnings
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterable, Mapping, TypeVar, cast

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

    return PropertyConfig(output=True)


def config(
    output: bool = False,
    default: Any | NotSet = NotSet.Value,
    default_factory: Callable[[], Any] | NotSet = NotSet.Value,
) -> Any:
    """Assign the result of this function as a default value to a property on the class level of an :class:`Object`
    subclass to configure it's default value or whether it is an output property. This is an alternative to using
    a :class:`typing.Annotated` type hint.

    .. code:: Example

        from kraken.core.property import Object, Property, config

        class MyObj(Object):
            a: Property[int] = config(default=42)
    """

    return PropertyConfig(output, default, default_factory)


@dataclasses.dataclass
class PropertyConfig:
    """Used to annotate properties, to configure the property.

    .. code:: Example

        from kraken.core.property import Object, Property, output
        from typing_extensions import Annotated

        class MyObj(Object):
            a: Annotated[Property[int], PropertyConfig(output=True)]
    """

    output: bool = False
    default: Any | NotSet = NotSet.Value
    default_factory: Callable[[], Any] | NotSet = NotSet.Value


@dataclasses.dataclass
class PropertyDescriptor:
    name: str
    is_output: bool
    default: Any | NotSet
    default_factory: Callable[[], Any] | NotSet
    accepted_types: tuple[type, ...]

    def has_default(self) -> bool:
        return not (self.default is NotSet.Value and self.default_factory is NotSet.Value)

    def get_default(self) -> Any:
        if self.default is not NotSet.Value:
            return copy.deepcopy(self.default)
        elif self.default_factory is not NotSet.Value:
            return self.default_factory()
        else:
            raise RuntimeError(f"property {self.name!r} has no default value")


class Property(Supplier[T]):
    """A property represents an input or output parameter of an :class:`Object`."""

    ValueAdapter = Callable[[Any], Any]

    # This dictionary is a registry for type adapters that are used to ensure that values passed
    # into a property with :meth:`set()` are of the appropriate type. If a type adapter for a
    # particular type does not exist, a basic type check is performed. Note that the type adaptation
    # is not particularly sophisticated at this point and will not apply on items in nested structures.
    VALUE_ADAPTERS: ClassVar[dict[type, ValueAdapter]] = {}

    output = staticmethod(output)
    config = staticmethod(config)

    def __init__(self, owner: Object, name: str, accepted_types: tuple[type, ...]) -> None:

        # Ensure that we have value adapters for every accepted type.
        for accepted_type in accepted_types:
            if accepted_type not in self.VALUE_ADAPTERS:
                raise ValueError(f"missing value adapter for type {accepted_type!r}")
        assert len(accepted_types) > 0

        self.owner = owner
        self.name = name
        self.accepted_types = accepted_types
        self._value: Supplier[T] = Supplier.void()
        self._finalized = False
        self._error_message: str | None = None

    def __repr__(self) -> str:
        return f"Property({self.owner}.{self.name})"

    def _adapt_value(self, value: Any) -> Any:
        errors = []
        for accepted_type in self.accepted_types:
            adapter = self.VALUE_ADAPTERS[accepted_type]
            try:
                return adapter(value)
            except TypeError as exc:
                errors.append(exc)
        raise TypeError(f"{self}: " + "\n".join(map(str, errors))) from (errors[0] if len(errors) == 1 else None)

    def derived_from(self) -> Iterable[Supplier[Any]]:
        yield self._value
        yield from self._value.derived_from()

    def get(self) -> T:
        try:
            return self._value.get()
        except Empty:
            raise Empty(self, self._error_message)

    def set(self, value: T | Supplier[T]) -> None:
        if self._finalized:
            raise RuntimeError(f"{self} is finalized")
        if not isinstance(value, Supplier):
            value = Supplier.of(self._adapt_value(value))
        self._value = value

    def setdefault(self, value: T | Supplier[T]) -> None:
        if self._finalized:
            raise RuntimeError(f"{self} is finalized")
        if self._value.is_void():
            self.set(value)

    def setfinal(self, value: T | Supplier[T]) -> None:
        self.set(value)
        self.finalize()

    def seterror(self, message: str) -> None:
        """Set an error message that should be included when the property is read."""

        self._error_message = message

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

    @staticmethod
    def value_adapter(type_: type) -> Callable[[ValueAdapter], ValueAdapter]:
        """Decorator for functions that serve as a value adapter for the given *type_*."""

        def decorator(func: Property.ValueAdapter) -> Property.ValueAdapter:
            Property.VALUE_ADAPTERS[type_] = func
            return func

        return decorator


class Object:
    """Base class. An object's schema is declared as annotations linking to properties."""

    __schema__: ClassVar[Mapping[str, PropertyDescriptor]] = {}

    def __init_subclass__(cls) -> None:
        """Initializes the :attr:`__schema__` by introspecting the class annotations."""

        schema: dict[str, PropertyDescriptor] = {}
        base: type[Object]
        for base in cls.__bases__:
            if issubclass(base, Object):
                schema.update(base.__schema__)

        for key, hint in typeapi.get_annotations(cls).items():
            hint = typeapi.of(hint)
            config: PropertyConfig | None = None

            # Unwrap annotatations, looking for a PropertyConfig annotation.
            if isinstance(hint, typeapi.Annotated):
                config = next((x for x in hint.metadata if isinstance(x, PropertyConfig)), None)
                hint = hint.wrapped

            # Check if :func:`output()` or :func:`default()` was used to configure the property.
            if hasattr(cls, key) and isinstance(getattr(cls, key), PropertyConfig):
                assert config is None, "PropertyConfig cannot be on both an attribute and type annotation"
                config = getattr(cls, key)
                delattr(cls, key)

            # Is the hint pointing to a Property type?
            if isinstance(hint, typeapi.Type) and hint.type == Property:
                assert hint.args is not None and len(hint.args) == 1, hint

                # Is the inner type a union?
                item_type = hint.args[0]
                if isinstance(item_type, typeapi.Union):
                    # TODO (@NiklasRosenstein): we just expect that any union member be just a type.
                    accepted_types = [cast(typeapi.Type, t).type for t in item_type.types]
                elif isinstance(item_type, typeapi.Type):
                    accepted_types = [item_type.type]
                else:
                    raise RuntimeError(f"Property generic parameter must be a type or union, got {item_type}")

                config = config or PropertyConfig()
                schema[key] = PropertyDescriptor(
                    name=key,
                    is_output=config.output,
                    default=config.default,
                    default_factory=config.default_factory,
                    accepted_types=tuple(accepted_types),
                )

            # The attribute is annotated as an output but not actually typed as a property?
            elif config:
                raise RuntimeError(
                    f"Type hint for {cls.__name__}.{key} is annotated as a 'PropertyConfig', but not actually "
                    "typed as a 'Property'."
                )

            cls.__schema__ = schema

    def __init__(self) -> None:
        """Creates :class:`Properties <Property>` for every property defined in the object's schema."""

        for key, desc in self.__schema__.items():
            prop = Property[Any](self, key, desc.accepted_types)
            setattr(self, key, prop)
            if desc.has_default():
                prop.setdefault(desc.get_default())

    def update(self, _raise: bool = False, **property_values: Any) -> None:
        """Assign the properties in *property_values* to the properties of the given :class:`Object`. Raises a
        :class:`ValueError` if any of the properties in *property_values* are not in the objects' schema and if
        *_raise* is set to `True`. Prints a warning otherwise."""

        additional_keys = property_values.keys() - self.__schema__.keys()
        if additional_keys and _raise:
            raise ValueError(f"{type(self).__name__} does not have these properties: {additional_keys}")
        if additional_keys:
            self._warn_non_existent_properties(additional_keys)

        for key in property_values.keys() - additional_keys:
            prop: Property[Any] = getattr(self, key)
            prop.set(property_values[key])

    def _warn_non_existent_properties(self, keys: set[str]) -> None:
        warnings.warn(f"{type(self).__name__} does not have these properties: {keys}", UserWarning)


# Register common value adapters


def _type_checking_adapter(type_: type) -> Property.ValueAdapter:
    def func(value: Any) -> Any:
        if not isinstance(value, type_):
            raise TypeError(f"expected {type_.__name__}, got {type(value).__name__}")
        return value

    func.__name__ = f"check_{type_.__name__}"
    return func


Property.value_adapter(str)(_type_checking_adapter(str))
Property.value_adapter(int)(_type_checking_adapter(int))
Property.value_adapter(bool)(_type_checking_adapter(bool))
Property.value_adapter(list)(_type_checking_adapter(list))
Property.value_adapter(dict)(_type_checking_adapter(dict))
Property.value_adapter(set)(_type_checking_adapter(set))
Property.value_adapter(type(None))(_type_checking_adapter(type(None)))
Property.value_adapter(cast(type, collections.abc.Callable))(
    _type_checking_adapter(cast(type, collections.abc.Callable))
)


@Property.value_adapter(Path)
def _adapt_path(value: Any) -> Path:
    if isinstance(value, str):
        return Path(value)
    if not isinstance(value, Path):
        raise TypeError(f"expected Path, got {type(value).__name__}")
    return value

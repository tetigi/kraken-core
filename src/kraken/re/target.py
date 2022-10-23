from __future__ import annotations

from typing import Any, ClassVar, Mapping, Type, TypeVar, cast, overload

from kraken.re.address import Address
from kraken.re.exceptions import (
    InvalidFieldException,
    InvalidTargetException,
    NoSuchFieldException,
    RequiredFieldMissingException,
)
from kraken.re.fields import Field
from kraken.re.util.frozendict import FrozenDict
from kraken.re.util.repr import SafeRepr

T_Field = TypeVar("T_Field", bound=Field[Any])
U = TypeVar("U")


class Target(SafeRepr):
    """A Target represents a set of addressable metadata. The metadata consists entirely of fields."""

    alias: ClassVar[str]
    help: ClassVar[str]
    fields: ClassVar[tuple[type[Field[Any]], ...]]
    _field_types: ClassVar[dict[str, type[Field[Any]]]]  # Automatically initialized
    _abstract: bool = True

    address: Address
    field_values: FrozenDict[type[Field[Any]], Field[Any]]

    def __init__(self, raw_values: Mapping[str, Any], address: Address) -> None:
        self.address = address
        self.field_values = self._calculate_field_values(raw_values, address)

    def __init_subclass__(cls, abstract: bool = False) -> None:
        cls._abstract = abstract
        if abstract:
            return
        assert hasattr(cls, "alias"), f"non-abstract target type `{cls.__qualname__}` is missing an `alias`"
        # Ensure no field names are conflicting while producing a mapping from alias to field type.
        cls._field_types = {}
        for field_type in cls.fields:
            if field_type.alias in cls._field_types:
                raise InvalidTargetException(f"found conflicting field alias `{field_type.alias}`")
            cls._field_types[field_type.alias] = field_type

    def __safe_repr__(self) -> str:
        attrs = ", ".join(f"{k.alias}={v.value!r}" for k, v in self.field_values.items())
        return f"{self.alias}({attrs})"

    def __getitem__(self, field_type: Type[T_Field]) -> T_Field:
        """Returns a field in the target by type.

        :raises NoSuchFieldException: If the target has no field of the given type."""

        try:
            return cast(T_Field, self.field_values[field_type])
        except KeyError:
            raise NoSuchFieldException(self, field_type)

    def _calculate_field_values(
        self,
        raw_values: Mapping[str, Any],
        address: Address,
    ) -> FrozenDict[type[Field[Any]], Field[Any]]:
        """Internal. Maps a parameter mapping of raw values by field names to the field type."""

        field_values = {}
        for alias, value in raw_values.items():
            if alias not in self._field_types:
                raise InvalidFieldException(
                    f"Unrecgonized field `{alias}={value!r}` in target `{address}`. Valid fields for the target "
                    f"type `{self.alias}`: {sorted(self._field_types)}."
                )
            field_type = self._field_types[alias]
            field_values[field_type] = field_type(value, address)

        for alias, field_type in self._field_types.items():
            if field_type.required and field_type not in field_values:
                raise RequiredFieldMissingException(address, alias)

        return FrozenDict(field_values)

    @overload
    def get(self, field_type: Type[T_Field]) -> None:
        ...

    @overload
    def get(self, field_type: Type[T_Field], default: U) -> T_Field | U:
        ...

    def get(self, field_type: Type[T_Field], default: U | None = None) -> T_Field | U | None:
        try:
            return self[field_type]
        except NoSuchFieldException:
            return default

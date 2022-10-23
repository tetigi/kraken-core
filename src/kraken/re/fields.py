from __future__ import annotations

import dataclasses
from typing import Any, ClassVar, Generic, Hashable, Optional, Tuple, Type, TypeVar, cast

import typeapi

from kraken.re.address import Address
from kraken.re.exceptions import InvalidFieldTypeException, RequiredFieldMissingException
from kraken.re.util.frozendict import FrozenDict

T = TypeVar("T", bound=Hashable)


class Field(Generic[T]):
    """A Field represents a piece of data in a target."""

    alias: ClassVar[str]
    help: ClassVar[str]
    default: Any  # NOTE (@NiklasRosenstein): Generic classvar is not allow
    required: ClassVar[bool] = False

    def __init__(self, raw_value: Any | None, address: Address) -> None:
        self.value = self._compute_value(raw_value, address)

    def __init_subclass__(cls, abstract: bool = False) -> None:
        # Validate that `default` is set if `required` is set to False.
        assert (
            abstract or hasattr(cls, "default") or cls.required
        ), f"missing `default` on optional field subclass `{cls.__name__}`"
        assert abstract or hasattr(cls, "alias"), f"missing `alias` on field subclass `{cls.__name__}`"

    def __eq__(self, other: Any | Field[Any]) -> bool:
        if not isinstance(other, Field):
            return NotImplemented
        return (self.__class__, self.value) == (other.__class__, other.value)

    def __hash__(self) -> int:
        return hash((type(self), self.value))

    def __repr__(self) -> str:
        return f"{type(self).__module__}.{type(self).__name__}(alias={self.alias!r}, value={self.value!r})"

    @classmethod
    def _compute_value(cls, raw_value: Any | None, address: Address) -> T | None:
        if cls.required and raw_value is None:
            raise RequiredFieldMissingException(address, cls.alias)
        if raw_value is None:
            return cast(T, getattr(cls, "default", None))
        return cast(T, raw_value)

    def get(self) -> T:
        """Should only be used with fields that are required."""
        if self.value is None:
            raise RuntimeError(f"value of field {self} is None or not set")
        return self.value


@dataclasses.dataclass(frozen=True)
class FieldSetSpec:
    """Contains the spec for a :class:`FieldSet` that is constructed for a :class:`FieldSet`."""

    fields: FrozenDict[str, Type[Field[Any]]] = dataclasses.field(default_factory=FrozenDict)
    required_fields: FrozenDict[str, Type[Field[Any]]] = dataclasses.field(default_factory=FrozenDict)

    def update(self, other: FieldSetSpec) -> FieldSetSpec:
        # TODO (@NiklasRosenstein): Ensure that no fields overlap in name or type
        return FieldSetSpec(
            fields=FrozenDict(**self.fields, **other.fields),
            required_fields=FrozenDict(**self.required_fields, **other.required_fields),
        )

    def validate(self) -> None:
        # Validate that all types on the field are unique.
        reverse_fields: dict[type, list[str]] = {}
        for field_name, field_type in self.fields.items():
            reverse_fields.setdefault(field_type, []).append(field_name)
        for field_type, field_names in reverse_fields.items():
            if len(field_names) > 1:
                raise RuntimeError(
                    f"Two fields on FieldSet subclasses cannot have the same type. The type {field_type.__qualname__} "
                    f"is used by more than one field: {', '.join(field_names)}"
                )


class FieldSet:
    """A FieldSet describes the inputs to a rule. Subclasses of the FieldSet should be dataclasses that declare
    the required and optional input fields for a target to be accepted by the rule. The field set will then be passed
    into the rule as an argument.

    The field members are derived from the annotations. The field name does not need to match the field name of the
    field type, they are matched based on the field type. However this means, just like on a target, that the same
    field type cannot occurr more than once in the same field set.

    Only concrete types and optionals are allowed as annotations. Take care that the annotations must be evaluatable
    at runtime, so using 3.10 built-in generics and unions will not work in Python versions before 3.10. ClassVar
    annotations are always ignored."""

    address: Address
    __fieldset_ignore__: ClassVar[Tuple[str, ...]] = ()  # Ignore these fields in the annotations
    __fieldset_spec__: ClassVar[FieldSetSpec] = FieldSetSpec()  # Automatically created __init_subclass__()

    def __init_subclass__(cls) -> None:
        spec = FieldSetSpec()

        for base in cls.__mro__:
            if issubclass(base, FieldSet):
                spec = spec.update(base.__fieldset_spec__)

        annotations = typeapi.get_annotations(cls, include_bases=False)
        for key, value in annotations.items():
            if key in cls.__fieldset_ignore__:
                continue

            hint = typeapi.of(value)
            if isinstance(hint, typeapi.ClassVar):
                continue

            required = True
            if isinstance(hint, typeapi.Union):
                if not hint.has_none_type() or len(hint.types) > 2:
                    raise RuntimeError(
                        "Annotations on FieldSet subclasses must be concrete types or optionals. "
                        f"Found {key}: {value}"
                    )
                required = False
                hint = hint.without_none_type()
            if not isinstance(hint, typeapi.Type) or hint.nparams > 1:
                raise RuntimeError(
                    f"Annotations on FieldSet subclasses must be concrete types or optionals. Found {key}: {value}"
                )

            spec = spec.update(
                FieldSetSpec(
                    fields=FrozenDict({key: hint.type}),
                    required_fields=FrozenDict({key: hint.type} if required else {}),
                )
            )

        spec.validate()
        cls.__fieldset_spec__ = spec


class ScalarField(Field[T], abstract=True):
    """A field for a scalar value."""

    value_type: ClassVar[type]
    value_type_description: ClassVar[str]

    @classmethod
    def _compute_value(cls, raw_value: Any | None, address: Address) -> T | None:
        computed_value = super()._compute_value(raw_value, address)
        if computed_value is not None and not isinstance(computed_value, cls.value_type):
            raise InvalidFieldTypeException(
                address,
                cls.alias,
                raw_value,
                cls.value_type_description,
            )
        return cast(Optional[T], computed_value)


class BooleanField(ScalarField[bool], abstract=True):
    value_type = bool
    value_type_description = "a boolean"


class IntField(ScalarField[int], abstract=True):
    value_type = int
    value_type_description = "an integer"


class FloatField(ScalarField[int], abstract=True):
    value_type = float
    value_type_description = "an float"


class StringField(ScalarField[str], abstract=True):
    value_type = str
    value_type_description = "a string"


class SequenceField(Field[Tuple[T, ...]], abstract=True):
    """Base class for fields that accept a particular type."""

    item_type: ClassVar[type]
    item_type_description: ClassVar[str]

    @classmethod
    def __compute_value(cls, raw_value: Any | None, address: Address) -> Tuple[T, ...] | None:
        computed_value = super()._compute_value(raw_value, address)
        if computed_value is None:
            return None
        # Ensure that every item is of the specified type.
        items = tuple(computed_value)
        for item in items:
            if not isinstance(item, cls.item_type):
                raise InvalidFieldTypeException(address, cls.alias, raw_value, cls.item_type_description)
        return items


class StringSequenceField(SequenceField[str], abstract=True):
    item_type = str
    item_type_description = "a sequence of strings"

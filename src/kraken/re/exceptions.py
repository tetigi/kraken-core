from __future__ import annotations

from typing import TYPE_CHECKING, Any, Collection, Sequence

from kraken.re.util.repr import SafeStr

if TYPE_CHECKING:
    from kraken.re.address import Address
    from kraken.re.fields import Field
    from kraken.re.rules import RulePath
    from kraken.re.target import Target


class NoSuchFieldException(SafeStr, Exception):
    def __init__(self, target: Target, field_type: type[Field[Any]]) -> None:
        self.target = target
        self.field_type = field_type

    def __safe_str__(self) -> str:
        return f"target `{self.target.address}` of type `{self.target.alias}` has no field `{self.field_type.__name__}`"


class InvalidFieldException(Exception):
    pass


class InvalidFieldTypeException(InvalidFieldException):
    def __init__(self, address: Address, field_alias: str, raw_value: Any | None, expected_type: str) -> None:
        self.address = address
        self.field_alias = field_alias
        self.raw_value = raw_value
        self.expected_type = expected_type


class RequiredFieldMissingException(InvalidFieldException):
    def __init__(self, address: Address, field_name: str) -> None:
        self.address = address
        self.field_name = field_name

    def __str__(self) -> str:
        return f"{self.address}: `{self.field_name}`"


class InvalidTargetException(Exception):
    pass


class ResolutionError(Exception):
    """For errors while resolving rules to reach a target type from a set of root types."""


class MultiplePathsToReachTargetTypeError(ResolutionError):
    """This exception is raised if multiple paths to go from a set of root types to a target type where encountered."""

    def __init__(self, target_type: type, root_types: Collection[type], paths: Sequence[RulePath]) -> None:
        self.target_type = target_type
        self.root_types = root_types
        self.paths = paths

    def __str__(self) -> str:
        message_parts = [f"Found multiple paths while resolving rules for target type `{self.target_type.__name__}` "]
        message_parts += ["from the following root types: {" + ", ".join(t.__name__ for t in self.root_types) + "}"]
        message_parts += [""]
        message_parts += [f"The following {len(self.paths)} path(s) were found:"]
        message_parts += [""]
        for idx, path in enumerate(self.paths):
            prefix = f"  [{idx}]: "
            rules_formatted = prefix + ("\n" + " " * len(prefix)).join(map(str, path))
            message_parts.append(rules_formatted)
        return "\n".join(message_parts)


class NoPathsToReachTargetTypeError(ResolutionError):
    def __init__(self, target_type: type, root_types: Collection[type]) -> None:
        self.target_type = target_type
        self.root_types = root_types

    def __str__(self) -> str:
        return (
            f"Could not find a path to reach target type `{self.target_type.__name__}` from root types {{"
            + ", ".join(t.__name__ for t in self.root_types)
            + "}"
        )

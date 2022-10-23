from __future__ import annotations

import abc
import dataclasses
import posixpath


def _validate_address_directory(directory: str) -> None:
    if not directory:
        raise ValueError("directory cannot be empty")
    if ":" in directory:
        raise ValueError(f"invalid directory: {directory!r}")


def _validate_address_name(name: str) -> None:
    if not name:
        raise ValueError("name cannot be empty")
    if ":" in name:
        raise ValueError(f"invalid name: {name!r}")


@dataclasses.dataclass(frozen=True)
class Address:
    """The address for a target. Consists of a `directory` and a `name` that are formatted in a single string as
    `<directory>:<name>`. The `directory` can be an absolute path, which then references the root directory of
    the current evaluation context."""

    directory: str
    name: str

    def __post_init__(self) -> None:
        _validate_address_directory(self.directory)
        _validate_address_directory(self.name)

    def __str__(self) -> str:
        return f"{self.directory}:{self.name}"

    def is_abs(self) -> bool:
        return self.directory.startswith("/")

    @classmethod
    def of(cls, s: str) -> Address:
        directory, name = s.partition(":")[::2]
        return Address(directory, name)


class AddressSpec(abc.ABC):
    """Represents a selector for an address."""

    @abc.abstractmethod
    def __str__(self) -> str:
        ...

    @abc.abstractmethod
    def matches_address(self, address: Address) -> bool:
        ...


@dataclasses.dataclass(frozen=True)
class CommonAddressSpec(AddressSpec):
    """The common AddressSpec allows to select an targets matching a given name or to select all targets in a given
    directory. Examples:

    - `:` matches all targets
    - `foo/bar` matches the directory `foo/bar`
    - `:spam` matches all targets with the name `spam`
    """

    directory: str | None
    name: str | None

    def __post_init__(self) -> None:
        if self.directory:
            _validate_address_directory(self.directory)
        if self.name:
            _validate_address_name(self.name)

    def __str__(self) -> str:
        result = self.directory or ""
        if self.name:
            result += f":{self.name}"
        return result

    def matches_address(self, address: Address) -> bool:
        if self.directory is not None:
            a = posixpath.normpath(self.directory)
            b = posixpath.normpath(address.directory)
            if a != b:
                return False

        return not self.name or self.name == address.name

    @classmethod
    def of(cls, s: str) -> CommonAddressSpec:
        if not s:
            raise ValueError(f"invalid address spec: {s!r}")
        directory, name = s.partition(":")[::2]
        return CommonAddressSpec(directory or None, name or None)

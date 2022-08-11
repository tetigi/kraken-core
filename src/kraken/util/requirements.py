from __future__ import annotations

import abc
import argparse
import dataclasses
import hashlib
import re
import shlex
from pathlib import Path
from typing import Any, Iterable, TextIO

from kraken.util.helpers import flatten


class Requirement(abc.ABC):

    name: str  #: The distribution name.

    @abc.abstractmethod
    def to_args(self, base_dir: Path) -> list[str]:
        """Convert the requirement to Pip args."""

        raise NotImplementedError


@dataclasses.dataclass(frozen=True)
class PipRequirement(Requirement):
    """Represents a Pip requriement."""

    name: str
    spec: str | None

    def __str__(self) -> str:
        return f"{self.name}{self.spec or ''}"

    def to_args(self, base_dir: Path) -> list[str]:
        return [str(self)]


@dataclasses.dataclass(frozen=True)
class LocalRequirement(Requirement):
    """Represents a requirement on a local project on the filesystem.

    The string format of a local requirement is `name@path`. The `name` must match the distribution name."""

    name: str
    path: Path

    def __str__(self) -> str:
        return f"{self.name}@{self.path}"

    def to_args(self, base_dir: Path) -> list[str]:
        return [str((base_dir / self.path if base_dir else self.path).absolute())]


def parse_requirement(value: str) -> Requirement:
    match = re.match(r"(.+?)@(.+)", value)
    if match:
        return LocalRequirement(match.group(1).strip(), Path(match.group(2).strip()))

    match = re.match(r"([\w\d\-\_]+)(.*)", value)
    if match:
        return PipRequirement(match.group(1), match.group(2).strip() or None)

    raise ValueError(f"invalid requirement: {value!r}")


@dataclasses.dataclass(frozen=True)
class RequirementSpec:
    """Represents the requirements for a Kraken build script."""

    requirements: tuple[Requirement, ...]
    index_url: str | None = None
    extra_index_urls: tuple[str, ...] = ()
    interpreter_constraint: str | None = None
    pythonpath: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for req in self.requirements:
            assert isinstance(req, Requirement), type(req)

    def __eq__(self, other: Any) -> bool:
        # NOTE (@NiklasRosenstein): packaging.requirements.Requirement is not properly equality comparable, so
        #       we implement a custom comparison based on the hash digest.
        if isinstance(other, RequirementSpec):
            return (type(self), self.to_hash()) == (type(other), other.to_hash())
        return False

    def with_requirements(self, reqs: Iterable[str | Requirement]) -> RequirementSpec:
        """Adds the given requirements and returns a new instance."""

        requirements = list(self.requirements)
        for req in reqs:
            if isinstance(req, str):
                req = parse_requirement(req)
            requirements.append(req)
        return RequirementSpec(
            requirements=tuple(requirements),
            index_url=self.index_url,
            extra_index_urls=self.extra_index_urls,
            interpreter_constraint=self.interpreter_constraint,
            pythonpath=self.pythonpath,
        )

    def with_pythonpath(self, path: Iterable[str]) -> RequirementSpec:
        return RequirementSpec(
            requirements=self.requirements,
            index_url=self.index_url,
            extra_index_urls=self.extra_index_urls,
            interpreter_constraint=self.interpreter_constraint,
            pythonpath=(*self.pythonpath, *path),
        )

    @staticmethod
    def from_json(data: dict[str, Any]) -> RequirementSpec:
        return RequirementSpec(
            requirements=tuple(parse_requirement(x) for x in data["requirements"]),
            index_url=data.get("index_url"),
            extra_index_urls=tuple(data.get("extra_index_urls", ())),
            interpreter_constraint=data.get("interpreter_constraint"),
            pythonpath=tuple(data.get("pythonpath", ())),
        )

    def to_json(self) -> dict[str, Any]:
        result: dict[str, Any] = {"requirements": [str(x) for x in self.requirements], "pythonpath": self.pythonpath}
        if self.index_url is not None:
            result["index_url"] = self.index_url
        if self.extra_index_urls:
            result["extra_index_urls"] = self.extra_index_urls
        if self.interpreter_constraint:
            result["interpreter_constraint"] = self.interpreter_constraint
        return result

    @staticmethod
    def from_args(args: list[str]) -> RequirementSpec:
        """Parses the arguments using :mod:`argparse` as if they are Pip install arguments.

        :raise ValueError: If an invalid argument is encountered."""

        parser = argparse.ArgumentParser()
        parser.add_argument("packages", nargs="*")
        parser.add_argument("--index-url")
        parser.add_argument("--extra-index-url", action="append")
        parser.add_argument("--interpreter-constraint")
        parsed, unknown = parser.parse_known_args(args)
        if unknown:
            raise ValueError(f"encountered unknown arguments in requirements: {unknown}")

        return RequirementSpec(
            requirements=tuple(parse_requirement(x) for x in parsed.packages or []),
            index_url=parsed.index_url,
            extra_index_urls=tuple(parsed.extra_index_url or ()),
            interpreter_constraint=parsed.interpreter_constraint,
        )

    def to_args(self, base_dir: Path = Path("."), with_requirements: bool = True) -> list[str]:
        """Converts the requirements back to Pip install arguments.

        :param base_dir: The base directory that relative :class:`LocalRequirement`s should be considered relative to.
        :param with_requirements: Can be set to `False` to not return requirements in the argument, just the index URLs.
        """

        args = []
        if self.index_url:
            args += ["--index-url", self.index_url]
        for url in self.extra_index_urls:
            args += ["--extra-index-url", url]
        if with_requirements:
            args += flatten(req.to_args(base_dir) for req in self.requirements)
        return args

    def to_hash(self, algorithm: str = "sha256") -> str:
        """Hash the requirements spec to a hexdigest."""

        hash_parts = [str(req) for req in self.requirements] + ["::pythonpath"] + list(self.pythonpath)
        hash_parts += ["::interpreter_constraint", self.interpreter_constraint or ""]
        return hashlib.new(algorithm, ":".join(hash_parts).encode()).hexdigest()


def parse_requirements_from_python_script(file: TextIO) -> RequirementSpec:
    """Parses the requirements defined in a Python script.

    The Pip install arguments are extracted from all lines in the first single-line comment block, which has to start
    at the beginning of the file, which start with the text `# ::requirements` (whitespace optional). Additionally,
    paths to ass to `sys.path` can be specified with `# ::pythonpath`.

    Example:

    ```py
    #!/usr/bin/env python
    # :: requirements PyYAML
    # :: pythonpath ./build-support
    ```

    The resulting :class:`RequirementSpec` will contain `["PyYAML"]` as requirement and `"./build-support"` ain
    the Python path.
    """

    requirements = []
    pythonpath = []
    for line in map(str.rstrip, file):
        if not line.startswith("#"):
            break
        match = re.match(r"#\s*::\s*(requirements|pythonpath)(.+)", line)
        if not match:
            break
        args = shlex.split(match.group(2))
        if match.group(1) == "requirements":
            requirements += args
        else:
            pythonpath += args

    print(requirements)
    return RequirementSpec.from_args(requirements).with_pythonpath(pythonpath)

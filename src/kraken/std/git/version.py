from __future__ import annotations

import dataclasses
import re
import subprocess as sp
from pathlib import Path


def git_describe(path: Path | None, tags: bool = True, dirty: bool = True) -> str:
    """Describe a repository with tags.

    :param path: The directory in which to describe.
    :param tags: Whether to include tags (adds the `--tags` flag).
    :param dirty: Whether to include if the directory tree is dirty (adds the `--dirty` flag).
    :raise ValueError: If `git describe` failed.
    :return: The Git head description.
    """

    command = ["git", "describe"]
    if tags:
        command.append("--tags")
    if dirty:
        command.append("--dirty")
    try:
        return sp.check_output(command, cwd=path).decode().strip()
    except sp.CalledProcessError:
        raise ValueError("could not describe Git repository")


@dataclasses.dataclass
class GitVersion:
    """Represents a "git version" that has a major, minor and patch version and optionall a commit distance."""

    @dataclasses.dataclass
    class CommitDistance:
        value: int
        sha: str

    major: int
    minor: int
    patch: int
    distance: CommitDistance | None
    dirty: bool

    @staticmethod
    def parse(value: str) -> GitVersion:
        GIT_VERSION_REGEX = r"^(\d+)\.(\d+)\.(\d+)(?:-(\d+)-g(\w+))?(-dirty)?$"
        match = re.match(GIT_VERSION_REGEX, value)
        if not match:
            raise ValueError(f"not a valid GitVersion: {value!r}")
        if match.group(4):
            distance = GitVersion.CommitDistance(value=int(match.group(4)), sha=match.group(5))
        else:
            distance = None
        return GitVersion(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            distance=distance,
            dirty=match.group(6) is not None,
        )

    def format(self, distance: bool = True, sha: bool = True, dirty: bool = False) -> str:
        result = f"{self.major}.{self.minor}.{self.patch}"
        if self.distance and distance:
            result = f"{result}-{self.distance.value}"
            if sha:
                result = f"{result}-g{self.distance.sha}"
            if self.dirty and dirty:
                result = f"{result}-dirty"
        return result

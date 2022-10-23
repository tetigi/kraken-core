from __future__ import annotations

import enum
import io
from itertools import islice
from os import PathLike
from pathlib import Path
from typing import Iterable, NamedTuple, TextIO


class GitignoreEntryType(enum.Enum):
    COMMENT = enum.auto()
    BLANK = enum.auto()
    PATH = enum.auto()


class GitignoreEntry(NamedTuple):
    type: GitignoreEntryType
    value: str

    def __str__(self) -> str:
        if self.is_comment():
            return f"# {self.value}"
        return self.value

    def is_comment(self) -> bool:
        return self.type == GitignoreEntryType.COMMENT

    def is_blank(self) -> bool:
        return self.type == GitignoreEntryType.BLANK

    def is_path(self) -> bool:
        return self.type == GitignoreEntryType.PATH


class GitignoreFile(NamedTuple):
    entries: list[GitignoreEntry]

    def find_comment(self, comment: str) -> int | None:
        return next(
            (i for i, e in enumerate(self.entries) if e.is_comment() and e.value.lstrip("#").strip() == comment), None
        )

    def paths(self, start: int | None = None, stop: int | None = None) -> Iterable[str]:
        return (entry.value for entry in islice(self.entries, start, stop) if entry.is_path())

    def add_comment(self, comment: str, index: int | None = None) -> None:
        entry = GitignoreEntry(GitignoreEntryType.COMMENT, comment)
        self.entries.insert(len(self.entries) if index is None else index, entry)

    def add_blank(self, index: int | None = None) -> None:
        entry = GitignoreEntry(GitignoreEntryType.BLANK, "")
        self.entries.insert(len(self.entries) if index is None else index, entry)

    def add_path(self, path: str, index: int | None = None) -> None:
        entry = GitignoreEntry(GitignoreEntryType.PATH, path)
        self.entries.insert(len(self.entries) if index is None else index, entry)

    def remove_path(self, path: str) -> None:
        removed = 0
        while True:
            index = next((i for i, e in enumerate(self.entries) if e.is_path() and e.value == path), None)
            if index is None:
                break
            del self.entries[index]
            removed += 1
        if removed == 0:
            raise ValueError(f'"{path}" not in GitignoreFile')

    def render(self) -> str:
        return "\n".join(map(str, self.entries)) + "\n"


def parse_gitignore(file: TextIO | Path | str) -> GitignoreFile:
    if isinstance(file, str):
        return parse_gitignore(io.StringIO(file))
    elif isinstance(file, PathLike):
        with file.open() as fp:
            return parse_gitignore(fp)

    result = GitignoreFile([])
    for line in file:
        line = line.rstrip("\n")
        if line.startswith("#"):
            line = line[1:].lstrip()
            type = GitignoreEntryType.COMMENT
        elif not line.strip():
            line = ""
            type = GitignoreEntryType.BLANK
        else:
            type = GitignoreEntryType.PATH
        result.entries.append(GitignoreEntry(type, line))

    return result


def sort_gitignore(gitignore: GitignoreFile, sort_paths: bool = True, sort_groups: bool = False) -> GitignoreFile:
    """Sorts the entries in the specified gitignore file, keeping paths under a common comment block grouped.
    Will also get rid of any extra blanks.

    :param gitignore: The input to sort.
    :param sort_paths: Whether to sort paths (default: True).
    :param sort_groups: Whether to sort groups among themselves, not just paths within groups (default: False).
    :return: A new, sorted gitignore file.
    """

    class Group(NamedTuple):
        comments: list[str]
        paths: list[str]

    # List of (comments, paths).
    groups: list[Group] = [Group([], [])]

    for entry in gitignore.entries:
        if entry.is_path():
            groups[-1].paths.append(entry.value)
        elif entry.is_comment():
            # If we already have paths in the current group, we open a new group.
            if groups[-1].paths:
                groups.append(Group([entry.value], []))
            # Otherwise we append the comment to the group.
            else:
                groups[-1].comments.append(entry.value)

    if sort_groups:
        groups.sort(key=lambda g: "\n".join(g.comments).lower())

    new = GitignoreFile([])
    for group in groups:
        if sort_paths:
            group.paths.sort(key=str.lower)
        for comment in group.comments:
            new.add_comment(comment)
        for path in group.paths:
            new.add_path(path)
        new.add_blank()

    if new.entries and new.entries[-1].is_blank():
        new.entries.pop()

    return new

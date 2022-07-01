from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .task import Task


class Action(abc.ABC):
    """Implementation of a task."""

    def execute(self, task: Task) -> None:
        ...

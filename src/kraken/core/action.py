from __future__ import annotations

import abc
from typing import Optional


class Action(abc.ABC):
    """Actions implement the behaviour of tasks."""

    @abc.abstractmethod
    def execute(self) -> Optional[int]:
        ...

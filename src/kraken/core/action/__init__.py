from __future__ import annotations

import abc
import enum


class ActionResult(enum.Enum):
    UP_TO_DATE = enum.auto()
    SKIPPED = enum.auto()
    SUCCEEDED = enum.auto()
    FAILED = enum.auto()


class Action(abc.ABC):
    """Actions implement the behaviour of tasks."""

    def is_up_to_date(self) -> bool:
        """Gives the action a chance before it is executed to inform the build executor that it is up
        to date and does not need to be executed. Some actions may be able to determine this quickly so
        they can implement this method to improve build performance and user information display."""

        return False

    def is_skippable(self) -> bool:
        """Gives the action a chance before it is executed to inform the build executor that the action
        can be skipped. This status is different from :meth:`is_up_to_date` but may lead to the same result,
        i.e. that the action is not executed."""

        return False

    @abc.abstractmethod
    def execute(self) -> ActionResult:
        ...

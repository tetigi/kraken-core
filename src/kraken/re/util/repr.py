import abc
import logging

logger = logging.getLogger(__name__)


class SafeRepr:
    def __repr__(self) -> str:
        try:
            return self.__safe_repr__()
        except Exception:
            logger.exception(
                "An unhandled exception occurred converting object of type `%s` to string.",
                type(self).__qualname__,
            )
            return f"<... {type(self).__qualname__} ...>"

    @abc.abstractmethod
    def __safe_repr__(self) -> str:
        ...


class SafeStr:
    def __str__(self) -> str:
        try:
            return self.__safe_str__()
        except Exception:
            logger.exception(
                "An unhandled exception occurred converting object of type `%s` to string.",
                type(self).__qualname__,
            )
            return f"<... {type(self).__qualname__} ...>"

    @abc.abstractmethod
    def __safe_str__(self) -> str:
        ...

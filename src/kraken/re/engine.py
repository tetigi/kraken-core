from __future__ import annotations

from typing import Any, Collection, TypeVar, cast

from kraken.re.exceptions import MultiplePathsToReachTargetTypeError, NoPathsToReachTargetTypeError
from kraken.re.rules import RuleSet, TypeMatcherFunc

T = TypeVar("T")


class RuleEngine:
    """Finds the path to evaluate rules to reach a target type from a set of input types."""

    def __init__(self, rules: RuleSet, type_matcher: TypeMatcherFunc | None = isinstance) -> None:
        self._rules = rules
        self._type_matcher = type_matcher

    def get(self, target_type: type[T], roots: Collection[Any]) -> T:
        """Resolve the creation of *target_type* from the given *roots*."""

        root_types = {type(v): v for v in roots}
        if len(root_types) != len(roots):
            raise ValueError("found at least one duplicate root type")

        paths = list(self._rules.resolve_paths(target_type, root_types, self._type_matcher))
        if len(paths) > 1:
            raise MultiplePathsToReachTargetTypeError(
                target_type=target_type,
                root_types=root_types,
                paths=paths,
            )
        if not paths:
            raise NoPathsToReachTargetTypeError(target_type=target_type, root_types=root_types)

        assert len(paths) == 1

        result = None
        for rule in paths[0]:
            result = rule.apply_to_inputs(root_types)
            root_types[rule.output_type] = result
        assert result is not None, paths[0]
        return cast(T, result)

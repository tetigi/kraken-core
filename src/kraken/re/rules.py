from __future__ import annotations

import dataclasses
import inspect
import operator
from typing import Any, Callable, Collection, Iterator, Tuple

from kraken.re.util.frozendict import FrozenDict

TypeMatcherFunc = Callable[[type, type], bool]
RulePath = Tuple["Rule", ...]


@dataclasses.dataclass
class Rule:
    """Represents a rule that can transform the input types into the output type."""

    name: str
    input_types: FrozenDict[str, type]
    output_type: type
    function: Callable[..., Any]

    def __post_init__(self) -> None:
        assert isinstance(self.name, str)
        assert isinstance(self.input_types, FrozenDict)
        assert all(isinstance(v, type) for v in self.input_types.values())
        assert isinstance(self.output_type, type)
        assert callable(self.function)

    def __str__(self) -> str:
        signature = ", ".join(f"{k}: {v.__name__}" for k, v in self.input_types.items())
        return f"{self.name}({signature}) -> {self.output_type.__name__}"

    def __repr__(self) -> str:
        return f"Rule<{self}>"

    def matches_inputs(self, input_types: Collection[type], type_matcher: TypeMatcherFunc | None = None) -> bool:
        if type_matcher is None:
            return all(t in input_types for t in self.input_types.values())
        else:
            return all(any(type_matcher(x, y) for y in input_types) for x in self.input_types.values())

    def apply_to_inputs(self, inputs: dict[type, str]) -> Any:
        kwargs = {k: inputs[v] for k, v in self.input_types.items()}
        result = self.function(**kwargs)
        if not isinstance(result, self.output_type):
            raise RuntimeError(
                f"rule `{self.name}` must return object of type {self.output_type.__qualname__} but "
                f"actually returned {type(result).__qualname__}"
            )
        return result

    @classmethod
    def of(cls, function: Callable[..., Any]) -> "Rule":
        """Construct a Rule object from a function."""

        def _eval(annotation: Any) -> Any:
            if isinstance(annotation, str):
                return eval(annotation, function.__globals__)
            return annotation

        # NOTE: inspect.signature(eval_str) is available in 3.10+, so for compatibility we evaluate string
        #       annotations manually.
        signature = inspect.signature(function)
        signature = inspect.Signature(
            parameters=[
                inspect.Parameter(name, param.kind, default=param.default, annotation=_eval(param.annotation))
                for name, param in signature.parameters.items()
            ],
            return_annotation=_eval(signature.return_annotation),
        )

        if signature.return_annotation is signature.empty:
            raise ValueError(f"rule function `{function.__qualname__}` must have a return type annotation")
        if not isinstance(signature.return_annotation, type) and signature.return_annotation is not None:
            raise ValueError(
                f"rule function `{function.__qualname__}` return type annotation must be a type "
                f"(got `{type(signature.return_annotation).__name__}`)"
            )

        required_types = {}
        for param_name, param in signature.parameters.items():
            if param.annotation is signature.empty:
                raise ValueError(
                    f"rule function `{function.__qualname__}` is missing a type annotation for parameter `{param_name}`"
                )
            if not isinstance(param.annotation, type):
                raise ValueError(
                    f"rule function `{function.__qualname__}` parameter `{param_name}` type annotation must be a type "
                    f"(got `{type(param.annotation).__name__}`)"
                )
            required_types[param_name] = param.annotation

        return cls(
            function.__qualname__,
            FrozenDict(required_types),
            type(None) if signature.return_annotation is None else signature.return_annotation,
            function,
        )


class RuleSet:
    """The RuleSet contains all rules that are defined in a session."""

    def __init__(self) -> None:
        self._rules: list[Rule] = []

    def add_rule(self, rule: Rule) -> None:
        assert isinstance(rule, Rule), type(rule).__qualname__
        self._rules.append(rule)

    def get_rules_for_input_types(
        self,
        input_types: Collection[type],
        type_matcher: TypeMatcherFunc | None = None,
    ) -> Iterator[Rule]:
        """Return all rules that accept any subset of the given *input_types*.

        :param input_types: A collection of input types that are available.
        :param type_matcher: If specified, the function is used to check if the type passed as positional argument 1
            is to be considered a subtype of the type at positional argument 2. If not specified, only exact type
            is matched.
        """

        type_matcher = type_matcher
        for rule in self._rules:
            if rule.matches_inputs(input_types, type_matcher):
                yield rule

    def get_rules_for_output_type(
        self,
        output_type: type,
        type_matcher: TypeMatcherFunc | None = None,
    ) -> Iterator[Rule]:
        """Return the rules that produce the given output type.

        :param output_type: The output type that must be produced by the rules.
        :param type_matcher: If specified, the function is used to check if the type passed as positional argument 1
            is to be considered a subtype of the type at positional argument 2. If not specified, only exact type
            is matched.
        """

        type_matcher = type_matcher or operator.eq
        for rule in self._rules:
            if type_matcher(rule.output_type, output_type):
                yield rule

    def resolve_paths(
        self,
        target_type: type,
        root_types: Collection[type],
        type_matcher: TypeMatcherFunc | None = None,
    ) -> Iterator[RulePath]:
        """Return all possible rule paths to reach the *target_type* from the given *root_types*.

        The evaluation assumes that any type evaluated by a rule results is added to the *root_types*."""

        def _find_paths(target_type: type, input_types: set[type], path: RulePath) -> Iterator[RulePath]:
            if target_type in input_types:
                yield path
            else:
                for rule in self.get_rules_for_input_types(input_types, type_matcher):
                    yield from _find_paths(rule.output_type, input_types | {rule.output_type}, path + (rule,))

        yield from _find_paths(target_type, set(root_types), ())

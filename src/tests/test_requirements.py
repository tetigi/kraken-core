import io
from pathlib import Path

import pytest

from kraken.core.util.requirements import (
    LocalRequirement,
    PipRequirement,
    RequirementSpec,
    parse_requirement,
    parse_requirements_from_python_script,
)


def test__parse_requirement__can_handle_various_pip_requirements() -> None:
    assert parse_requirement("requests") == PipRequirement("requests", None)
    assert parse_requirement("requests>=0.1.2,<2") == PipRequirement("requests", ">=0.1.2,<2")
    assert parse_requirement("requests >=0.1.2,<2") == PipRequirement("requests", ">=0.1.2,<2")
    assert parse_requirement("abc[xyz,012] !=  2") == PipRequirement("abc", "[xyz,012] !=  2")
    with pytest.raises(ValueError):
        assert parse_requirement("!=  2") == PipRequirement("abc", "[xyz,012] !=  2")


def test__parse_requirement__can_handle_local_requirements() -> None:
    assert parse_requirement("kraken-std@.") == LocalRequirement("kraken-std", Path("."))
    assert parse_requirement("abc @ ./abc") == LocalRequirement("abc", Path("./abc"))
    assert parse_requirement("abc@/module/at/abc") == LocalRequirement("abc", Path("/module/at/abc"))


def test__parse_requirements_from_python_script__ok() -> None:
    parsed = parse_requirements_from_python_script(
        io.StringIO(
            "# ::requirements abc>=2 'xyz @ ./xyz' \n"
            "#:: requirements --extra-index-url https://... --interpreter-constraint >=3.7 \n"
            "# :: pythonpath build-support\n"
        )
    )
    expected = RequirementSpec(
        requirements=(PipRequirement("abc", ">=2"), LocalRequirement("xyz", Path("./xyz"))),
        extra_index_urls=("https://...",),
        interpreter_constraint=">=3.7",
        pythonpath=("build-support",),
    )
    assert parsed == expected

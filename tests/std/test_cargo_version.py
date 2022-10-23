from kraken.std.cargo.version import git_version_to_cargo_version


def test__git_version_to_cargo_version() -> None:
    assert git_version_to_cargo_version("0.1.0", True) == "0.1.0"
    assert git_version_to_cargo_version("0.1.0", False) == "0.1.0"
    assert git_version_to_cargo_version("0.1.0-7-gabcdef", True) == "0.1.0-dev7+abcdef"
    assert git_version_to_cargo_version("0.1.0-7-gabcdef", False) == "0.1.0-dev7"
    assert git_version_to_cargo_version("0.1.0-7-gabcdef-dirty", True) == "0.1.0-dev7+abcdef"
    assert git_version_to_cargo_version("0.1.0-7-gabcdef-dirty", False) == "0.1.0-dev7"

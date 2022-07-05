from pathlib import Path

import pytest

from kraken.core.build_context import BuildContext
from kraken.core.project import Project

__version__ = "0.2.0"


@pytest.fixture
def context() -> BuildContext:
    return BuildContext(Path(".build"))


@pytest.fixture
def project(context: BuildContext) -> Project:
    context.root_project = Project("test", Path.cwd(), None, context)
    return context.root_project

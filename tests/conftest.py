from kraken.core.test import kraken_project  # noqa: F401

import contextlib
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from tests.std.utils.docker import DockerServiceManager


@pytest.fixture
def docker_service_manager() -> Iterator[DockerServiceManager]:
    with contextlib.ExitStack() as stack:
        yield DockerServiceManager(stack)


@pytest.fixture
def tempdir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tempdir:
        yield Path(tempdir)

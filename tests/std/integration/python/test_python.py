import logging
import os
import shutil
import unittest.mock
from pathlib import Path

import pytest
from kraken.core import Context
from kraken.core.util.helpers import not_none

from tests.std.utils.docker import DockerServiceManager

logger = logging.getLogger(__name__)
PYPISERVER_PORT = 23213
USER_NAME = "integration-test-user"
USER_PASS = "password-for-integration-test"


@pytest.fixture
def pypiserver(docker_service_manager: DockerServiceManager, tempdir: Path) -> str:

    # Create a htpasswd file for the registry.
    logger.info("Generating htpasswd for Pypiserver")
    htpasswd_content = not_none(
        docker_service_manager.run(
            "httpd:2",
            entrypoint="htpasswd",
            args=["-Bbn", USER_NAME, USER_PASS],
            capture_output=True,
        )
    )
    htpasswd = tempdir / "htpasswd"
    htpasswd.write_bytes(htpasswd_content)

    index_url = f"http://localhost:{PYPISERVER_PORT}/simple"
    docker_service_manager.run(
        "pypiserver/pypiserver:latest",
        ["--passwords", "/.htpasswd", "-a", "update"],
        ports=[f"{PYPISERVER_PORT}:8080"],
        volumes=[f"{htpasswd.absolute()}:/.htpasswd"],
        detach=True,
        probe=("GET", index_url),
    )
    logger.info("Started local Pypiserver at %s", index_url)
    return index_url


@pytest.mark.parametrize(
    "project_dir",
    [
        pytest.param(
            "poetry-project",
            marks=pytest.mark.xfail(
                reason="""
                    There appears to be an issue with Poetry 1.2.x and Pypiserver where the hashsums don't add up.
                    Example error messafge:

                        Retrieved digest for link poetry_project-0.1.0-py3-none-any.whl(md5:6340bed3198ccf181970f82cf6220f78)
                        not in poetry.lock metadata ['sha256:a2916a4e6ccb4c2f43f0ee9fb7fb1331962b9ec061f967c642fcfb9dbda435f3',
                        'sha256:80a47720d855408d426e835fc6088ed3aba2d0238611e16b483efe8e063d71ee']
                """  # noqa: E501
            ),
        ),
        "slap-project",
    ],
)
@unittest.mock.patch.dict(os.environ, {})
def test__python_project_install_lint_and_publish(
    project_dir: str,
    kraken_ctx: Context,
    tempdir: Path,
    pypiserver: str,
) -> None:
    consumer_dir = project_dir + "-consumer"

    # Copy the projects to the temporary directory.
    shutil.copytree(Path(__file__).parent / "data" / project_dir, tempdir / project_dir)
    shutil.copytree(Path(__file__).parent / "data" / consumer_dir, tempdir / consumer_dir)

    # TODO (@NiklasRosenstein): Make sure Poetry installs the environment locally so it gets cleaned up
    #       with the temporary directory.

    logger.info("Loading and executing Kraken project (%s)", tempdir / project_dir)
    os.environ["LOCAL_PACKAGE_INDEX"] = pypiserver
    os.environ["LOCAL_USER"] = USER_NAME
    os.environ["LOCAL_PASSWORD"] = USER_PASS
    kraken_ctx.load_project(directory=tempdir / project_dir)
    kraken_ctx.execute([":lint", ":publish"])

    # Try to run the "consumer" project.
    logger.info("Loading and executing Kraken project (%s)", tempdir / consumer_dir)
    Context.__init__(kraken_ctx, kraken_ctx.build_directory)
    kraken_ctx.load_project(directory=tempdir / consumer_dir)
    kraken_ctx.execute([":python.install"])
    # TODO (@NiklasRosenstein): Test importing the consumer project.

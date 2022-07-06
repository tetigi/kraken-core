""" Install additional dependencies into a Kraken build environment. """


from __future__ import annotations

import hashlib
import logging
import subprocess as sp
import sys
from pathlib import Path

import localimport

logger = logging.getLogger(__name__)


class PyenvManager:
    def __init__(self, lib_directory: Path) -> None:
        """Install any missing dependencies into a new location as per the project buildscript blocks."""

        self.lib_directory = lib_directory
        self.localimport = localimport.localimport(
            sys.path + [str(self.lib_directory.absolute())], do_autodisable=False
        )

    def install(self, pip_args: list[str]) -> None:
        if not pip_args:
            raise ValueError("no pip_args specified")

        hash_file = self.lib_directory / "lib.hash"

        command = ["pip", "install"] + pip_args
        command += ["--target", str(self.lib_directory)]

        command_hash = hashlib.md5("!:!".join(command).encode()).hexdigest()
        if self.lib_directory.exists() and hash_file.exists() and hash_file.read_text().strip() == command_hash:
            logger.info("Skip bootstrapping environment as it is already initialized.")
            return

        hash_file.parent.mkdir(parents=True, exist_ok=True)
        hash_file.write_text(command_hash)

        sp.check_call([sys.executable, "-m"] + command)

    def activate(self) -> None:
        self.localimport.__enter__()

    def deactivate(self) -> None:
        self.localimport.__exit__()

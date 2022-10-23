from __future__ import annotations

import subprocess as sp

from kraken.core import Property, Task, TaskStatus


class CargoFmtTask(Task):
    check: Property[bool] = Property.default(False)

    def execute(self) -> TaskStatus:
        command = ["cargo", "fmt"]
        if self.check.get():
            command += ["--check"]
        return TaskStatus.from_exit_code(command, sp.call(command, cwd=self.project.directory))

    def get_description(self) -> str | None:
        if self.check.get():
            return "Run `cargo fmt --check`."
        else:
            return "Run `cargo fmt`."

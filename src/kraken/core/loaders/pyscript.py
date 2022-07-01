""" Implements a loader for Python scripts. These Python scripts have access to importing certain build context
related members from the :mod:`kraken.api` module; note that these members are only available when imported in
the context of a script executed by this loader and not otherwise. """

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

from kraken.core.project import Project

from . import BuildScriptLoader

DEFAULT_FILE = Path("kraken.py")


class PyscriptLoader(BuildScriptLoader):
    def detect_in_project_directory(self, project_dir: Path) -> Path | None:
        file = project_dir / DEFAULT_FILE
        return file if file.is_file() else None

    def match_file(self, file: Path) -> bool | Path | None:
        return file.suffix == ".py"

    def load_script(self, file: Path, project: Project) -> None:
        module_name = "kraken.api"

        # Create the temporary replacement for the kraken.api module that the script will import from.
        module: Any = types.ModuleType(module_name)
        module.ctx = project.context
        module.project = project

        old_module = sys.modules.get(module_name)
        try:
            sys.modules[module_name] = module
            code = compile(file.read_text(), filename=file, mode="exec")
            exec(code, {"__file__": str(file), "__name__": project.name})
        finally:
            if old_module is None:
                sys.modules.pop(module_name)
            else:
                sys.modules[module_name] = old_module

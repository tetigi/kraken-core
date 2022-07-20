"""
This file serves as a proxy for Mypy type hints. Importing it in a normal Python script results in a
:class:`RuntimeError`, you can only import from this module when your code is loaded via the Pyscript loader.
"""

from kraken.core.context import Context
from kraken.core.project import Project

__version__ = "0.3.6"

ctx: Context
project: Project

raise RuntimeError(f"you cannot import from {__name__} directly; make sure your script is loaded by Kraken")

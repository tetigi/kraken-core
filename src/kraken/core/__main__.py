"""A simple CLI to execute a Kraken build. You should use the `kraken-cli` package instead, if possible."""

import argparse
from pathlib import Path

from kraken.core.context import Context

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("tasks", nargs="*")
parser.add_argument("-b", "--build-dir", metavar="PATH", type=Path, default=Path("build"))
parser.add_argument("-p", "--project-dir", metavar="PATH", type=Path, default=Path.cwd())


def main() -> None:
    args = parser.parse_args()
    ctx = Context(args.build_dir)
    ctx.load_project(directory=args.project_dir)
    ctx.execute(args.tasks or None)


if __name__ == "__main__":
    main()

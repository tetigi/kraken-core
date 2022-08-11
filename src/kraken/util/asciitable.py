from __future__ import annotations

import re
from typing import Iterator, Sequence, TextIO

from kraken._vendor.termcolor import colored

REGEX_ANSI_ESCAPE = re.compile(
    r"""
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
""",
    re.VERBOSE,
)


class AsciiTable:
    def __init__(self) -> None:
        self.headers: list[str] = []
        self.rows: list[Sequence[str]] = []

    def __iter__(self) -> Iterator[Sequence[str]]:
        yield self.headers
        yield from self.rows

    def print(self, fp: TextIO | None = None) -> None:
        widths = [
            max(len(REGEX_ANSI_ESCAPE.sub("", row[col_idx])) for row in self) for col_idx in range(len(self.headers))
        ]
        for row_idx, row in enumerate(self):
            if row_idx == 0:
                row = [colored(x.ljust(widths[col_idx]), attrs=["bold"]) for col_idx, x in enumerate(row)]
            else:
                row = [x.ljust(widths[col_idx]) for col_idx, x in enumerate(row)]
            if row_idx == 1:
                print("  ".join("-" * widths[idx] for idx in range(len(row))), file=fp)
            print("  ".join(row[idx].ljust(widths[idx]) for idx in range(len(row))), file=fp)

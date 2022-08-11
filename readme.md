# kraken-build

[![Python application](https://github.com/kraken-build/kraken-build/actions/workflows/python-package.yml/badge.svg)](https://github.com/kraken-build/kraken-build/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/kraken-build.svg)](https://badge.fury.io/py/kraken-build)

__The Kraken build system.__

Kraken focuses on ease of use and simplicity to model complex task orchestration workflows.

The **`kraken-build`** packages provides the _`kraken.core`_, _`kraken.cli`_ and _`kraken.util`_ top-level namespace
packages. Other Python packages may provide additional top-level packages in the _`kraken.`_ namespace.

## Quickstart

> This example requires the **`kraken-std`** package.

```py
# .kraken.py
from kraken.core import Project, Supplier
from kraken.std.generic.render_file_task import RenderFileTask
project = Project.current()
project.do(
    "renderDockerfile",
    RenderFileTask,
    file=project.build_directory / "Dockerfile",
    content=Supplier.of_callable(lambda: "FROM ubuntu:focal\n..."),
)
```

```
$ kraken run :renderDockerfile
[ ... ]
$ cat build/Dockerfile
FROM ubuntu:focal
...
```

## Reproducible build environments

The _`kraken`_ CLI provided by _`kraken.cli`_ executes in the same Python environment that the CLI was installed in.

We recommend you use the _`krakenw`_ command to achieve fully reproducible builds thanks to its lockfile support.
The _`krakenw`_ command can be installed via the **`kraken-wrapper`** package.

    $ pipx install kraken-wrapper

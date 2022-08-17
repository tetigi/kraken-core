# kraken-core

[![Python application](https://github.com/kraken-build/kraken-core/actions/workflows/python-package.yml/badge.svg)](https://github.com/kraken-build/kraken-core/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/kraken-core.svg)](https://badge.fury.io/py/kraken-core)

__The Kraken build system.__

Kraken focuses on ease of use and simplicity to model complex task orchestration workflows.

__Reproducible build environments__

We recommend that you use `krakenw` to invoke Kraken builds instead of the `kraken` cli directly to ensure that you
have an isolated and reproducible build environment. Install the kraken wrapper cli via the `kraken-wrapper` package
and define your build requirements at the top of your `.kraken.py` build script:

```
# ::requirements kraken-std>=0.3.0
from kraken.std.cargo import cargo_build
cargo_build()
```

__Vendored packages__

We're vendoring a number of third party packages for the purpose of reducing the burden of package resolution
at installation time. This is particularly relevant for using Kraken in continuous integration systems to improve
resolve times and PEX size.

* `networkx`
* `nr.io.graphviz`
* `nr.python.environment`
* `termcolor`
* `types-termcolor`
* `typeapi`

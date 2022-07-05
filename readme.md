# kraken-core

The `kraken.core` package provides the primitives of describing a build and deriving build tasks.

Aside from the `kraken.core` package, this package also provides the `kraken.api` module that is
used only at runtime by Kraken build scripts and the `kraken.testing` module for Pytest fixtures.

## How does it work?

Kraken uses **tasks** to describe units of work that can be chained and establish dependencies between each other.
Each task has a **schema** that defines its input and output properties. When an output property is linked to the
input property of another task, this established as dependency between the tasks.

```py
from kraken.std.docker_gen import generate_dockerfile
from kraken.std.docker_build import build_docker_image
dockerfile = generate_dockerfile(source_file="Dockerfile.yml")
build_docker_image(dockerfile=dockerfile.path, tags=["example:latest"], load=True)
```

This populates the project with two **tasks** and connects the computed output property of one to the other,
allowing the tasks that will run for `build_docker_image()` to pick up the dynamically generated Dockerfile that
is written into a location in the build directory by the `generate_dockerfile()` task.

<p align="center"><img src="assets/graph.png" height="225px"></p>

## Core API

Kraken **tasks** are described with a schema. Each schema field has a type and may be an input or output parameter.
Output parameters are only available once a resource is executed; Kraken will that a proper execution order is
established such that output properties are hydrated before another resource tries to access them as an input.

```py
from kraken.core.task import Context, Task, Property, Output, task_factory
from typing_extensions import Annotated

class GenerateDockerfileTask(Task):
    source_file: Property[str]
    path: Annotated[Property[str], Output]

    def execute(self, ctx: Context) -> None:
        path = Path(self.path.setdefault(str(ctx.build_directory / "Dockerfile")))
        path.write_text(render_dockerfile(Path(self.source_file.get()).read_text()))

generate_dockerfile = task_factory(GenerateDockerfileTask)
```

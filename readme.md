# kraken-core

[![Python application](https://github.com/kraken-build/kraken-core/actions/workflows/python-package.yml/badge.svg)](https://github.com/kraken-build/kraken-core/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/kraken-core.svg)](https://badge.fury.io/py/kraken-core)

The `kraken-core` package provides the primitives to describe a dependency graph for the purpose of task
orchestration.

__Packages__

* `kraken.api` &ndash; This module can be imported from in a `.kraken.py` build script to get access to the current
    build context and project.
* `kraken.core` &ndash; The core API that consists of primitives to describe tasks with dependencies, as well as
    Pytest fixtures.

## Concepts

* __Context__: The build context is the "root object" which contains a reference to the root project as well as
the path to a designated build directory. The context can hold metadata that is addressable globally by the Python
type (see `Context.metadata`).
* __Project__: A project represents a directory on the file system and tasks that are associated with the contents of
that directory and the build script loaded from it. A project's members are named and either `Task`s or other
`Project`s. A project is uniquely identified by it's "path" which is similar to a filesystem path only that the
separator is a colon (`:`). The root project is identifier with just a single colon, while members of a project are
identified by concatenating the project path with the member name (such as `:subproject:task`).
* __Task__: A task is a unit of work that can is related to a project. Tasks can have relationships to other tasks
that describe whether it needs to run before or after the related task. The relationship can also be strict (default)
or optional, in which case only the order of execution is informed. Tasks have properties that when passed to
properties of other tasks inform a strict dependency relationship.
* __Task factory__: A task factory is a function that is a convenient utility for Kraken build scripts to define one
or more tasks in a project. The `Project.do()` method in particular is often used to create task, allowing users to
conveniently set task property values directly instead of interfacing with the property API.
* __Group tasks__: Group tasks are a special kind of task that store a list of tasks as their dependencies, effectively
grouping the tasks under their name. There is some special treatment for group tasks when the task graph is constructed,
but otherwise they behave like normal tasks that don't actually do any work themselves. Every Kraken project always
has the following groups by default: `fmt`, `lint`, `build` and `test`.
* __Property__: A property is a typed container for a value. It can receive a static value or another task's property
to inform a strict dependency relationship between the property owners. Properties have a `.set(value)`, `.get()` and
`.get_or()` method.
* __Task graph__: The task graph represents a fully wired graph of the tasks in a *context*. The task graph must only
be constructed after `Context.finalize()` was called to allow tasks to perform one final update before nothing can be
changed anymore. After constructing a graph from a set of initially required tasks, it only contains the tasks that are
transitively required by the initial set. The graph can be further trimmed to remove weakly connected components of the
graph (such as group tasks if they were of the initial set or dependencies that are not strictly required by any other
task).

## Example

Check out the [`example/`](./example/) directory.

## Remarks for writing extensions

__Use `typing` aliases when defining Task properties for pre-3.10 compatibility__

The Kraken code base uses the 3.10+ type union operator `|` for type hints where possible. However, special care needs
to be taken with this operator when defining properties on Kraken tasks. The annotations on task objects are eveluated
and will cause errors in Python versions lower than 3.10 when using the union operator `|` even with
`__future__.annotations` enabled.

The following code will cause a `TypeError` when executed even when using `from __future__ import annotations`:

```py
class MyTask(Task):
    my_prop: Property[str | Path]  # unsupported operand type(s) for |: 'type' and 'type'
```

__Property value adapters__

Properties only support the types for which there is a value adapter registered. The default adapters registered in
the `kraken.core.property` module covert most use cases such as plain data types (`bool`, `int`, `float`, `str`,
`None`) and containers (`list`, `set`, `dict`) for which (not nested) type checking is implemented. Additionally, the
value adapter for `pathlib.Path` will allow a `str` to be passed and automatically convert it to a path.

Be aware that the order of the union members will play a role: A property declared as `Property[Union[Path, str]]`
will always coerce strings to paths, whereas a property declared as `Property[Union[str, Path]]` will accept a string
and not coerce it to a string.

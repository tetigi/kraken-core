# kraken-core

The kraken core API provides the primitives to fully describe complex build processes of software components.

## 1. Concepts

### 1.1 Projects

A project maps to a directory on the file system that represents a software component, usually
comprised of many different source code and supporting files, and eventually additional other
sub projects.

In every build there is at least one project involved, the root project. When tasks are referenced
by the full qualified name, the root project name is omitted from the path (similar to how the root
directory in a file system does not have a name and is represented by a single slash).

### 1.2 Tasks

A task is a logical unit of work that has a unique name within the project it is associated with. Tasks
can have dependencies on other tasks or groups of tasks, even across projects. When a task is optional,
it will only be executed if strictly required by another task.

Dependencies on task can be strict or non-strict. Non-strict dependencies enforce an order on the
execution sequence of tasks, wheras strict dependencies will ensure that the dependency has been
executed.

Tasks are usually marked as "default", meaning that they be selected by default if no explicit set of
tasks was selected to be executed.

### 1.4 Task selectors

Without any arguments, all default tasks are selected and executed. When an explicit selection is made,
it can be in one of the following forms:

1. A fully qualified project reference
2. A fully qualified task reference
3. A task name to select from all projects that contain it

Projects and tasks are structured hierarchally and fully qualified references are constructed like file system
paths but with colons instead of slashes. For example, `:` represents the root roject, `:foo:bar` references
task or project `bar` in project `foo` in the root project, `spam` references all tasks named `spam`.

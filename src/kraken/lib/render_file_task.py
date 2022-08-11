from __future__ import annotations

from pathlib import Path
from typing import Optional

from kraken._vendor.termcolor import colored
from kraken.core import Property, Supplier, Task, TaskStatus
from kraken.util.path import try_relative_to

DEFAULT_ENCODING = "utf-8"


class RenderFileTask(Task):
    """The RenderFileTask renders a single file to disk.

    The contents of the file can be provided by the :attr:`content` property or by creating a subclass
    that implements the :meth:`get_file_contents` method.

    It is a common pattern to have a separate task to validate the contents of the file are up to date
    with what the RenderFileTask would produce. This additional task can be created with the
    :meth:`make_check_task` helper method.

    It is common for a RenderFileTask to be added to the default `fmt` task group. The check task, should
    you create it, would be a good candidate to add to the default `check` group.
    """

    description = 'Create or update "%(file)s".'
    file: Property[Path]
    encoding: Property[str] = Property.default(DEFAULT_ENCODING)
    content: Property[str]

    _content_cache: Optional[bytes] = None

    def make_check_task(
        self,
        name: str | None = None,
        group: str = "check",
        default: bool = False,
        description: str | None = None,
    ) -> _CheckFileContentsTask:
        """Create a task that checks if the file that would be created or updated by the RenderFileTask would
        be modified. If the file would be modified, the check task will fail. By default, the new task name is
        the RenderFileTask's name appended with `.check`.

        :param name: The name of the check task.
        :param group: The group to attach the check group to.
        :param default: Whether the task runs by default.
        :param description: The description of the task.
        """

        task = self.project.do(
            name or (self.name + ".check"),
            _CheckFileContentsTask,
            default=default,
            group=group,
            # Use `Property.value` instead of the property directly to avoid creating a dependency between the
            # RenderFileTask and the check task.
            file=self.file.value,
            content=Supplier.of_callable(lambda: self.__get_file_contents_cached(), [self.content.value]),
            update_task=self.path,
        )

        task.description = description or 'Check if "%(file)s" is up to date.'
        task.add_relationship(self, strict=False)

        return task

    def get_file_contents(self, file: Path) -> str | bytes:
        """Return the content that should be written to *file*. The method may read the contents of *file* to
        take it into account, for example to produce a convoluted response (for example appending contents of the
        file that are missing).

        The default implementation returns the contents of the :attr:`content` property."""

        return self.content.get()

    def __get_file_contents_cached(self) -> bytes:
        """Internal. Caches the result of :meth:`get_file_contents`."""

        if self._content_cache is None:
            file = self.file.get()
            # Materialize the file contents.
            content = self.get_file_contents(file)
            if isinstance(content, str):
                self._content_cache = content.encode(self.encoding.get())
            else:
                self._content_cache = content

        return self._content_cache

    # Task

    def finalize(self) -> None:
        self.file.setmap(lambda path: self.project.directory / path)
        super().finalize()

    def prepare(self) -> TaskStatus | None:
        file = self.file.get()
        if file.is_file() and file.read_bytes() == self.__get_file_contents_cached():
            return TaskStatus.up_to_date()
        return TaskStatus.pending()

    def execute(self) -> TaskStatus:
        file = self.file.get()
        file.parent.mkdir(exist_ok=True)
        content = self.__get_file_contents_cached()
        file.write_bytes(content)
        return TaskStatus.succeeded(f"write {len(content)} bytes to {try_relative_to(file)}")


class _CheckFileContentsTask(Task):
    """Internal. Helper task to check the contents of a file."""

    file: Property[Path]
    content: Property[bytes]
    update_task_name: Property[str]

    def execute(self) -> TaskStatus | None:
        file = self.file.get()
        try:
            file = file.relative_to(Path.cwd())
        except ValueError:
            pass
        file_fmt = colored(str(file), "yellow", attrs=["bold"])
        uptask = colored(self.update_task_name.get(), "blue", attrs=["bold"])
        if not file.exists():
            return TaskStatus.failed(f'file "{file_fmt}" does not exist, run {uptask} to generate it')
        if not file.is_file():
            return TaskStatus.failed(f'"{file}" is not a file')
        if file.read_bytes() != self.content.get():
            return TaskStatus.failed(f'file "{file_fmt}" is not up to date, run {uptask} to update it')
        return None

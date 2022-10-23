from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from kraken.core import Project, Property
from kraken.core.lib.render_file_task import RenderFileTask

from ..gitignore import GitignoreFile, parse_gitignore, sort_gitignore


class GitignoreSyncTask(RenderFileTask):
    """This task ensures that a given set of entries are present in a `.gitignore` file.

    The :attr:`header` property can be set to place the paths below a particular comment in the `.gitignore` file. If
    there is no comment with the given text, it and the paths will be appended to the end of the file. When no header
    is specified, only missing paths will be added to beginning of the `.gitignore` file.

    If :attr:`sort` is enabled, the `.gitignore` file will be sorted (keeping paths grouped under their comments).

    It's common to group this task under the default `fmt` group, as it is similar to formatting a `.gitignore` file.
    """

    file: Property[Path] = Property.default(".gitignore")
    sort_paths: Property[bool] = Property.config(default=True)
    sort_groups: Property[bool] = Property.config(default=False)

    _paths: Dict[Optional[str], List[str]]

    def __init__(self, name: str, project: Project) -> None:
        super().__init__(name, project)
        self._paths = {}
        self.content.setcallable(lambda: self.get_file_contents(self.file.get()))

    def add_paths(self, header: str | None, paths: Sequence[str]) -> None:
        the_paths = self._paths.setdefault(header, [])
        the_paths[:] = set(list(the_paths) + list(paths))

    def get_file_contents(self, file: Path) -> str | bytes:
        if file.exists():
            gitignore = parse_gitignore(file)
        else:
            gitignore = GitignoreFile([])

        for comment_header, paths in self._paths.items():
            has_paths = set(gitignore.paths())

            if comment_header is not None:

                # Remove all existing paths, we'll make sure they're located under the header.
                for path in paths:
                    if path in has_paths:
                        gitignore.remove_path(path)
                        has_paths.discard(path)

                # Find the location of the header.
                insert_index = gitignore.find_comment(comment_header)
                if insert_index is None:
                    gitignore.add_blank()
                    gitignore.add_comment(comment_header)
                    insert_index = len(gitignore.entries)
                else:
                    insert_index += 1

            else:
                insert_index = 0

            for path in paths:
                if path not in has_paths:
                    gitignore.add_path(path, insert_index)
                    insert_index += 1

        gitignore = sort_gitignore(gitignore, self.sort_paths.get(), self.sort_groups.get())

        return gitignore.render()

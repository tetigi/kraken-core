from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, MutableMapping

import tomli
import tomli_w


@dataclass
class Pyproject(MutableMapping[str, Any]):
    _path: Path
    _data: dict[str, Any]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    @classmethod
    def read(cls, path: Path) -> Pyproject:
        with path.open("rb") as fp:
            return cls.of(path, tomli.load(fp))

    @classmethod
    def of(cls, path: Path, data: dict[str, Any]) -> Pyproject:
        return Pyproject(path, data)

    def to_json(self) -> dict[str, Any]:
        return self._data

    def to_toml_string(self) -> str:
        return tomli_w.dumps(self.to_json())

    def save(self, path: Path | None = None) -> None:
        path = path or self._path
        with path.open("wb") as fp:
            tomli_w.dump(self.to_json(), fp)

    def get_poetry_sources(self) -> list[dict[str, Any]]:
        return list(self.setdefault("tool", {}).setdefault("poetry", {}).setdefault("source", []))

    def delete_poetry_source(self, source_name: str) -> None:
        sources_conf = self.setdefault("tool", {}).setdefault("poetry", {}).setdefault("source", [])
        index = next((i for i, v in enumerate(sources_conf) if v["name"] == source_name), None)
        if index is None:
            raise KeyError(source_name)
        del sources_conf[index]

    def upsert_poetry_source(self, source_name: str, url: str, default: bool = False, secondary: bool = False) -> None:
        source_config: dict[str, Any] = {"name": source_name, "url": url}
        if default:
            source_config["default"] = True
        if secondary:
            source_config["secondary"] = True
        sources_conf = self.setdefault("tool", {}).setdefault("poetry", {}).setdefault("source", [])

        # Find the source with the same name and update it, or create a new one.
        source = next((x for x in sources_conf if x["name"] == source_name), None)
        if source is None:
            sources_conf.append(source_config)
        else:
            source.update(source_config)

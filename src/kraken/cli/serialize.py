from __future__ import annotations

import logging
import uuid
from pathlib import Path

import dill  # type: ignore[import]

from kraken.core import Context, TaskGraph
from kraken.util.text import pluralize

logger = logging.getLogger(__name__)


def load_build_state(state_dir: Path) -> tuple[Context, TaskGraph] | tuple[None, None]:
    state_files = list(state_dir.iterdir()) if state_dir.is_dir() else []
    if not state_files:
        return None, None
    logger.info(
        "Resuming from %d build %s (%s)",
        len(state_files),
        pluralize("state", state_files),
        ", ".join(file.name for file in state_files),
    )
    context: Context | None = None
    graph: TaskGraph | None = None
    for state_file in sorted(state_files):
        with state_file.open("rb") as fp:
            new_graph: TaskGraph = dill.load(fp)
        if context is None or graph is None:
            context, graph = new_graph.context, new_graph
        else:
            graph.update_statuses_from(new_graph)
    assert context is not None and graph is not None
    return context, graph


def save_build_state(state_dir: Path, graph: TaskGraph) -> None:
    state_file = state_dir / f"state-{str(uuid.uuid4())[:7]}.dill"
    state_dir.mkdir(parents=True, exist_ok=True)
    with state_file.open("wb") as fp:
        dill.dump(graph, fp)
    for file in state_dir.iterdir():
        if file != state_file:
            file.unlink()
    logger.info('Saving build state to "%s"', state_file)

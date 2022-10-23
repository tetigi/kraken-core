# ::dialect dsl
# type: ignore

from kraken.std.docker import build_docker_image
from kraken.core.lib.render_file_task import RenderFileTask

do "docker.file" RenderFileTask
    content: "FROM ubuntu:focal\nRUN echo Hello world\n"
    file: build_directory / "Dockerfile"

build_docker_image
    name: "docker.build"
    dockerfile: task("docker.file").file
    tags: ["kraken-example"]
    load: True

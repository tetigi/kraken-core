# ::dialect dsl
# ::pythonpath .
# type: ignore

from my_tasks import DockerBuildTask, WriteDockerfileTask
from textwrap import dedent

do "docker.file" WriteDockerfileTask content: dedent("""
    FROM ubuntu:latest
    RUN echo Hello World
    """)

do "docker.build" DockerBuildTask
    dockerfile: task("docker.file").dockerfile

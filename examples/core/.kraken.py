# ::pythonpath .

from my_tasks import DockerBuildTask, WriteDockerfileTask
from kraken.core import Project

project = Project.current()
dockerfile = project.do("docker.file", WriteDockerfileTask, content="FROM ubuntu:latest\nRUN echo Hello World")
project.do("docker.build", DockerBuildTask, dockerfile=dockerfile.dockerfile)

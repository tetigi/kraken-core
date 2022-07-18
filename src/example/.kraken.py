from my_tasks import DockerBuildTask, WriteDockerfileTask

from kraken.api import project

dockerfile = project.do("writeDockerfile", WriteDockerfileTask, content="FROM ubuntu:latest\nRUN echo Hello World")
project.do("dockerBuild", DockerBuildTask, dockerfile=dockerfile.dockerfile)

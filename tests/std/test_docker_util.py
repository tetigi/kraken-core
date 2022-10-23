from textwrap import dedent

from kraken.std.docker.util import update_run_commands


def test__update_run_commands() -> None:
    dockerfile = dedent(
        """
        FROM alpine
        RUN echo hello
        """
    ).strip()
    updated = dedent(
        """
        FROM alpine
        RUN %% echo hello %%
        """
    ).strip()
    assert update_run_commands(dockerfile, prefix="%% ", suffix=" %%") == updated


def test__update_run_commands__supports_multiline_run_command() -> None:
    dockerfile = dedent(
        """
        FROM alpine
        RUN echo hello \\
            && goodbye
        """
    ).strip()
    updated = dedent(
        """
        FROM alpine
        RUN %% echo hello \\
            && goodbye %%
        """
    ).strip()
    assert update_run_commands(dockerfile, prefix="%% ", suffix=" %%") == updated


def test__update_run_commands__supports_multiline_run_command_with_comments() -> None:
    dockerfile = dedent(
        """
        FROM alpine
        RUN echo hello \\
            # This says goodbye
            && echo goodbye
        """
    ).strip()
    updated = dedent(
        """
        FROM alpine
        RUN %% echo hello \\
            # This says goodbye
            && echo goodbye %%
        """
    ).strip()
    assert update_run_commands(dockerfile, prefix="%% ", suffix=" %%") == updated

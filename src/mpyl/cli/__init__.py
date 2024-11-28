"""Command Line Interface parsing for MPyL"""

import logging
import os
from rich.console import Console
from rich.logging import RichHandler

CONFIG_PATH_HELP = "Path to the config.yml. Can be set via `MPYL_CONFIG_PATH` env var. "


def create_console_logger(show_path: bool) -> Console:
    console = Console(
        markup=False,
        no_color=False,
        log_path=False,
        log_time=False,
    )
    verbose = os.environ.get("RUNNER_DEBUG", "0") == "1"
    log_level = "DEBUG" if verbose else "INFO"
    print(f"Log level is set to {log_level}")
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(markup=False, console=console, show_path=show_path)],
    )
    return console

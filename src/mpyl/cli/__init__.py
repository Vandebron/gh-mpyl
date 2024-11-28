"""Command Line Interface parsing for MPyL"""

import logging
import os
from rich.console import Console
from rich.logging import RichHandler

CONFIG_PATH_HELP = "Path to the config.yml. Can be set via `MPYL_CONFIG_PATH` env var. "


def create_console_logger(show_path: bool = False) -> Console:
    console = Console(
        markup=False,
        log_path=show_path,
        log_time=False,
        force_terminal=True,
        width=999,
    )
    verbose = os.environ.get("RUNNER_DEBUG", "0") == "1"
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=show_path)],
    )
    return console

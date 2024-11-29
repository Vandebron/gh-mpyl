"""Command Line Interface parsing for MPyL"""

import logging
import os
from rich.console import Console
from rich.logging import RichHandler

CONFIG_PATH_HELP = "Path to the config.yml. Can be set via `MPYL_CONFIG_PATH` env var. "


def create_console_logger() -> Console:
    verbose = os.environ.get("RUNNER_DEBUG", "0") == "1"
    level = "DEBUG" if verbose else "INFO"
    console = Console(
        markup=False,
        log_path=False,
        log_time=False,
        force_terminal=True,
        color_system="truecolor",
        width=999,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        # handlers=[RichHandler(console=console, show_path=verbose)],
        handlers=[RichHandler(level=level, show_path=verbose)],
    )
    return console

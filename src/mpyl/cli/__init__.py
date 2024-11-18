"""Command Line Interface parsing for MPyL"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

CONFIG_PATH_HELP = "Path to the config.yml. Can be set via `MPYL_CONFIG_PATH` env var. "


@dataclass(frozen=True)
class MpylCliParameters:
    tag: Optional[str] = None
    stage: Optional[str] = None
    projects: Optional[str] = None
    deploy_image: Optional[str] = None


FORMAT = "%(message)s"


def create_console_logger(show_path: bool, max_width: Optional[int] = None) -> Console:
    console = Console(
        markup=True,
        width=max_width if (max_width is not None and max_width > 0) else None,
        no_color=False,
        log_path=False,
        log_time=False,
        color_system="256",
    )
    verbose = os.environ.get("RUNNER_DEBUG", "0") == "1"
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO",
        format=FORMAT,
        datefmt="[%X]",
        handlers=[RichHandler(markup=True, console=console, show_path=show_path)],
    )
    return console

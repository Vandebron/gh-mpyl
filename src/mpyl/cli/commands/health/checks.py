"""Health checks"""

import os
import pkgutil
from pathlib import Path
from typing import Optional

import click
import jsonschema
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

from ....constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
)
from ....utilities.pyaml_env import parse_config
from ....validation import validate


class HealthConsole:
    def __init__(self, console: Console):
        self.console = console
        self.failure = False

    def title(self, title: str):
        self.console.print(Markdown(f"*{title}*"))

    def check(self, check: str, success: bool):
        if not success:
            self.failure = True
        icon = "✅" if success else "❌"
        self.console.print(Markdown(f"&nbsp;&nbsp;{icon} {check}"))

    def print(self, text: str):
        self.console.print(Markdown(text))


def perform_health_checks(bare_console: Console):
    console = HealthConsole(bare_console)
    load_dotenv(Path(".env"))

    console.title("Run configuration")
    if properties_path := __validate_config_path(
        console,
        env_var="MPYL_RUN_PROPERTIES_PATH",
        default=DEFAULT_RUN_PROPERTIES_FILE_NAME,
        config_name="run properties",
    ):
        _validate_config(
            console,
            config_file_path=properties_path,
            schema_path="../../../schema/run_properties.schema.yml",
        )

    console.title("MPyL configuration")
    if config_path := __validate_config_path(
        console,
        env_var="MPYL_CONFIG_PATH",
        default=DEFAULT_CONFIG_FILE_NAME,
        config_name="config",
    ):
        _validate_config(
            console,
            config_file_path=config_path,
            schema_path="../../../schema/mpyl_config.schema.yml",
        )

    if console.failure:
        raise click.ClickException("Health check failed")


def __validate_config_path(
    console: HealthConsole, env_var: str, default: str, config_name: str
) -> Optional[Path]:
    path_env = os.environ.get(env_var)
    path = Path(path_env or default)
    location = (
        f"{config_name} at `{path}` via environment variable `{env_var}`"
        if path_env
        else f"{config_name} at `{path}`"
    )
    if os.path.exists(path):
        console.check(f"Found {location}", success=True)
        return path

    console.check(
        f"Could not find {location}. Location can be specified with env var '{env_var}'",
        success=False,
    )
    return None


def _validate_config(
    console: HealthConsole,
    config_file_path: Path,
    schema_path: str,
):
    if load_dotenv(Path(".env")):
        console.check("Set env variables via .env file", success=True)

    parsed = parse_config(config_file_path)
    schema_dict = pkgutil.get_data(__name__, schema_path)
    if schema_dict:
        try:
            validate(parsed, schema_dict.decode("utf-8"))
            console.check(f"{config_file_path} is valid", success=True)
        except jsonschema.exceptions.ValidationError as exc:
            console.check(
                f"{config_file_path} is invalid: {exc.message} at '{'.'.join(map(str, exc.path))}'",
                success=False,
            )

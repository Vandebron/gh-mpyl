"""Health checks"""

import asyncio
import os
import pkgutil
from pathlib import Path
from typing import Optional

import jsonschema
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

from ....cli import get_latest_publication, get_meta_version
from ....constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
    DEFAULT_STAGES_SCHEMA_FILE_NAME,
    ROOT_PATH,
)
from ....utilities.pyaml_env import parse_config
from ....validation import validate


class HealthConsole:
    def __init__(self, console: Console):
        self.console = console

    def title(self, title: str):
        self.console.print(Markdown(f"*{title}*"))

    def check(self, check: str, success: bool):
        icon = "✅" if success else "❌"
        self.console.print(Markdown(f"&nbsp;&nbsp;{icon} {check}"))

    def print(self, text: str):
        self.console.print(Markdown(text))


def perform_health_checks(bare_console: Console):
    console = HealthConsole(bare_console)
    load_dotenv(Path(".env"))

    console.title("Version")
    __check_version(console)

    console.title("Run configuration")
    properties_schema_path = Path(
        os.environ.get("MPYL_RUN_PROPERTIES_PATH") or DEFAULT_RUN_PROPERTIES_FILE_NAME
    )

    stages_schema = properties_schema_path.parent / DEFAULT_STAGES_SCHEMA_FILE_NAME
    stages_schema_exists = Path(stages_schema).exists()
    if not stages_schema_exists:
        console.check(
            f"{stages_schema} does not exist. See _Stage configuration_ in documentation for an example.",
            False,
        )
    else:
        console.check(f"{stages_schema} is present", True)

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


def __check_version(console):
    update = asyncio.get_event_loop().run_until_complete(get_latest_publication())
    meta_version = get_meta_version()
    if update and meta_version:
        if meta_version == update:
            console.check(f"At latest version: {update}", success=True)
        else:
            console.check(
                f"Outdated version: {meta_version} (latest: {update})", success=False
            )
    else:
        console.check("Could not determine latest version", success=False)


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


# root_dir is necessary because we load mpyl_stages.schema.yml dynamically (but only on tests?!)
# It would be good to move mpyl_stages back to src/mpyl/schemas (next to the other schemas) and simplify this
def _validate_config(
    console: HealthConsole,
    config_file_path: Path,
    schema_path: str,
    root_dir: Path = Path(ROOT_PATH),
):
    if load_dotenv(Path(".env")):
        console.check("Set env variables via .env file", success=True)

    parsed = parse_config(config_file_path)
    schema_dict = pkgutil.get_data(__name__, schema_path)
    if schema_dict:
        try:
            validate(parsed, schema_dict.decode("utf-8"), root_dir=root_dir)
            console.check(f"{config_file_path} is valid", success=True)
        except jsonschema.exceptions.ValidationError as exc:
            console.check(
                f"{config_file_path} is invalid: {exc.message} at '{'.'.join(map(str, exc.path))}'",
                success=False,
            )

"""Commands related to plan"""

from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console

from . import CONFIG_PATH_HELP
from . import create_console_logger
from ..constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
)
from ..project import Stage, Target
from ..run_plan import create_run_plan, print_run_plan
from ..steps.models import ConsoleProperties
from ..steps.run_properties import construct_run_properties, validate_run_properties
from ..utilities.pyaml_env import parse_config


@dataclass(frozen=True)
class Context:
    run_properties: dict
    config: dict
    console: Console = create_console_logger(show_path=False, max_width=0)


@click.group("plan")
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help=CONFIG_PATH_HELP,
    envvar="MPYL_CONFIG_PATH",
    default=DEFAULT_CONFIG_FILE_NAME,
)
@click.option(
    "--properties",
    "-p",
    required=False,
    type=click.Path(exists=False),
    help="Path to run properties",
    envvar="MPYL_RUN_PROPERTIES_PATH",
    default=DEFAULT_RUN_PROPERTIES_FILE_NAME,
    show_default=True,
)
@click.pass_context
def plan(ctx, config, properties):
    """Pipeline build commands"""
    parsed_properties = parse_config(properties)
    parsed_config = parse_config(config)

    console_config = ConsoleProperties.from_configuration(ctx.run_properties)
    console = create_console_logger(
        show_path=console_config.show_paths,
        max_width=console_config.width,
    )
    ctx.obj = Context(
        run_properties=parsed_properties, config=parsed_config, console=console
    )


@click.command("create")
@click.option("--tag", "-t", help="Tag to build", type=click.STRING, required=False)
@click.pass_obj
def create_plan(ctx: Context, tag: str):
    changed_files_path = ctx.config["vcs"]["changedFilesPath"]
    if not Path(changed_files_path).exists():
        raise ValueError(
            "Unable to calculate run plan without a changed files JSON file."
        )

    run_properties = construct_run_properties(
        target=Target.PULL_REQUEST,  # FIXME
        config=ctx.config,
        properties=ctx.run_properties,
        tag=tag,
    )

    create_run_plan(
        console=ctx.console,
        changed_files_path=changed_files_path,
        revision=run_properties.versioning.revision,
        all_projects=run_properties.projects,
        all_stages=run_properties.stages,
    )


@click.command("print")
@click.pass_obj
def print_plan(ctx: Context):
    validate_run_properties(ctx.run_properties)

    print_run_plan(
        console=ctx.console,
        all_stages=[
            Stage(stage["name"], stage["icon"])
            for stage in ctx.run_properties["stages"]
        ],
    )

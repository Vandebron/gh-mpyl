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
from ..project import Stage
from ..run_plan import discover_run_plan, RunPlan
from ..steps.models import ConsoleProperties, RunProperties
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

    RunProperties.validate(parsed_properties)

    console_config = ConsoleProperties.from_configuration(parsed_properties)
    console = create_console_logger(
        show_path=console_config.show_paths,
        max_width=console_config.width,
    )
    ctx.obj = Context(
        run_properties=parsed_properties, config=parsed_config, console=console
    )


@plan.command("create")
@click.pass_obj
def create_plan(ctx: Context):
    changed_files_path = Path(ctx.config["vcs"]["changedFilesPath"])
    if not changed_files_path.is_dir():
        raise ValueError(
            f"Unable to calculate run plan because {changed_files_path} is not a directory"
        )

    all_stages = [
        Stage(stage["name"], stage["icon"]) for stage in ctx.run_properties["stages"]
    ]

    run_plan = discover_run_plan(
        revision=ctx.run_properties["build"]["versioning"]["revision"],
        all_stages=all_stages,
        changed_files_path=changed_files_path,
    )

    run_plan.write_to_pickle_file()
    run_plan.write_to_json_file()
    run_plan.print_markdown(ctx.console, all_stages)


@plan.command("print")
@click.pass_obj
def print_plan(ctx: Context):
    all_stages = [
        Stage(stage["name"], stage["icon"]) for stage in ctx.run_properties["stages"]
    ]
    run_plan = RunPlan.load_from_pickle_file(selected_project=None, selected_stage=None)
    run_plan.print_markdown(ctx.console, all_stages)

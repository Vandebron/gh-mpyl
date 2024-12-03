"""Commands related to plan"""

import logging
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown

from . import CONFIG_PATH_HELP
from . import create_console_logger
from ..constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
)
from ..project import Stage
from ..run_plan import discover_run_plan, RunPlan
from ..steps.models import RunProperties
from ..utilities.pyaml_env import parse_config


@dataclass(frozen=True)
class Context:
    run_properties: dict
    config: dict
    console: Console = create_console_logger()


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

    ctx.obj = Context(
        run_properties=parsed_properties,
        config=parsed_config,
        console=create_console_logger(),
    )


@plan.command("create")
@click.option(
    "--project",
    "-p",
    type=click.STRING,
    required=False,
    help="Limit the run plan to only this project",
)
@click.pass_obj
def create_plan(ctx: Context, project):
    changed_files_path = Path(ctx.config["vcs"]["changedFilesPath"])
    if not changed_files_path.is_dir():
        raise ValueError(
            f"Unable to calculate run plan because {changed_files_path} is not a directory"
        )

    logger = logging.getLogger("mpyl")
    run_plan = discover_run_plan(
        logger=logger,
        revision=ctx.run_properties["build"]["versioning"]["revision"],
        all_stages=[
            Stage(stage["name"], stage["icon"])
            for stage in ctx.run_properties["stages"]
        ],
        changed_files_path=changed_files_path,
    )

    if project != "":
        run_plan = run_plan.select_project(project)
        logger.info(f"Selected project: {project}")

    run_plan.write_to_pickle_file()
    run_plan.write_to_json_file()
    ctx.console.print(Markdown(run_plan.to_markdown()))


@plan.command("print")
@click.pass_obj
def print_plan(ctx: Context):
    run_plan = RunPlan.load_from_pickle_file()
    ctx.console.print(Markdown(run_plan.to_markdown()))

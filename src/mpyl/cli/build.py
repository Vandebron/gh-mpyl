"""Commands related to build"""

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console

from . import CONFIG_PATH_HELP
from . import create_console_logger
from ..build import run_mpyl
from ..constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
    RUN_ARTIFACTS_FOLDER,
    RUN_RESULT_FILE_GLOB,
)
from ..project import load_project, Target
from ..run_plan import RunPlan
from ..stages.discovery import find_projects
from ..steps import deploy
from ..steps.models import ConsoleProperties, RunProperties
from ..utilities.pyaml_env import parse_config
from ..validation import validate_run_properties


@dataclass(frozen=True)
class Context:
    target: Target
    config: dict
    console: Console
    run_properties: dict


@click.group("build")
@click.option(
    "--environment",
    "-e",
    required=True,
    type=click.Choice(["pull-request", "test", "acceptance", "production"]),
    help="The environment to deploy to",
)
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
def build(ctx, environment, config, properties):
    """Pipeline build commands"""
    parsed_properties = parse_config(properties)
    validate_run_properties(parsed_properties)

    console_config = ConsoleProperties.from_configuration(parsed_properties)
    console = create_console_logger(
        show_path=console_config.show_paths,
        max_width=console_config.width,
    )

    ctx.obj = Context(
        target=Target.from_environment(environment),
        config=parse_config(config),
        console=console,
        run_properties=parsed_properties,
    )


class CustomValidation(click.Command):
    def invoke(self, ctx):
        selected_stage = ctx.params.get("stage")
        stages = [stage["name"] for stage in ctx.obj.run_properties["stages"]]

        if selected_stage and selected_stage not in stages:
            raise click.ClickException(
                message=f"Stage {ctx.params.get('stage')} is not defined in the configuration."
            )

        super().invoke(ctx)


@build.command(help="Run an MPyL build", cls=CustomValidation)
@click.option(
    "--stage", default=None, type=click.STRING, required=True, help="Stage to run"
)
@click.option(
    "--projects",
    "-p",
    type=click.STRING,
    required=True,
    help="Comma separated list of the projects to build",
)
@click.option(
    "--image", type=click.STRING, required=False, help="Docker image to deploy"
)
@click.pass_obj
def run(
    obj: Context,
    stage,
    projects,
    image,
):  # pylint: disable=invalid-name
    run_result_files = list(Path(RUN_ARTIFACTS_FOLDER).glob(RUN_RESULT_FILE_GLOB))
    for run_result_file in run_result_files:
        run_result_file.unlink()

    if image:
        if not stage or not projects:
            raise click.ClickException(
                message="Need to pass stage and project when passing an image"
            )
        if stage != deploy.STAGE_NAME:
            raise click.ClickException(
                message="Images can only be passed when selecting the deploy stage"
            )
        if len(projects.split(",")) != 1:
            raise click.ClickException(
                message="Need to pass exactly one project to deploy when passing an image"
            )

    run_properties = RunProperties.from_configuration(
        target=obj.target,
        run_properties=obj.run_properties,
        config=obj.config,
        deploy_image=image,
    )

    run_plan = RunPlan.load_from_pickle_file(
        selected_stage=run_properties.selected_stage(stage),
        selected_projects=run_properties.selected_projects(projects),
    )

    run_result = run_mpyl(
        console_properties=ConsoleProperties.from_configuration(obj.run_properties),
        run_properties=run_properties,
        run_plan=run_plan,
    )

    run_result.write_to_pickle_file()
    sys.exit(0 if run_result.is_success else 1)


@build.command(help=f"Clean all MPyL metadata in `{RUN_ARTIFACTS_FOLDER}` folders")
@click.pass_obj
def clean(obj: Context):
    artifacts_path = Path(RUN_ARTIFACTS_FOLDER)
    if artifacts_path.is_dir():
        shutil.rmtree(artifacts_path)
        obj.console.print(f"🧹 Cleaned up {artifacts_path}")

    found_projects: list[Path] = [
        Path(load_project(project_path, validate_project_yaml=False).target_path)
        for project_path in find_projects()
    ]

    paths_to_clean = [path for path in found_projects if path.exists()]
    if paths_to_clean:
        for target_path in set(paths_to_clean):
            shutil.rmtree(target_path)
            obj.console.print(f"🧹 Cleaned up {target_path}")
    else:
        obj.console.print("Nothing to clean")

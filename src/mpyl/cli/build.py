"""Commands related to build"""

import asyncio
import pickle
import shutil
import sys
import uuid
from pathlib import Path

import click

from . import (
    CliContext,
    CONFIG_PATH_HELP,
    MpylCliParameters,
)
from . import create_console_logger
from ..build import print_status, run_mpyl
from ..constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
    RUN_ARTIFACTS_FOLDER,
    RUN_RESULT_FILE_GLOB,
)
from ..project import load_project
from ..stages.discovery import find_projects
from ..steps import deploy
from ..steps.run_properties import construct_run_properties
from ..utilities.pyaml_env import parse_config


@click.group("build")
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
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    show_default=True,
    help="Verbose output",
)
@click.pass_context
def build(ctx, config, properties, verbose):
    """Pipeline build commands"""
    parsed_properties = parse_config(properties)
    parsed_config = parse_config(config)
    console_config = construct_run_properties(
        properties=parsed_properties,
        config=parsed_config,
    ).console
    console = create_console_logger(
        show_path=console_config.show_paths,
        verbose=verbose,
        max_width=console_config.width,
    )

    ctx.obj = CliContext(parsed_config, console, verbose, parsed_properties)


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
@click.option("--tag", "-t", help="Tag to build", type=click.STRING, required=False)
@click.option(
    "--stage", default=None, type=click.STRING, required=False, help="Stage to run"
)
@click.option(
    "--projects",
    "-p",
    type=click.STRING,
    required=False,
    help="Comma separated list of the projects to build",
)
@click.option(
    "--image", type=click.STRING, required=False, help="Docker image to deploy"
)
@click.pass_obj
def run(
    obj: CliContext,
    tag,
    stage,
    projects,
    image,
):  # pylint: disable=invalid-name
    run_result_files = list(Path(RUN_ARTIFACTS_FOLDER).glob(RUN_RESULT_FILE_GLOB))
    for run_result_file in run_result_files:
        run_result_file.unlink()

    if image:
        if stage != deploy.STAGE_NAME:
            raise click.ClickException(
                message="Images can only be passed when deploying"
            )
        if len(projects) != 1:
            raise click.ClickException(
                message="Need to pass exactly one project to deploy when passing an image"
            )

    parameters = MpylCliParameters(
        verbose=obj.verbose, tag=tag, stage=stage, projects=projects, deploy_image=image
    )
    obj.console.log(parameters)

    run_properties = construct_run_properties(
        config=obj.config,
        properties=obj.run_properties,
        cli_parameters=parameters,
    )
    run_result = run_mpyl(run_properties=run_properties, cli_parameters=parameters)

    Path(RUN_ARTIFACTS_FOLDER).mkdir(parents=True, exist_ok=True)
    run_result_file = Path(RUN_ARTIFACTS_FOLDER) / f"run_result-{uuid.uuid4()}.pickle"
    with open(run_result_file, "wb") as file:
        pickle.dump(run_result, file, pickle.HIGHEST_PROTOCOL)

    sys.exit(0 if run_result.is_success else 1)


@build.command(help="The status of the current local branch from MPyL's perspective")
@click.option(
    "--projects",
    "-p",
    type=click.STRING,
    required=False,
    help="Comma separated list of the projects to build",
)
@click.option(
    "--stage",
    default=None,
    type=click.STRING,
    required=False,
    help="Stage to get status for",
)
@click.option("--tag", "-t", help="Tag to build", type=click.STRING, required=False)
@click.option("--explain", "-e", is_flag=True, help="Explain the current run plan")
@click.pass_obj
def status(obj: CliContext, projects, stage, tag, explain):
    try:
        parameters = MpylCliParameters(projects=projects, stage=stage, tag=tag)
        print_status(obj, parameters, explain)
    except asyncio.exceptions.TimeoutError:
        pass


@build.command(help=f"Clean all MPyL metadata in `{RUN_ARTIFACTS_FOLDER}` folders")
@click.pass_obj
def clean(obj: CliContext):
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

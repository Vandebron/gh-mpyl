"""Commands related to build"""

import datetime
import logging
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click
from jsonschema import ValidationError
from rich.console import Console
from rich.markdown import Markdown

from . import CONFIG_PATH_HELP
from . import create_console_logger
from ..build import run_deploy_stage
from ..constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
    RUN_ARTIFACTS_FOLDER,
    RUN_RESULT_FILE_GLOB,
)
from ..project import load_project, Target
from ..plan.discovery import find_projects
from ..run_plan import RunPlan
from ..steps.models import RunProperties
from ..steps.run import RunResult
from ..utilities.pyaml_env import parse_config


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
def build(ctx, environment: str, config: Path, properties: Path):
    """Pipeline build commands"""
    parsed_properties = parse_config(properties)
    RunProperties.validate(parsed_properties)

    ctx.obj = Context(
        target=Target.from_environment(environment),
        config=parse_config(config),
        console=create_console_logger(),
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
    "--project",
    "-p",
    type=click.STRING,
    required=True,
    help="The project to run",
)
@click.option(
    "--image", type=click.STRING, required=False, help="Docker image to deploy"
)
@click.pass_obj
def run(obj: Context, project: str, image: Optional[str]):
    run_result_files = list(Path(RUN_ARTIFACTS_FOLDER).glob(RUN_RESULT_FILE_GLOB))
    for run_result_file in run_result_files:
        run_result_file.unlink()

    run_properties = RunProperties.from_configuration(
        target=obj.target,
        run_properties=obj.run_properties,
        config=obj.config,
        deploy_image=image,
    )

    run_result = _run_stage(
        console=obj.console,
        run_properties=run_properties,
        project_name_to_run=project,
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


def _run_stage(
    console: Console,
    run_properties: RunProperties,
    project_name_to_run: str,
) -> RunResult:
    logger = logging.getLogger("mpyl")
    start_time = time.time()
    try:
        run_plan = RunPlan.load_from_pickle_file()
        console.print(Markdown(run_plan.to_markdown()))

        run_result = run_deploy_stage(
            logger=logger,
            run_properties=run_properties,
            run_plan=run_plan,
            project_name_to_run=project_name_to_run,
        )

        console.log(
            f"Completed in {datetime.timedelta(seconds=time.time() - start_time)}"
        )
        console.print(Markdown(run_result.to_markdown()))
        return run_result

    except ValidationError as exc:
        console.log(
            f'Schema validation failed {exc.message} at `{".".join(map(str, exc.path))}`'
        )
        raise exc

    except Exception as exc:
        console.log(f"Unexpected exception: {exc}")
        console.print_exception()
        raise exc

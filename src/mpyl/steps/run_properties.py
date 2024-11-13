"""Module to initiate run properties"""

import logging
from typing import Optional

from ..cli import MpylCliParameters
from ..project import load_project, Stage, Project, Target
from ..stages.discovery import create_run_plan, find_projects
from ..steps.models import RunProperties


def construct_run_properties(
    target: Target,
    config: dict,
    properties: dict,
    cli_parameters: MpylCliParameters = MpylCliParameters(),
    explain_run_plan: bool = False,
) -> RunProperties:
    all_projects = set(
        map(
            lambda p: load_project(
                project_path=p, validate_project_yaml=False, log=True
            ),
            find_projects(),
        )
    )

    run_plan_logger = logging.getLogger("mpyl")
    if explain_run_plan:
        run_plan_logger.setLevel("DEBUG")

    run_plan = _create_run_plan(
        cli_parameters=cli_parameters,
        all_projects=all_projects,
        all_stages=[
            Stage(stage["name"], stage["icon"]) for stage in properties["stages"]
        ],
        explain_run_plan=explain_run_plan,
        changed_files_path=config["vcs"].get("changedFilesPath", None),
        revision=properties["build"]["versioning"]["revision"],
    )

    return RunProperties.from_configuration(
        target=target,
        run_properties=properties,
        config=config,
        run_plan=run_plan,
        all_projects=all_projects,
        cli_tag=cli_parameters.tag or properties["build"]["versioning"].get("tag"),
        deploy_image=cli_parameters.deploy_image,
    )


def _create_run_plan(
    cli_parameters: MpylCliParameters,
    all_projects: set[Project],
    all_stages: list[Stage],
    explain_run_plan: bool,
    revision: str,
    changed_files_path: Optional[str] = None,
):
    run_plan_logger = logging.getLogger("mpyl")
    if explain_run_plan:
        run_plan_logger.setLevel("DEBUG")

    if cli_parameters.stage:
        selected_stage = next(
            (stage for stage in all_stages if stage.name == cli_parameters.stage), None
        )
    else:
        selected_stage = None

    if cli_parameters.projects:
        selected_projects = {
            p for p in all_projects if p.name in cli_parameters.projects.split(",")
        }
    else:
        selected_projects = set()

    return create_run_plan(
        logger=run_plan_logger,
        revision=revision,
        all_projects=all_projects,
        all_stages=all_stages,
        selected_stage=selected_stage,
        selected_projects=selected_projects,
        changed_files_path=changed_files_path,
    )

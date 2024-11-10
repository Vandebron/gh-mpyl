"""Module to initiate run properties"""

import logging
from pathlib import Path
from typing import Optional

from ..cli import MpylCliParameters
from ..project import load_project, Stage, Project
from ..stages.discovery import create_run_plan, find_projects
from ..steps.models import RunProperties


def construct_run_properties(
    config: dict,
    properties: dict,
    cli_parameters: MpylCliParameters = MpylCliParameters(),
    root_dir: Path = Path(""),
    explain_run_plan: bool = False,
) -> RunProperties:
    all_projects = set(
        map(lambda p: load_project(project_path=p, log=True), find_projects())
    )

    stages = [Stage(stage["name"], stage["icon"]) for stage in properties["stages"]]
    run_plan_logger = logging.getLogger("mpyl")
    if explain_run_plan:
        run_plan_logger.setLevel("DEBUG")

    run_plan = _create_run_plan(
        cli_parameters=cli_parameters,
        all_projects=all_projects,
        all_stages=stages,
        explain_run_plan=explain_run_plan,
        changed_files_path=config["vcs"].get("changedFilesPath", None),
        revision=config["versioning"]["revision"],
    )

    return RunProperties.from_configuration(
        run_properties=properties,
        config=config,
        run_plan=run_plan,
        all_projects=all_projects,
        cli_tag=cli_parameters.tag or properties["build"]["versioning"].get("tag"),
        root_dir=root_dir,
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

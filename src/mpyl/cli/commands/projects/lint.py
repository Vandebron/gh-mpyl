"""Helper methods for linting projects for correctness are found here"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click
import jsonschema
from rich.console import Console

from ....project import Project, load_project, Target
from ....steps.deploy import STAGE_NAME
from ....steps.deploy.k8s import substitute_namespaces
from ....steps.deploy.k8s.chart import ChartBuilder


def __load_project(console: Console, project_path: Path) -> Optional[Project]:
    try:
        project = load_project(project_path, validate_project_yaml=True, log=False)
    except jsonschema.exceptions.ValidationError as exc:
        console.print(f"❌ {project_path}: {exc.message}")
        return None
    except Exception as exc:  # pylint: disable=broad-except
        console.print(f"❌ {project_path}: {exc}")
        return None

    console.print(f"✅ {project_path}")
    return project


def _check_and_load_projects(
    console: Console, project_paths: list[Path]
) -> list[Project]:
    projects = [__load_project(console, project_path) for project_path in project_paths]
    valid_projects = [project for project in projects if project]
    num_invalid = len(projects) - len(valid_projects)
    console.print(
        f"Validated {len(projects)} projects. {len(valid_projects)} valid, {num_invalid} invalid"
    )
    if num_invalid > 0:
        console.print(
            "Note: the validation error(s) can also come from the *-traefik.yml file(s)"
        )
        click.get_current_context().exit(1)
    return valid_projects


def _assert_unique_project_names(console: Console, all_projects: list[Project]):
    console.print("")
    console.print("Checking for duplicate project names: ")
    duplicates = [
        project.name for project in all_projects if all_projects.count(project) > 1
    ]
    return duplicates


@dataclass
class WrongLinkupPerProject:
    name: str
    wrong_substitutions: list[tuple[str, str]]


def _assert_correct_project_linkup(
    console: Console,
    target: Target,
    projects: list[Project],
    pr_identifier: Optional[int],
) -> list[WrongLinkupPerProject]:
    console.print("")
    console.print("Checking namespace substitution: ")
    wrong_substitutions = __get_wrong_substitutions_per_project(
        projects, pr_identifier, target
    )
    return wrong_substitutions


def __get_wrong_substitutions_per_project(
    projects: list[Project],
    pr_identifier: Optional[int],
    target: Target,
) -> list[WrongLinkupPerProject]:
    project_linkup: list[WrongLinkupPerProject] = []
    for project in projects:
        if project.deployments:
            for deployment in project.deployments:
                if deployment.properties:
                    env = ChartBuilder.extract_raw_env(
                        target=target, env=deployment.properties.env
                    )
                    substituted: dict[str, str] = substitute_namespaces(
                        env_vars=env,
                        all_projects=set(projects),
                        projects_to_deploy=set(projects),
                        target=target,
                        pr_identifier=pr_identifier,
                    )
                    wrong_subs = list(
                        filter(lambda x: "{namespace}" in x[1], substituted.items())
                    )
                    if len(wrong_subs) > 0:
                        project_linkup.append(
                            WrongLinkupPerProject(project.name, wrong_subs)
                        )
    return project_linkup


def __detail_wrong_substitutions(
    console: Console,
    all_projects: list[Project],
    wrong_substitutions_per_project: list[WrongLinkupPerProject],
):
    all_project_names: dict[str, str] = {
        project.name.lower(): project.name for project in all_projects
    }
    for project in wrong_substitutions_per_project:
        console.print(f"  ❌ Project {project.name} has wrong namespace substitutions:")
        for env, url in project.wrong_substitutions:
            unrecognized_project_name = url.split(".{namespace}")[0].split("/")[-1]
            suggestion = all_project_names.get(unrecognized_project_name.lower())
            console.print(
                f"  {env} references unrecognized project {unrecognized_project_name}"
                + (f" (did you mean {suggestion}?)" if suggestion else "")
            )


def _assert_no_self_dependencies(console: Console, all_projects: list[Project]):
    console.print("")
    console.print("Checking for projects depending on themselves:")

    projects_with_self_dependencies = []

    for project in all_projects:
        if project.dependencies:
            # this check is dependent on root_path always ending with a trailing slash (which is the case now).
            # it will break if that is changed in the future
            if any(
                path == project.root_path
                or path.startswith(str(project.root_path) + "/")
                for paths in project.dependencies.all().values()
                for path in paths
            ):
                projects_with_self_dependencies.append(project)

    return projects_with_self_dependencies


def _find_projects_without_deployments(console: Console, all_projects: list[Project]):
    console.print("")
    console.print("Checking for deployments:")
    projects_without_deployments = []

    for project in all_projects:
        if project.stages.for_stage(STAGE_NAME):
            if not project.deployments:
                projects_without_deployments.append(project)

    return projects_without_deployments

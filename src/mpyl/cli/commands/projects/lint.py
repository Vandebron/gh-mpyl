"""Helper methods for linting projects for correctness are found here"""

import itertools
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


def __load_project(
    console: Optional[Console],
    project_path: Path,
) -> Optional[Project]:
    try:
        project = load_project(project_path, validate_project_yaml=True, log=False)
    except jsonschema.exceptions.ValidationError as exc:
        if console:
            console.print(f"❌ {project_path}: {exc.message}")
        return None
    except Exception as exc:  # pylint: disable=broad-except
        if console:
            console.print(f"❌ {project_path}: {exc}")
        return None
    if console:
        console.print(f"✅ {project_path}")
    return project


def _check_and_load_projects(
    console: Optional[Console], project_paths: list[Path]
) -> list[Project]:
    projects = [__load_project(console, project_path) for project_path in project_paths]
    valid_projects = [project for project in projects if project]
    num_invalid = len(projects) - len(valid_projects)
    if console:
        console.print(
            f"Validated {len(projects)} projects. {len(valid_projects)} valid, {num_invalid} invalid"
        )
    if num_invalid > 0:
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


def _lint_whitelisting_rules(
    console: Console,
    projects: list[Project],
    config: dict,
    target: Target,
) -> list[tuple[Project, set[str]]]:
    console.print("")
    console.print(f"Checking whitelisting rules for target {target}: ")
    defined_whitelists: set[str] = set(
        map(lambda rule: rule["name"], config["whiteLists"]["addresses"])
    )
    wrong_whitelists: list[tuple[Project, set[str]]] = []
    for project in projects:
        if project.deployments:
            for deployment in project.deployments:
                if traefik := deployment.traefik:
                    whitelists: set[str] = set(
                        itertools.chain.from_iterable(
                            [
                                whitelist_property.get_value(target)
                                for whitelist_property in [
                                    host.whitelists
                                    for host in traefik.hosts
                                    if host.whitelists is not None
                                ]
                                if whitelist_property.get_value(target) is not None
                            ]
                        )
                    )
                    if diff := whitelists.difference(defined_whitelists):
                        wrong_whitelists.append((project, diff))

    return wrong_whitelists


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


def _find_too_long_service_names(console: Console, all_projects: list[Project]):
    console.print("")
    console.print("Checking for services with too long names:")
    too_long_names = []

    for project in all_projects:
        for deployment in project.deployments:
            name = f"{project.name}-{deployment.name}"
            if len(name) > 52:
                too_long_names.append(name)

    return too_long_names


def _find_project_names_with_underscores(console: Console, all_projects: list[Project]):
    console.print("")
    console.print("Checking for project names with underscores:")

    return [project.name for project in all_projects if "_" in project.name]

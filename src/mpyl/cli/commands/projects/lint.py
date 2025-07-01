"""Helper methods for linting projects for correctness are found here"""

from pathlib import Path
from typing import Optional

import click
import jsonschema
from rich.console import Console

from ....project import Project, load_project


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


def _find_project_names_with_underscores(console: Console, all_projects: list[Project]):
    console.print("")
    console.print("Checking for project names with underscores:")

    return [project.name for project in all_projects if "_" in project.name]

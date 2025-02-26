"""Commands related to projects and how they relate"""

import sys
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Confirm

from . import (
    CONFIG_PATH_HELP,
    create_console_logger,
)
from ..cli.commands.projects.lint import (
    _check_and_load_projects,
    _assert_unique_project_names,
    _assert_correct_project_linkup,
    __detail_wrong_substitutions,
    _assert_no_self_dependencies,
    _find_projects_without_deployments,
)
from ..cli.commands.projects.upgrade import check_upgrade
from ..constants import DEFAULT_CONFIG_FILE_NAME
from ..plan.discovery import find_projects
from ..project import load_project, Target
from ..projects.versioning import check_upgrades_needed, upgrade_file
from ..utilities.pyaml_env import parse_config


@dataclass(frozen=True)
class Context:
    config: dict
    console: Console = create_console_logger()


@click.group("projects")
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help=CONFIG_PATH_HELP,
    envvar="MPYL_CONFIG_PATH",
    default=DEFAULT_CONFIG_FILE_NAME,
)
@click.pass_context
def projects(ctx, config: Path):
    """Commands related to MPyL project configurations (project.yml)"""
    ctx.obj = Context(parse_config(config))


@projects.command(name="list", help="List found projects")
@click.pass_obj
def list_projects(ctx: Context):
    found_projects = find_projects()

    for proj in found_projects:
        project = load_project(proj, validate_project_yaml=False, log=False)
        ctx.console.print(Markdown(f"{proj} `{project.name}`"))


@projects.command(name="names", help="List found project names")
@click.pass_obj
def list_project_names(ctx: Context):
    names = sorted(
        [
            load_project(project, validate_project_yaml=False, log=False).name
            for project in (find_projects())
        ]
    )

    for name in names:
        ctx.console.print(name)


@projects.command(help="Validate the yaml of changed projects against their schema")
@click.pass_obj
# pylint: disable=too-many-branches,too-many-statements
def lint(ctx: Context):
    all_projects = _check_and_load_projects(
        console=ctx.console, project_paths=find_projects()
    )

    console = ctx.console
    failed = False

    duplicates = _assert_unique_project_names(
        console=ctx.console,
        all_projects=all_projects,
    )
    if duplicates:
        console.print(
            f"  ❌ Found {len(duplicates)} duplicate project names: {duplicates}"
        )
        failed = True
    else:
        console.print("  ✅ No duplicate project names found")

    wrong_substitutions = _assert_correct_project_linkup(
        console=console,
        target=Target.PULL_REQUEST,
        projects=all_projects,
        pr_identifier=123,
    )
    if len(wrong_substitutions) == 0:
        console.print("  ✅ No wrong namespace substitutions found")
    else:
        failed = True
        __detail_wrong_substitutions(console, all_projects, wrong_substitutions)

    projects_with_self_dependencies = _assert_no_self_dependencies(
        console, all_projects
    )
    if len(projects_with_self_dependencies) == 0:
        console.print("  ✅ No project with a dependency on itself found")
    else:
        for project in projects_with_self_dependencies:
            console.print(f"  ❌ Project {project.name} has a dependency on itself")
        failed = True

    projects_without_deployments = _find_projects_without_deployments(
        console, all_projects
    )
    if len(projects_without_deployments) == 0:
        console.print("  ✅ No project without a required deployment found")
    else:
        for project in projects_without_deployments:
            console.print(
                f"  ❌ Project {project.name} has a deploy stage defined without a deployments config"
            )
        failed = True

    if failed:
        click.get_current_context().exit(1)


@projects.command(help="Upgrade projects to conform with the latest schema")
@click.option(
    "--apply",
    "-a",
    is_flag=True,
    help="Apply upgrade operations to the project files",
)
@click.pass_obj
def upgrade(ctx: Context, apply: bool):
    paths = find_projects()
    candidates = check_upgrades_needed(paths)
    console = ctx.console
    if not apply:
        upgradable = check_upgrade(console, candidates)
        number_in_need_of_upgrade = len(upgradable)
        if number_in_need_of_upgrade > 0:
            console.print(f"{number_in_need_of_upgrade} projects need to be upgraded")
            sys.exit(1)

    with console.status("Checking for upgrades...") as status:
        materialized = list(candidates)
        need_upgrade = [path for path, diff in materialized if diff is not None]
        number_of_upgrades = len(need_upgrade)
        status.console.print(
            f"Found {len(materialized)} projects, of which {number_of_upgrades} need to be upgraded"
        )
        status.stop()
        if number_of_upgrades > 0 and Confirm.ask("Upgrade all?"):
            status.start()
            for path in need_upgrade:
                status.update(f"Upgrading {path}")
                upgraded = upgrade_file(path)
                if upgraded:
                    path.write_text(upgraded)
            status.stop()
            status.console.print(
                Markdown(
                    f"Upgraded {number_of_upgrades} projects. Validate with `mpyl projects lint`"
                )
            )

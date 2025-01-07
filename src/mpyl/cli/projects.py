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
    _lint_whitelisting_rules,
    __detail_wrong_substitutions,
    _assert_missing_project_ids,
    _assert_no_self_dependencies,
    _assert_namespaces,
    _assert_dagster_configs,
    _assert_different_project_ids,
)
from ..cli.commands.projects.upgrade import check_upgrade
from ..constants import DEFAULT_CONFIG_FILE_NAME
from ..plan.discovery import find_projects
from ..project import load_project, Target
from ..projects.versioning import (
    check_upgrades_needed,
    upgrade_file,
    PROJECT_UPGRADERS,
)
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

    namespaces = _assert_namespaces(console=console, all_projects=all_projects)
    if len(namespaces) > 0:
        console.print(
            f"  ❌ Found {len(namespaces)} project with different namespaces in its deployments: {namespaces}"
        )
        failed = True
    else:
        console.print("  ✅ All deployments have the same namespace")

    dagster_configs = _assert_dagster_configs(
        console=console, all_projects=all_projects
    )
    if len(dagster_configs) > 0:
        console.print(
            f"  ❌ Found {len(dagster_configs)} project(s) with multiple dagster configs: {dagster_configs}"
        )
        failed = True
    else:
        console.print("  ✅ Only one dagster config found in deployments")

    missing_project_ids = _assert_missing_project_ids(
        console=console, all_projects=all_projects
    )
    if missing_project_ids:
        console.print(
            f"  ❌ Found {len(missing_project_ids)} projects without a project id: {missing_project_ids}"
        )
        failed = True
    else:
        console.print("  ✅ All kubernetes projects have a project id")

    different_project_ids = _assert_different_project_ids(
        console=console, all_projects=all_projects
    )
    if different_project_ids:
        console.print(
            f"  ❌ Found {len(different_project_ids)} projects with different project ids: {different_project_ids}"
        )
        failed = True
    else:
        console.print("  ✅ All project id's are equal")

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

    for target in Target:
        wrong_whitelists = _lint_whitelisting_rules(
            console=console,
            projects=all_projects,
            config=ctx.config,
            target=target,
        )
        if len(wrong_whitelists) == 0:
            console.print("  ✅ No undefined whitelists found")
        else:
            for project, diff in wrong_whitelists:
                console.log(
                    f"  ❌ Project {project.name} has undefined whitelists: {diff}"
                )
                failed = True

    projects_with_self_dependencies = _assert_no_self_dependencies(
        console, all_projects
    )
    if len(projects_with_self_dependencies) == 0:
        console.print("  ✅ No project with a dependency on itself found")
    else:
        for project in projects_with_self_dependencies:
            console.print(f"  ❌ Project {project.name} has a dependency on itself")
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
    candidates = check_upgrades_needed(paths, PROJECT_UPGRADERS)
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
                upgraded = upgrade_file(path, PROJECT_UPGRADERS)
                if upgraded:
                    path.write_text(upgraded)
            status.stop()
            status.console.print(
                Markdown(
                    f"Upgraded {number_of_upgrades} projects. Validate with `mpyl projects lint`"
                )
            )

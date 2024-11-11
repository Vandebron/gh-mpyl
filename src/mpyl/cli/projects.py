"""Commands related to projects and how they relate"""

import sys
from dataclasses import dataclass

import click
from rich.markdown import Markdown
from rich.prompt import Confirm

from . import (
    CliContext,
    CONFIG_PATH_HELP,
    create_console_logger,
)
from ..cli.commands.projects.lint import (
    _check_and_load_projects,
    _assert_unique_project_names,
    _assert_correct_project_linkup,
    _lint_whitelisting_rules,
    __detail_wrong_substitutions,
    _assert_project_ids,
    _assert_no_self_dependencies,
)
from ..cli.commands.projects.upgrade import check_upgrade
from ..constants import DEFAULT_CONFIG_FILE_NAME
from ..project import load_project, Target
from ..projects.versioning import (
    check_upgrades_needed,
    upgrade_file,
    PROJECT_UPGRADERS,
)
from ..stages.discovery import find_projects
from ..utilities.pyaml_env import parse_config


@dataclass
class ProjectsContext:
    cli: CliContext


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
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.pass_context
def projects(ctx, config, verbose):
    """Commands related to MPyL project configurations (project.yml)"""
    ctx.obj = ProjectsContext(
        cli=CliContext(
            config=parse_config(config),
            console=create_console_logger(
                show_path=False, verbose=verbose, max_width=0
            ),
            verbose=verbose,
            run_properties={},
        ),
    )


OVERRIDE_PATTERN = "project-override"


@projects.command(name="list", help="List found projects")
@click.pass_obj
def list_projects(obj: ProjectsContext):
    found_projects = find_projects()

    for proj in found_projects:
        project = load_project(proj, log=False)
        obj.cli.console.print(Markdown(f"{proj} `{project.name}`"))


@projects.command(name="names", help="List found project names")
@click.pass_obj
def list_project_names(obj: ProjectsContext):
    found_projects = find_projects()

    names = sorted([load_project(project, log=False).name for project in found_projects])

    for name in names:
        obj.cli.console.print(name)


@projects.command(help="Validate the yaml of changed projects against their schema")
@click.pass_obj
# pylint: disable=too-many-branches
def lint(obj: ProjectsContext):
    all_projects = _check_and_load_projects(
        console=obj.cli.console, project_paths=find_projects()
    )

    console = obj.cli.console
    failed = False

    duplicates = _assert_unique_project_names(
        console=console,
        all_projects=all_projects,
    )
    if duplicates:
        console.print(
            f"  ❌ Found {len(duplicates)} duplicate project names: {duplicates}"
        )
        failed = True
    else:
        console.print("  ✅ No duplicate project names found")

    missing_project_ids = _assert_project_ids(
        console=console, all_projects=all_projects
    )
    if missing_project_ids:
        console.print(
            f"  ❌ Found {len(missing_project_ids)} projects without a project id: {missing_project_ids}"
        )
        failed = True
    else:
        console.print("  ✅ All kubernetes projects have a project id")

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
            config=obj.cli.config,
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
def upgrade(obj: ProjectsContext, apply: bool):
    paths = find_projects()
    candidates = check_upgrades_needed(paths, PROJECT_UPGRADERS)
    console = obj.cli.console
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


if __name__ == "__main__":
    projects()  # pylint: disable=no-value-for-parameter

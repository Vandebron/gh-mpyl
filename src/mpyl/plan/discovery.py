""" Discovery of projects that are relevant to a specific `mpyl.stage.Stage` . Determine which of the
discovered projects have to be run due to changes in the source code since the last build of the project's
output."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from ..project import Project
from ..utilities.repo import Changeset


def find_projects() -> list[Path]:
    # Ideally we'd use globbing here, as it's super easy to read:
    #   projects = root.rglob(f"deployment/project.yml")
    #
    # However, because monorepo, this takes literally minutes to scan the entire repository, which we can't afford to
    # do every time we run a command on mpyl. For this reason, I decided to go with an optimized find command, which
    # is a bit harder to read but completes in a couple of seconds.
    # If you find a faster way to list all files, please raise a PR.

    command = (
        f"find {Path('.')}"
        " -type d ( -name target -o -name .git ) -prune"
        " -o ("
        f" -path **/deployment/{Project.project_yaml_file_name()}"
        f" -o -path **/deployment/{Project.project_overrides_yaml_file_pattern()}"
        " )"
        " -print"
    )
    files = subprocess.run(
        command.split(" "), capture_output=True, text=True, check=True, shell=False
    ).stdout.splitlines()
    return list(map(Path, sorted(files)))


def is_file_in_project(logger: logging.Logger, project: Project, path: str) -> bool:
    if path.startswith(str(project.root_path) + "/"):
        logger.debug(
            f"Project {project.name} added to the run plan because project file was modified: {path}"
        )
        return True
    return False


def is_file_a_dependency(
    logger: logging.Logger,
    project: Project,
    path: str,
) -> bool:
    if any(path.startswith(d) for d in project.dependencies):
        logger.debug(
            f"Project {project.name} added to the run plan because a dependency was modified: {path}"
        )
        return True

    return False


def find_projects_to_execute(
    logger: logging.Logger,
    all_projects: set[Project],
    changeset: Changeset,
) -> set[Project]:
    def find_projects_that_should_execute(project: Project) -> Optional[Project]:
        if any(
            is_file_in_project(logger, project, changed_file)
            for changed_file in changeset.files_touched()
        ):
            logger.debug(
                f"Project {project.name} will run because its content changed since the previous run"
            )
            return project

        if any(
            is_file_a_dependency(logger, project, changed_file)
            for changed_file in changeset.files_touched()
        ):
            logger.debug(
                f"Project {project.name} will run because one or more of its dependencies was modified"
            )
            return project

        return None

    return {
        project
        for project in map(find_projects_that_should_execute, all_projects)
        if project is not None
    }

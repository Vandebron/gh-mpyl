""" Discovery of projects that are relevant to a specific `mpyl.stage.Stage` . Determine which of the
discovered projects have to be run due to changes in the source code since the last build of the project's
output."""

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional

from ..project import Project
from ..project_execution import ProjectExecution
from ..steps import deploy
from ..steps.output import Output
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


def file_belongs_to_project(project: Project, path: str) -> bool:
    return path.startswith(str(project.root_path) + "/")


def is_file_in_project(logger: logging.Logger, project: Project, path: str) -> bool:
    if file_belongs_to_project(project, path):
        logger.debug(
            f"Project {project.name} added to the run plan because project file was modified: {path}"
        )
        return True
    return False


def is_file_a_dependency(
    logger: logging.Logger,
    project: Project,
    stage: str,
    path: str,
) -> bool:
    deps = project.dependencies
    if not deps:
        return False

    touched_stages: set[str] = {
        dep_stage
        for dep_stage, dependencies in deps.all().items()
        if len([d for d in dependencies if path.startswith(d)]) > 0
    }

    if stage in touched_stages:
        logger.debug(
            f"Project {project.name} added to the run plan because a {stage} dependency was modified: {path}"
        )
        return True

    return False


def is_project_cached_for_stage(
    logger: logging.Logger,
    project: str,
    stage: str,
    output: Optional[Output],
    hashed_changes: Optional[str],
) -> bool:
    cached = False

    if stage == deploy.STAGE_NAME:
        logger.debug(
            f"Project {project} will execute stage {stage} because this stage is never cached"
        )
    elif output is None:
        logger.debug(
            f"Project {project} will execute stage {stage} because there is no previous run"
        )
    elif not output.success:
        logger.debug(
            f"Project {project} will execute stage {stage} because the previous run was not successful"
        )
    elif not output.hash:
        logger.debug(
            f"Project {project} will execute stage {stage} because there are no hashed changes for the previous run"
        )
    elif not hashed_changes:
        logger.debug(
            f"Project {project} will execute stage {stage} because there are no hashed changes for the current run"
        )
    elif output.hash != hashed_changes:
        logger.debug(
            f"Project {project} will execute stage {stage} because its content changed since the previous run"
        )
        logger.debug(f"Hashed changes for the previous run: {output.hash}")
        logger.debug(f"Hashed changes for the current run:  {hashed_changes}")
    else:
        logger.debug(
            f"Project {project} will skip stage {stage} because its content did not change since the previous run"
        )
        logger.debug(f"Hashed changes for the current run: {hashed_changes}")
        cached = True

    return cached


def _hash_changes_in_project(
    project: Project,
    changeset: Changeset,
) -> Optional[str]:
    files_to_hash = set(
        filter(
            lambda changed_file: file_belongs_to_project(project, changed_file),
            changeset.files_touched(status={"A", "M", "R", "C"}),
        )
    )

    if len(files_to_hash) == 0:
        return None

    sha256 = hashlib.sha256()

    for changed_file in sorted(files_to_hash):
        with open(changed_file, "rb") as file:
            while True:
                data = file.read(65536)
                if not data:
                    break
                sha256.update(data)

    return sha256.hexdigest()


def find_projects_to_execute(
    logger: logging.Logger,
    all_projects: set[Project],
    stage: str,
    changeset: Changeset,
) -> set[ProjectExecution]:
    def build_project_execution(
        project: Project,
    ) -> Optional[ProjectExecution]:
        if project.stages.for_stage(stage) is None:
            return None

        is_any_dependency_modified = any(
            is_file_a_dependency(logger, project, stage, changed_file)
            for changed_file in changeset.files_touched()
        )
        is_project_modified = any(
            is_file_in_project(logger, project, changed_file)
            for changed_file in changeset.files_touched()
        )

        if is_any_dependency_modified:
            logger.debug(
                f"Project {project.name} will execute stage {stage} because (at least) one of its dependencies was "
                f"modified"
            )

            if is_project_modified:
                hashed_changes = _hash_changes_in_project(
                    project=project, changeset=changeset
                )
            else:
                hashed_changes = None

            return ProjectExecution.run(project, hashed_changes)

        if is_project_modified:
            hashed_changes = _hash_changes_in_project(
                project=project, changeset=changeset
            )

            return ProjectExecution.create(
                project=project,
                cached=is_project_cached_for_stage(
                    logger=logger,
                    project=project.name,
                    stage=stage,
                    output=Output.try_read(project.target_path, stage),
                    hashed_changes=hashed_changes,
                ),
                hashed_changes=hashed_changes,
            )

        return None

    return {
        project_execution
        for project_execution in map(build_project_execution, all_projects)
        if project_execution is not None
    }

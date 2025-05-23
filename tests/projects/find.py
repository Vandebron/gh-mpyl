""" Loads all projects inside a repository. """

from pathlib import Path
from typing import Optional

from src.mpyl.plan.discovery import find_projects
from src.mpyl.project import Project, load_project
from src.mpyl.projects import ProjectWithDependents, Protocol, Contract, Dependency
from tests.test_resources.test_data import TestStage


def load_projects(paths: Optional[list[Path]] = None) -> set[Project]:
    if not paths:
        paths = find_projects()
    return set(map(lambda p: load_project(p, validate_project_yaml=False), paths))


def find_by_contract_dep(
    dep: str, projects: list[ProjectWithDependents]
) -> Optional[ProjectWithDependents]:
    for project in projects:
        if str(project.project.root_path) in dep:
            return project
    return None


def find_dependencies(
    project: Project, other_projects: set[Project]
) -> ProjectWithDependents:
    mapped = list(map(lambda p: ProjectWithDependents(p, {}), other_projects))

    def recursively_find(
        proj: ProjectWithDependents,
        other: list[ProjectWithDependents],
        discovery_stack: list[str],
    ):
        dependent_projects = {}
        for dep in (
            proj.project.dependencies.set_for_stage(TestStage.test().name)
            if proj.project.dependencies
            else set()
        ):
            found = find_by_contract_dep(dep, other)
            if found:
                if found.name not in discovery_stack:
                    discovery_stack.append(found.name)
                    recursively_find(found, other, discovery_stack[:])
                    dependent_projects[found.name] = Dependency(
                        found.project, {Contract(Protocol.UNKNOWN, dep)}
                    )
                elif found.name in dependent_projects:
                    dependent_projects[found.name].contracts.add(
                        Contract(Protocol.UNKNOWN, dep)
                    )

        proj.dependent_projects = dependent_projects
        return proj

    return recursively_find(
        ProjectWithDependents(project=project, dependent_projects={}), mapped, []
    )

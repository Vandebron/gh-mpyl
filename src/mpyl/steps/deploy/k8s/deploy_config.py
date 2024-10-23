"""Configuration dataclasses for the deploy step."""

from typing import Optional

from ...models import RunProperties
from ....project import Project, Target


def get_namespace(run_properties: RunProperties, project: Project) -> str:
    if run_properties.target == Target.PULL_REQUEST:
        return run_properties.versioning.identifier

    return __get_namespace_from_project(project) or project.name


def __get_namespace_from_project(project: Project) -> Optional[str]:
    if project.deployment and project.deployment.namespace:
        return project.deployment.namespace

    return None

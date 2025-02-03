"""Kubernetes deployment related helper methods"""

from logging import Logger
from pathlib import Path
from typing import Optional

from .helm import write_helm_chart
from ...deploy.k8s.resources import CustomResourceDefinition
from ...input import Input
from ...models import RunProperties
from ...output import Output
from ....project import ProjectName, Project, Target
from ....utilities import replace_pr_number


def generate_helm_charts(
    logger: Logger, chart: dict[str, CustomResourceDefinition], step_input: Input
) -> Output:
    chart_path = write_helm_chart(
        logger, chart, Path(step_input.project_execution.project.target_path)
    )

    return Output(
        success=True,
        message=f"Helm charts written to {chart_path}",
    )


def get_namespace(run_properties: RunProperties, project: Project) -> str:
    if run_properties.target == Target.PULL_REQUEST:
        return run_properties.versioning.identifier

    return __get_namespace_from_project(project) or project.name


def __get_namespace_from_project(project: Project) -> Optional[str]:
    if project.deployment and project.deployment.namespace:
        return project.deployment.namespace

    return None


def substitute_namespaces(
    env_vars: dict[str, str],
    all_projects: set[ProjectName],
    projects_to_deploy: set[ProjectName],
    pr_identifier: Optional[int],
) -> dict[str, str]:
    """
    Substitute namespaces in environment variables.

    In the project yamls we define references to other projects with e.g.:

    ```yaml
    - key: SOME_SERVICE_URL:
      all: http://serviceName.{namespace}.svc.cluster.local
    ```

    When the env var is substituted, first the referenced service (serviceName) is looked up in the list of projects.
    If it is part of the run plan, and we're in deploying to target PullRequest,
    the namespace is substituted with the PR namespace (pr-XXXX).
    Else is substituted with the namespace of the referenced project.

    Note that the name of the service in the env var is case-sensitive!

    :param env_vars: environment variables to substitute
    :param all_projects: all projects in repo
    :param projects_to_deploy: projects in run plan
    :param pr_identifier: PR number if applicable
    :return: dictionary of substituted env vars
    """
    env = env_vars.copy()

    def get_namespace_for_linked_project(project_name: ProjectName) -> str:
        is_part_of_same_deploy_set = project_name in projects_to_deploy
        if is_part_of_same_deploy_set and pr_identifier:
            return f"pr-{pr_identifier}"
        return project_name.namespace or project.name

    def replace_namespace(env_value: str, project_name: str, namespace: str) -> str:
        search_value = project_name + ".{namespace}"
        replace_value = project_name + "." + namespace
        return env_value.replace(search_value, replace_value)

    for project in all_projects:
        if project.namespace:
            linked_project_namespace = get_namespace_for_linked_project(project)
            for key, value in env.items():
                replaced_namespace = replace_namespace(
                    value, project.name, linked_project_namespace
                )
                updated_pr = replace_pr_number(replaced_namespace, pr_identifier)
                env[key] = updated_pr
    return env

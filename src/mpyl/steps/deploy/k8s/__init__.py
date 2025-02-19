"""Kubernetes deployment related helper methods"""

from logging import Logger
from pathlib import Path
from typing import Optional

from .helm import write_helm_chart
from ...deploy.k8s.resources import CustomResourceDefinition
from ...input import Input
from ...output import Output
from ....project import Project, Target
from ....utilities import replace_pr_number


def generate_helm_charts(
    logger: Logger, chart: dict[str, CustomResourceDefinition], step_input: Input
) -> Output:
    chart_path = write_helm_chart(logger, chart, Path(step_input.project.target_path))

    return Output(
        success=True,
        message=f"Helm charts written to {chart_path}",
    )


def substitute_namespaces(
    env_vars: dict[str, str],
    all_projects: set[Project],
    projects_to_deploy: set[Project],
    target: Target,
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
    :param target: the deploy target to resolve the namespace
    :param pr_identifier: PR number if applicable
    :return: dictionary of substituted env vars
    """
    env = env_vars.copy()

    def get_namespace_for_linked_project(project: Project) -> str:
        is_part_of_same_deploy_set = project in projects_to_deploy
        if is_part_of_same_deploy_set and pr_identifier:
            return f"pr-{pr_identifier}"
        return project.namespace(target)

    def replace_namespace(
        original_value: str,
        service_name: str,
        namespace: str,
    ):
        search_value = service_name + ".{namespace}"
        replace_value = service_name + "." + namespace
        replaced_namespace = original_value.replace(search_value, replace_value)
        updated_pr = replace_pr_number(replaced_namespace, pr_identifier)
        if updated_pr != original_value:
            env[key] = updated_pr

    for project in all_projects:
        linked_project_namespace = get_namespace_for_linked_project(project)
        for key, value in env.items():
            replace_namespace(
                original_value=value,
                service_name=project.name,
                namespace=linked_project_namespace,
            )

            for deployment in project.deployments:
                replace_namespace(
                    original_value=value,
                    service_name=deployment.name,
                    namespace=linked_project_namespace,
                )

    return env

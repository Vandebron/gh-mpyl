"""Kubernetes deployment related helper methods"""

import datetime
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Optional

import yaml as dict_to_yaml_str
from kubernetes import config, client
from kubernetes.client import V1ConfigMap, ApiException, V1Deployment
from ruamel.yaml import yaml_object, YAML

from .deploy_config import DeployConfig, DeployAction, get_namespace
from .helm import write_helm_chart, GENERATED_WARNING
from ...deploy.k8s.resources import CustomResourceDefinition
from ...models import RunProperties, ArtifactSpec
from ....project import ProjectName
from ....steps import Input, Output
from ....steps.deploy.k8s import helm
from ....steps.deploy.k8s.cluster import (
    get_namespace_metadata,
    ClusterConfig,
    get_cluster_config_for_project,
)
from ....steps.deploy.k8s.resources import to_yaml
from ....utilities import replace_pr_number

yaml = YAML()


@yaml_object(yaml)
@dataclass
class DeployedHelmAppSpec(ArtifactSpec):
    yaml_tag = "!DeployedHelmAppSpec"
    url: Optional[str]


@yaml_object(yaml)
@dataclass
class RenderedHelmChartSpec(ArtifactSpec):
    yaml_tag = "!RenderedHelmChartSpec"
    chart_path: str


def rollout_restart_deployment(
    logger: Logger, apps_api: client.AppsV1Api, namespace: str, deployment: str
) -> Output:
    # from https://stackoverflow.com/a/67491253
    now = datetime.datetime.utcnow()
    now_str = now.isoformat("T") + "Z"
    body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {"kubectl.kubernetes.io/restartedAt": now_str}
                }
            }
        }
    }
    try:
        logger.info(f"Starting rollout restart of {deployment}...")
        _, status_code, _ = apps_api.patch_namespaced_deployment_with_http_info(
            deployment, namespace, body, pretty="true"
        )
        return Output(
            success=True,
            message=f"Rollout restart of {deployment} finished with statuscode {status_code}",
        )
    except ApiException as api_exception:
        return Output(
            success=False,
            message=f"Exception when calling AppsV1Api -> patch_namespaced_deployment: {api_exception}\n"
            f"{deployment} was NOT restarted",
        )


def upsert_namespace(
    logger: Logger,
    namespace: str,
    project_id: str,
    run_properties: RunProperties,
    cluster_config: ClusterConfig,
) -> None:
    config.load_kube_config(context=cluster_config.context)
    logger.info(
        f"Deploying target {run_properties.target} and k8s context {cluster_config.context}"
    )
    api = client.CoreV1Api()

    meta_data = get_namespace_metadata(
        namespace=namespace, cluster_config=cluster_config, project_id=project_id
    )
    namespaces = api.list_namespace(field_selector=f"metadata.name={namespace}")

    if len(namespaces.items) == 0:
        try:
            api.create_namespace(
                client.V1Namespace(
                    api_version="v1", kind="Namespace", metadata=meta_data
                )
            )
        except ApiException as error:
            # when concurrently deploying multiple services of the same PR, we can sometimes still try to create a
            # namespace that already exists. if that happens, ignore the error
            if error.status == 409:
                logger.info(f"Found namespace {namespace}")
            else:
                raise error
    else:
        logger.info(f"Found namespace {namespace}")


def render_crd(name: str, crd: CustomResourceDefinition):
    return f"---\n# {name}\n{to_yaml(crd)}"


def get_config_map(
    core_api: client.CoreV1Api, namespace: str, config_map_name: str
) -> V1ConfigMap:
    user_code_config_map: V1ConfigMap = core_api.read_namespaced_config_map(
        config_map_name, namespace
    )
    return user_code_config_map


def get_version_of_deployment(
    apps_api: client.AppsV1Api, namespace: str, deployment: str, version_label: str
) -> str:
    v1deployment: V1Deployment = apps_api.read_namespaced_deployment(
        deployment, namespace
    )
    return v1deployment.metadata.labels[version_label]


def update_config_map_field(
    config_map: V1ConfigMap, field: str, data: dict
) -> V1ConfigMap:
    config_map.data[field] = dict_to_yaml_str.dump(data)
    return config_map


def replace_config_map(
    core_api: client.CoreV1Api,
    namespace: str,
    config_map_name: str,
    config_map: V1ConfigMap,
) -> Output:
    try:
        _, status_code, _ = core_api.replace_namespaced_config_map_with_http_info(
            config_map_name, namespace, config_map
        )
        return Output(
            success=True,
            message=f"ConfigMap Update of {config_map_name} finished with statuscode {status_code}",
        )
    except ApiException as api_exception:
        return Output(
            success=False,
            message=f"Exception when calling CoreV1Api -> replace_namespaced_config_map: {api_exception}\n",
        )


def deploy_helm_chart(
    logger: Logger,
    chart_path: Path,
    step_input: Input,
    release_name: str,
    delete_existing: bool = False,
) -> Output:
    run_properties = step_input.run_properties
    project = step_input.project_execution.project
    namespace = get_namespace(run_properties, project)
    project_id: str = (
        project.deployment.kubernetes.rancher.project_id.get_value(
            target=run_properties.target
        )
        if project.deployment
        and project.deployment.kubernetes
        and project.deployment.kubernetes.rancher
        and project.deployment.kubernetes.rancher.project_id
        else ""
    )

    cluster_config: ClusterConfig = get_cluster_config_for_project(
        run_properties, project
    )

    upsert_namespace(
        logger=logger,
        namespace=namespace,
        project_id=project_id,
        run_properties=run_properties,
        cluster_config=cluster_config,
    )

    return helm.install(
        logger,
        chart_path,
        release_name,
        namespace,
        cluster_config.context,
        delete_existing,
    )


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
    If it is part of the deploy set, and we're in deploying to target PullRequest,
    the namespace is substituted with the PR namespace (pr-XXXX).
    Else is substituted with the namespace of the referenced project.

    Note that the name of the service in the env var is case-sensitive!

    :param env_vars: environment variables to substitute
    :param all_projects: all project in repo
    :param projects_to_deploy: projects in deploy set
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

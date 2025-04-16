"""Functions to generate backstage components"""

import os

import yaml

from ..plan.discovery import find_projects
from ..project import load_project, Project, Target, KeyValueProperty
from ..steps import deploy
from ..steps.deploy.k8s.chart import ChartBuilder


def generate_components(directory: str, repository_url: str) -> None:
    projects: list[Project] = []
    for project_yaml_file in find_projects():
        projects.append(load_project(project_yaml_file, validate_project_yaml=True))

    service_components: list[dict] = []
    maintainers: list[str] = []
    project_names = __get_project_names(projects)
    for project in projects:
        maintainer = ",".join(
            project.maintainer if len(project.maintainer) else ["unknown"]
        )
        service_components.append(
            __generate_component(project, project_names, maintainer, repository_url)
        )
        maintainers.append(maintainer)

    group_components: list[dict] = []
    for maintainer in set(maintainers):
        group_components.append(__generate_group(maintainer))

    component_collections: list[dict[str, list[dict]]] = [
        {f"{directory}/services.yaml": service_components},
        {f"{directory}/groups.yaml": group_components},
    ]
    for component_collection in component_collections:
        for file_location, components in component_collection.items():
            os.makedirs(os.path.dirname(file_location), exist_ok=True)
            with open(file_location, "w+", encoding="utf-8") as components_yaml_file:
                components_yaml_file.write(
                    yaml.dump_all(components, default_flow_style=False, sort_keys=False)
                )


def __get_project_type(project: Project) -> str:
    # This check can be removed after all project overrides are replaced
    if len(list(project.deployment_path.glob("*-override-*"))) > 0:
        return "project override"

    deploy_step = project.stages.for_stage(deploy.STAGE_NAME)
    if not deploy_step:
        return "library"

    if "BPM" in deploy_step:
        return "bpm diagram"

    job_config = project.deployments[0].kubernetes.job
    if job_config:
        if job_config.cron:
            return "cronjob"
        return "job"

    return "service"


def __get_project_names(projects: list[Project]) -> list[str]:
    return [project.name for project in projects]


def __get_dependencies_for_project(
    project: Project, project_names: list[str]
) -> list[str]:
    env_vars: list[KeyValueProperty] = []
    for deployment in project.deployments:
        if deployment.properties:
            env_vars = env_vars + deployment.properties.env

    dependencies: list[str] = []

    for project_name in project_names:
        raw_env_vars = ChartBuilder.extract_raw_env(Target.PRODUCTION, env_vars)
        for value in raw_env_vars.values():
            if "svc.cluster.local" in value and project_name in value:
                dependencies.append(
                    project_name
                )  # add check for keycloak and other tools (browserless, etc)
    return list(set(dependencies))


def __generate_component(
    project: Project, project_names: list[str], maintainer: str, repository_url: str
) -> dict:
    return {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "metadata": {
            "name": project.name,
            "description": project.description,
            "links": [
                {
                    "url": f"{repository_url}/{project.path}",
                    "type": "repository",
                    "title": "Github",
                }
            ],
        },
        "spec": {
            "type": __get_project_type(project),
            "lifecycle": "production",
            "owner": maintainer,
            "dependsOn": [
                f"component:default/{name}"
                for name in __get_dependencies_for_project(project, project_names)
            ],
        },
    }


def __generate_group(maintainer: str) -> dict:
    return {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Group",
        "metadata": {
            "name": maintainer,
        },
        "spec": {
            "type": "team",
            "children": [],
        },
    }

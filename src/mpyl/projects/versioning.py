"""Versioning and upgrade utilities for mpyl projects.
### Writing an upgrade script

To write an upgrade script, create a new class that inherits from `Upgrader` and
implements the `upgrade` method. This class should then be added to the `UPGRADERS`
list in this module.

"""

import copy
import re
from abc import ABC
from pathlib import Path
from typing import Generator
from typing import Optional

from deepdiff import DeepDiff
from ruamel.yaml.compat import ordereddict

from ..constants import NAMESPACE_PLACEHOLDER
from ..project import Project
from ..utilities.yaml import yaml_to_string, load_for_roundtrip, yaml_for_roundtrip

VERSION_FIELD = "projectYmlVersion"
BASE_RELEASE = 1


class Upgrader(ABC):
    """Base class for upgrade scripts"""

    target_version: int

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        return previous_dict


class ProjectUpgraderOne(Upgrader):
    target_version = 1

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        if "mpylVersion" in previous_dict:
            del previous_dict["mpylVersion"]

        return previous_dict


class ProjectUpgraderTwo(Upgrader):
    project_yml_path: Path

    def __init__(self, project_yml_path: Path):
        self.project_yml_path = project_yml_path

    target_version = 2

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        traefik = previous_dict.get("deployment", {}).get("traefik", {})

        if traefik:
            service_name = previous_dict["name"]
            traefik_yml_path = (
                self.project_yml_path.parent
                / Project.traefik_yaml_file_name(service_name)
            )
            traefik_config = {
                "traefik": traefik,
            }
            traefik_yml_path.write_text(
                yaml_to_string(traefik_config, yaml_for_roundtrip())
            )

            del previous_dict["deployment"]["traefik"]

        return previous_dict


class ProjectUpgraderThree(Upgrader):
    target_version = 3

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        deployment = previous_dict.get("deployment")

        # only upgrades for projects with deployment config
        if not deployment:
            return previous_dict

        namespace = deployment.get("namespace")
        project_id = (
            deployment.get("kubernetes", {}).get("rancher", {}).get("projectId")
        )
        new_kubernetes_config = previous_dict.get("kubernetes")

        # create new dict entry if needed
        if (namespace or project_id) and not new_kubernetes_config:
            previous_dict["kubernetes"] = {}

        # move namespace from deployment to common kubernetes config since it's shared between deployments
        if namespace:
            del deployment["namespace"]
            previous_dict["kubernetes"]["namespace"] = {}
            previous_dict["kubernetes"]["namespace"]["all"] = namespace

        # same as namespace above
        if project_id:
            del deployment["kubernetes"]["rancher"]
            previous_dict["kubernetes"]["projectId"] = project_id

        # move dagster config out of deployment since it's not related
        dagster_config = deployment.get("dagster")
        if dagster_config:
            del deployment["dagster"]
            previous_dict["dagster"] = dagster_config

        # copy project name to deployment name (just for the migration, they don't need to match later)
        deployment.insert(0, "name", previous_dict["name"])

        # move deployment to deployments
        del previous_dict["deployment"]
        previous_dict["deployments"] = [deployment]

        # combine kubernetes deploy steps
        if previous_dict["stages"].get("deploy", "") == "Kubernetes Job Deploy":
            previous_dict["stages"]["deploy"] = "Kubernetes Deploy"

        return previous_dict


class ProjectUpgraderFour(Upgrader):
    project_yml_path: Path

    def __init__(self, project_yml_path: Path):
        self.project_yml_path = project_yml_path

    target_version = 4

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        service_name = previous_dict["name"]

        # change the default deployment name
        deployments = previous_dict.get("deployments", [])
        if len(deployments) == 1:
            deployment = deployments[0]

            if deployment["name"] == service_name:
                is_job = deployment.get("kubernetes", {}).get("job", {})
                is_cron_job = is_job.get("cron")

                if is_cron_job:
                    deployment["name"] = "cronjob"
                elif is_job:
                    deployment["name"] = "job"
                else:
                    deployment["name"] = "http"

        # update traefik config file name
        traefik_yml_path = (
            self.project_yml_path.parent / Project.traefik_yaml_file_name(service_name)
        )
        if traefik_yml_path.exists():
            traefik_yml_path.rename(
                self.project_yml_path.parent / Project.traefik_yaml_file_name("http")
            )

        return previous_dict


class ProjectUpgraderFive(Upgrader):
    target_version = 5

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        # update the env var url's
        deployments = previous_dict.get("deployments", [])
        for deployment in deployments:
            properties = deployment.get("properties")

            if properties:
                for env_var in properties.get("env", []):
                    for key, value in env_var.items():
                        if "keycloak" in value:
                            continue
                        regex = (
                            r"http://([a-zA-Z0-9\-]+)\.("
                            + f"{NAMESPACE_PLACEHOLDER}"
                            + r"|[a-z\-]+)\.svc"
                        )
                        match = re.search(regex, value)
                        if match:
                            service_name = match.groups()[0]
                            namespace = match.groups()[1]
                            env_var[key] = re.sub(
                                regex,
                                f"http://{service_name}-http.{namespace}.svc",
                                value,
                            )

        return previous_dict


def get_entry_upgrader_index(
    current_version: int, upgraders: list[Upgrader]
) -> Optional[int]:
    next_index = next(
        (i for i, v in enumerate(upgraders) if v.target_version == current_version),
        None,
    )
    return next_index


def __get_version(project: dict) -> int:
    return project.get(VERSION_FIELD, BASE_RELEASE)


def upgrade_to_latest(project_file: Path) -> ordereddict:
    loaded, _ = load_for_roundtrip(project_file)
    to_upgrade = copy.deepcopy(loaded)
    upgraders = [
        ProjectUpgraderOne(),
        ProjectUpgraderTwo(project_file),
        ProjectUpgraderThree(),
        ProjectUpgraderFour(project_file),
        ProjectUpgraderFive(),
    ]

    upgrade_index = get_entry_upgrader_index(__get_version(to_upgrade), upgraders)
    if upgrade_index is None:
        return to_upgrade

    upgraded = to_upgrade
    for i in range(upgrade_index, len(upgraders)):
        upgrader = upgraders[i]
        before_upgrade = copy.deepcopy(upgraded)
        upgraded = upgrader.upgrade(copy.deepcopy(before_upgrade))
        diff = DeepDiff(before_upgrade, upgraded, ignore_order=True, view="tree")
        if diff:
            upgraded.insert(2, VERSION_FIELD, upgrader.target_version)
    return upgraded


def pretty_print_value(value) -> str:
    print_yaml = yaml_for_roundtrip()
    if isinstance(value, (dict, list, set)):
        return f"\n```\n{yaml_to_string(value, print_yaml)}```"
    return f"`{value}`\n"


def pretty_print(diff: DeepDiff) -> str:
    result = []
    if "dictionary_item_added" in diff:
        for key, value in diff["dictionary_item_added"].items():
            result.append(f"➕ {key} -> {pretty_print_value(value)}")
    if "dictionary_item_removed" in diff:
        for key, value in diff["dictionary_item_removed"].items():
            result.append(f"➖ {key} -> {pretty_print_value(value)}")
    if "values_changed" in diff:
        for key, values in diff["values_changed"].items():
            new = values.get("new_value", None)
            old = values.get("old_value", None)
            result.append(f"  {key}: {f'{old} ->' if old else ''}{new if new else ''}")
    return "\n".join(result)


def check_upgrades_needed(
    file_path: list[Path],
) -> Generator[tuple[Path, DeepDiff | None], None, None]:
    for path in file_path:
        yield check_upgrade_needed(path)


def check_upgrade_needed(file_path: Path) -> tuple[Path, Optional[DeepDiff]]:
    loaded, _ = load_for_roundtrip(file_path)
    upgraded = upgrade_to_latest(file_path)
    diff = DeepDiff(loaded, upgraded, ignore_order=True, view="_delta")
    if diff:
        return file_path, diff
    return file_path, None


def upgrade_file(project_file: Path) -> Optional[str]:
    _, yaml = load_for_roundtrip(project_file)
    upgraded = upgrade_to_latest(project_file)
    return yaml_to_string(upgraded, yaml)

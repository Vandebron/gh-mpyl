"""Versioning and upgrade utilities for mpyl projects.
### Writing an upgrade script

To write an upgrade script, create a new class that inherits from `Upgrader` and
implements the `upgrade` method. This class should then be added to the `UPGRADERS`
list in this module.

"""

import copy
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generator
from typing import Optional

from deepdiff import DeepDiff
from ruamel.yaml.compat import ordereddict

from ..project import Project
from ..utilities.yaml import yaml_to_string, load_for_roundtrip, yaml_for_roundtrip

VERSION_FIELD = "projectYmlVersion"
BASE_RELEASE = 1


class Upgrader(ABC):
    """Base class for upgrade scripts"""

    target_version: int
    version_field_position: int

    @abstractmethod
    def works_with(self, project_file: Path):
        pass

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        return previous_dict


class TraefikYamlUpgrader(Upgrader):
    version_field_position = 0

    def works_with(self, project_file: Path):
        return bool(Project.traefik_yaml_file_pattern().match(project_file.name))


class ProjectYamlUpgrader(Upgrader):
    version_field_position = 2

    def works_with(self, project_file: Path):
        return project_file.name == Project.project_yaml_file_name() or bool(
            Project.project_overrides_yaml_file_pattern().match(project_file.name)
        )


class TraefikUpgraderFour(TraefikYamlUpgrader):
    target_version = 4

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        middlewares = previous_dict["traefik"].get("middlewares", [])
        for target in middlewares:
            for middleware in middlewares[target]:
                spec = middleware["spec"]
                if "ipAllowList" in spec:
                    middlewares[target].remove(middleware)

        hosts = previous_dict["traefik"].get("hosts", [])
        for host in hosts:
            if "whitelists" in host:
                del host["whitelists"]

        return previous_dict


class ProjectUpgraderOne(ProjectYamlUpgrader):
    target_version = 1

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        if "mpylVersion" in previous_dict:
            del previous_dict["mpylVersion"]

        return previous_dict


class ProjectUpgraderTwo(ProjectYamlUpgrader):
    target_version = 2
    project_yml_path: Path

    def __init__(self, project_yml_path: Path):
        self.project_yml_path = project_yml_path

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


class ProjectUpgraderThree(ProjectYamlUpgrader):
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
    all_existing_upgraders = (
        ProjectUpgraderOne(),
        ProjectUpgraderTwo(project_file),
        ProjectUpgraderThree(),
        TraefikUpgraderFour(),
    )
    upgraders = list(
        filter(lambda u: u.works_with(project_file), all_existing_upgraders)
    )

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
            upgraded.insert(
                upgrader.version_field_position, VERSION_FIELD, upgrader.target_version
            )
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
    file_paths: list[Path],
) -> Generator[tuple[Path, DeepDiff | None], None, None]:
    all_paths = []
    all_paths += file_paths
    for path in file_paths:
        all_paths += list(path.parent.glob(Project.traefik_yaml_file_glob_pattern()))

    for path in all_paths:
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
    return yaml_to_string(upgraded, yaml, explicit_start=True)

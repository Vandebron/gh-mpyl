"""Versioning and upgrade utilities for mpyl projects.
### Writing an upgrade script

To write an upgrade script, create a new class that inherits from `Upgrader` and
implements the `upgrade` method. This class should then be added to the `UPGRADERS`
list in this module.

"""

import copy
import numbers
from abc import ABC
from pathlib import Path
from typing import Generator
from typing import Optional

from deepdiff import DeepDiff
from ruamel.yaml.compat import ordereddict

from ..utilities.yaml import yaml_to_string, load_for_roundtrip, yaml_for_roundtrip

VERSION_FIELD = "mpylVersion"
BASE_RELEASE = "1.0.8"


class Upgrader(ABC):
    """Base class for upgrade scripts"""

    target_version: str

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        return previous_dict


class ProjectUpgraderOneFour20(Upgrader):
    target_version = "1.4.20"

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        hosts = previous_dict.get("deployment", {}).get("traefik", {}).get("hosts", [])
        for host in hosts:
            if priority := host.get("priority", None):
                if isinstance(priority, numbers.Number) or not any(
                    env in priority
                    for env in ["all", "pr", "test", "acceptance", "production"]
                ):
                    host["priority"] = {}
                    host["priority"]["all"] = priority

        return previous_dict


class ProjectUpgraderOneFour18(Upgrader):
    target_version = "1.4.18"

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        return previous_dict  # To account for the project id upgrade that couldn't be committed


class ProjectUpgraderOneFour15(Upgrader):
    target_version = "1.4.15"

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        job = previous_dict.get("deployment", {}).get("kubernetes", {}).get("job", {})
        if cron := job.get("cron", None):
            if not any(
                env in cron for env in ["all", "pr", "test", "acceptance", "production"]
            ):
                job["cron"] = {}
                job["cron"]["all"] = cron

        return previous_dict


class ProjectUpgraderOne31(Upgrader):
    target_version = "1.3.1"

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        if kubernetes := previous_dict.get("deployment", {}).get("kubernetes", {}):
            if "cmd" in kubernetes:
                kubernetes["command"] = kubernetes.pop("cmd")
        return previous_dict


class ProjectUpgraderOne11(Upgrader):
    target_version = "1.0.11"


class ProjectUpgraderOne10(Upgrader):
    target_version = "1.0.10"

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        if found_deployment := previous_dict.get("deployment", {}):
            existing_namespace = found_deployment.get("namespace", None)
            if not existing_namespace:
                previous_dict["deployment"].insert(
                    0, "namespace", previous_dict["name"]
                )

        return previous_dict


class ProjectUpgraderOne9(Upgrader):
    target_version = "1.0.9"

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        previous_dict.insert(3, VERSION_FIELD, self.target_version)
        return previous_dict


class ProjectUpgraderOne8(Upgrader):
    target_version = BASE_RELEASE

    def upgrade(self, previous_dict: ordereddict) -> ordereddict:
        return previous_dict


PROJECT_UPGRADERS = [
    ProjectUpgraderOne8(),
    ProjectUpgraderOne9(),
    ProjectUpgraderOne10(),
    ProjectUpgraderOne11(),
    ProjectUpgraderOne31(),
    ProjectUpgraderOneFour15(),
    ProjectUpgraderOneFour18(),
    ProjectUpgraderOneFour20(),
]


def get_entry_upgrader_index(
    current_version: str, upgraders: list[Upgrader]
) -> Optional[int]:
    next_index = next(
        (i for i, v in enumerate(upgraders) if v.target_version == current_version),
        None,
    )
    return next_index


def __get_version(project: dict) -> str:
    return project.get(VERSION_FIELD, "1.0.8")


def upgrade_to_latest(
    to_upgrade: ordereddict, upgraders: list[Upgrader]
) -> ordereddict:
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
            upgraded[VERSION_FIELD] = upgrader.target_version
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
    file_path: list[Path], upgraders: list[Upgrader]
) -> Generator[tuple[Path, DeepDiff | None], None, None]:
    for path in file_path:
        yield check_upgrade_needed(path, upgraders)


def check_upgrade_needed(
    file_path: Path, upgraders: list[Upgrader]
) -> tuple[Path, Optional[DeepDiff]]:
    loaded, _ = load_for_roundtrip(file_path)
    upgraded = upgrade_to_latest(loaded, upgraders)
    diff = DeepDiff(loaded, upgraded, ignore_order=True, view="_delta")
    if diff:
        return file_path, diff
    return file_path, None


def upgrade_file(project_file: Path, upgraders: list[Upgrader]) -> Optional[str]:
    to_upgrade, yaml = load_for_roundtrip(project_file)
    upgraded = upgrade_to_latest(copy.deepcopy(to_upgrade), upgraders)
    return yaml_to_string(upgraded, yaml)

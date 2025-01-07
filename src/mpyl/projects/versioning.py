"""Versioning and upgrade utilities for mpyl projects.
### Writing an upgrade script

To write an upgrade script, create a new class that inherits from `Upgrader` and
implements the `upgrade` method. This class should then be added to the `UPGRADERS`
list in this module.

"""

import copy
from abc import ABC
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

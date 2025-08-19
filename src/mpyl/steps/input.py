"""Input passed to execute a step."""

from dataclasses import dataclass

from ruamel.yaml import yaml_object, YAML

from ..project import Project


@yaml_object(YAML())
@dataclass(frozen=False)  # yaml_object classes can't be frozen
class Input:
    project: Project

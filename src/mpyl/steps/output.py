"""Output produced by a step execution."""

from dataclasses import dataclass

from ruamel.yaml import yaml_object, YAML


yaml = YAML()


@yaml_object(yaml)
@dataclass(frozen=False)  # yaml_object classes can't be frozen
class Output:
    success: bool
    message: str

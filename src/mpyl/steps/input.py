"""Input passed to execute a step."""

from dataclasses import dataclass

from ruamel.yaml import yaml_object, YAML

from .models import RunProperties
from ..project_execution import ProjectExecution
from ..run_plan import RunPlan

yaml = YAML()


@yaml_object(yaml)
@dataclass(frozen=False)  # yaml_object classes can't be frozen
class Input:
    project_execution: ProjectExecution
    run_properties: RunProperties
    run_plan: RunPlan

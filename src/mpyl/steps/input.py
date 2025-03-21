"""Input passed to execute a step."""

from dataclasses import dataclass

from ruamel.yaml import yaml_object, YAML


from .models import RunProperties
from ..project import Project
from ..run_plan import RunPlan


@yaml_object(YAML())
@dataclass(frozen=False)  # yaml_object classes can't be frozen
class Input:
    project: Project
    run_properties: RunProperties
    run_plan: RunPlan

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..project import Project
from ..stage import Stage
from ..target import Target
from ruamel.yaml import YAML, yaml_object

yaml = YAML()


@dataclass(frozen=True)
class VersioningProperties:
    revision: str
    pr_number: Optional[str]
    tag: Optional[str]


@yaml_object(yaml)
@dataclass(frozen=True)
class BuildProperties:
    build_id: str
    target: Target
    git: VersioningProperties


@yaml_object(yaml)
@dataclass(frozen=True)
class ArtifactType(Enum):
    def __eq__(self, other):
        return self.value == other.value

    @classmethod
    def from_yaml(cls, constructor, node):
        return ArtifactType(int(node.value.split('-')[1]))

    @classmethod
    def to_yaml(cls, representer, node):
        return representer.represent_scalar(u'!ArtifactType',
                                            '{}-{}'.format(node._name_, node._value_)
                                            )

    DOCKER_IMAGE = 1
    JUNIT_TESTS = 2
    NONE = 3


@yaml_object(yaml)
@dataclass(frozen=True)
class Artifact:
    artifact_type: ArtifactType
    revision: str
    producing_step: str
    spec: dict


@yaml_object(yaml)
@dataclass(frozen=True)
class Input:
    project: Project
    build_properties: BuildProperties
    required_artifact: Optional[Artifact] = None

    def docker_image_tag(self):
        git = self.build_properties.git
        tag = f"pr-{git.pr_number}" if git.pr_number else git.tag
        return f"{self.project.name.lower()}:{tag}"


@yaml_object(yaml)
@dataclass()
class Output:
    success: bool
    message: str
    produced_artifact: Optional[Artifact] = None


@dataclass(frozen=True)
class Meta:
    name: str
    description: str
    version: str
    stage: Stage

    def __str__(self) -> str:
        return f'{self.name}: {self.version}'

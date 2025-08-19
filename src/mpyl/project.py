"""
Datamodel representation of project specific configuration as specified
in the `deployment/project.yml`. It defines how the source code to which it relates
"wants" to be built / tested / deployed.

<details>
  <summary>Schema definition</summary>
```yaml
.. include:: ./schema/project.schema.yml
```
</details>

.. include:: ../../README-dev.md
"""

import logging
import pkgutil
import time
import traceback
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, TypeVar

import jsonschema
from mypy.checker import Generic
from ruamel.yaml import YAML

from .constants import RUN_ARTIFACTS_FOLDER
from .validation import validate

T = TypeVar("T")


def without_keys(dictionary: dict, keys: set[str]):
    return {k: dictionary[k] for k in dictionary.keys() - keys}


@dataclass(frozen=True)
class Target(Enum):
    def __eq__(self, other):
        return self.value == other.value

    def __str__(self):
        return str(self.value)

    @staticmethod
    def from_environment(environment: str):
        if environment == "pull-request":
            return Target.PULL_REQUEST
        if environment == "test":
            return Target.TEST
        if environment == "acceptance":
            return Target.ACCEPTANCE
        if environment == "production":
            return Target.PRODUCTION

        raise ValueError(f"Invalid value for environment: {environment}")

    PULL_REQUEST = "PullRequest"
    TEST = "Test"
    ACCEPTANCE = "Acceptance"
    PRODUCTION = "Production"


@dataclass(frozen=True)
class Stage:
    name: str
    icon: str

    def to_markdown(self) -> str:
        return f"{self.icon} {self.name.capitalize()}"


@dataclass(frozen=True)
class TargetProperty(Generic[T]):
    pr: Optional[T]  # pylint: disable=invalid-name
    test: Optional[T]
    acceptance: Optional[T]
    production: Optional[T]
    all: Optional[T]

    def get_value(self, target: Target):
        if self.all:
            return self.all
        if target == Target.PULL_REQUEST:
            return self.pr
        if target == Target.TEST:
            return self.test
        if target == Target.ACCEPTANCE:
            return self.acceptance
        if target == Target.PRODUCTION:
            return self.production
        return None

    @staticmethod
    def from_config(values: dict):
        if not values:
            return None
        return TargetProperty(
            pr=values.get("pr"),
            test=values.get("test"),
            acceptance=values.get("acceptance"),
            production=values.get("production"),
            all=values.get("all"),
        )


@dataclass(frozen=True)
class KeyValueProperty(TargetProperty[str]):
    key: str

    @staticmethod
    def from_config(values: dict):
        return KeyValueProperty(
            key=values["key"],
            pr=values.get("pr"),
            test=values.get("test"),
            acceptance=values.get("acceptance"),
            production=values.get("production"),
            all=values.get("all"),
        )


@dataclass(frozen=True)
class KeyValueRef:
    key: str
    value_from: dict

    @staticmethod
    def from_config(values: dict):
        key = values["key"]
        value_from = values["valueFrom"]

        return KeyValueRef(
            key=key,
            value_from=value_from,
        )


@dataclass(frozen=True)
class EnvCredential:
    key: str
    secret_id: str

    @staticmethod
    def from_config(values: dict):
        key = values.get("key")
        secret_id = values.get("id")
        if not key or not secret_id:
            raise KeyError("Credential must have a key and id set.")
        return EnvCredential(key, secret_id)


@dataclass(frozen=True)
class StageSpecificProperty(Generic[T]):
    stages: dict[str, Optional[T]]

    def for_stage(self, stage: str) -> Optional[T]:
        if stage not in self.stages.keys():
            return None
        return self.stages[stage]


@dataclass(frozen=True)
class Stages(StageSpecificProperty[str]):
    def all(self) -> dict[str, Optional[str]]:
        return self.stages

    @staticmethod
    def from_config(values: dict):
        return Stages(values)


@dataclass(frozen=True)
class Dependencies(StageSpecificProperty[set[str]]):
    def set_for_stage(self, stage: str) -> set[str]:
        deps_for_stage = self.for_stage(stage)
        return deps_for_stage if deps_for_stage else set()

    def all(self) -> dict[str, set[str]]:
        return {key: self.set_for_stage(key) for key in self.stages.keys()}

    @staticmethod
    def from_config(values: dict):
        return Dependencies(values)


@dataclass(frozen=True)
class Env:
    @staticmethod
    def from_config(values: list[dict]):
        return list(map(KeyValueProperty.from_config, values))


@dataclass(frozen=True)
class Project:
    name: str
    description: str
    path: str
    pipeline: Optional[str]
    stages: Stages
    maintainer: list[str]
    dependencies: Optional[Dependencies]

    def __lt__(self, other):
        return self.path < other.path

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self):
        return hash(self.path)

    @staticmethod
    def project_yaml_file_name() -> str:
        return "project.yml"

    @property
    def root_path(self) -> Path:
        return Path(self.path).parent.parent

    @property
    def deployment_path(self) -> Path:
        return Path(self.path).parent

    @property
    def target_path(self) -> Path:
        return self.deployment_path / RUN_ARTIFACTS_FOLDER

    @property
    def test_report_path(self) -> Path:
        return Path(self.root_path) / "target/test-reports"

    @staticmethod
    def from_config(values: dict, project_path: Path):
        dependencies = values.get("dependencies")
        return Project(
            name=values["name"],
            description=values["description"],
            path=str(project_path),
            pipeline=values.get("pipeline"),
            stages=Stages.from_config(values.get("stages", {})),
            maintainer=values.get("maintainer", []),
            dependencies=(
                Dependencies.from_config(dependencies) if dependencies else None
            ),
        )


def validate_project(yaml_values: dict) -> dict:
    """
    :type yaml_values: the yaml dictionary to validate
    :return: the validated schema
    :raises `jsonschema.exceptions.ValidationError` when validation fails
    """
    template = pkgutil.get_data(__name__, "schema/project.schema.yml")
    if not template:
        raise ValueError("Schema project.schema.yml not found in package")
    validate(yaml_values, template.decode("utf-8"))

    return yaml_values


def load_traefik_config(traefik_path: Path, loader: YAML) -> Optional[dict]:
    if not traefik_path.exists():
        return None

    with open(traefik_path, encoding="utf-8") as file:
        return loader.load(file)


def load_project(  # pylint: disable=too-many-locals
    project_path: Path,
    validate_project_yaml: bool,
    log: bool = True,
) -> Project:
    """
    Load a `project.yml` to `Project` data class
    :param project_path: path to the `project.yml`
    :param validate_project_yaml: indicates whether the schema should be validated
    :param log: indicates whether problems should be logged as warning
    :return: `Project` data class
    """
    log_level = logging.WARNING if log else logging.DEBUG
    with open(project_path, encoding="utf-8") as file:
        try:
            start = time.time()
            loader: YAML = YAML()
            yaml_values: dict = loader.load(file)

            if validate_project_yaml:
                validate_project(yaml_values)
            project = Project.from_config(yaml_values, project_path)
            logging.debug(
                f"Loaded project {project.path} in {(time.time() - start) * 1000} ms"
            )
            return project
        except jsonschema.exceptions.ValidationError as exc:
            logging.log(
                log_level, f"{project_path} does not comply with schema: {exc.message}"
            )
            raise
        except TypeError:
            traceback.print_exc()
            logging.log(log_level, "Type error", exc_info=True)
            raise
        except Exception:
            logging.log(log_level, f"Failed to load {project_path}", exc_info=True)
            raise

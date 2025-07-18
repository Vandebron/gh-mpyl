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
from typing import Optional, TypeVar, Any, List

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
class Properties:
    env: list[KeyValueProperty]
    sealed_secrets: list[KeyValueProperty]
    kubernetes: list[KeyValueRef]

    @staticmethod
    def from_config(values: dict[Any, Any]):
        return Properties(
            env=list(map(KeyValueProperty.from_config, values.get("env", []))),
            sealed_secrets=list(
                map(KeyValueProperty.from_config, values.get("sealedSecret", []))
            ),
            kubernetes=list(map(KeyValueRef.from_config, values.get("kubernetes", []))),
        )


@dataclass(frozen=True)
class Probe:
    path: TargetProperty[str]
    values: dict

    @staticmethod
    def from_config(values: dict):
        if not values:
            return None
        return Probe(path=TargetProperty.from_config(values["path"]), values=values)


@dataclass(frozen=True)
class Alert:
    name: str
    expr: str
    for_duration: str
    description: str
    severity: str

    @staticmethod
    def from_config(values: dict):
        name = values.get("name")
        expr = values.get("expr")
        for_duration = values.get("forDuration")
        description = values.get("description")
        severity = values.get("severity")
        if not name or not expr or not for_duration or not description or not severity:
            raise KeyError(
                "Alerts must have a name, expr, forDuration, description and severity set."
            )
        return Alert(name, expr, for_duration, description, severity)


@dataclass(frozen=True)
class Metrics:
    path: str
    port: Optional[str]
    enabled: bool
    alerts: list[Alert]

    @staticmethod
    def from_config(values: dict):
        if not values:
            return None
        return Metrics(
            path=values.get("path", "/metrics"),
            port=values.get("port", None),
            enabled=values.get("enabled", False),
            alerts=[Alert.from_config(v) for v in values.get("alerts", [])],
        )


@dataclass(frozen=True)
class ResourceSpecification:
    cpus: Optional[TargetProperty[float]]
    mem: Optional[TargetProperty[int]]
    disk: Optional[TargetProperty[int]]

    @staticmethod
    def from_config(values: dict):
        return ResourceSpecification(
            cpus=TargetProperty.from_config(values.get("cpus", {})),
            mem=TargetProperty.from_config(values.get("mem", {})),
            disk=TargetProperty.from_config(values.get("disk", {})),
        )


@dataclass(frozen=True)
class Resources:
    instances: Optional[TargetProperty[int]]
    limit: Optional[ResourceSpecification]
    request: Optional[ResourceSpecification]

    @staticmethod
    def from_config(values: dict):
        return Resources(
            instances=TargetProperty.from_config(values.get("instances", {})),
            limit=ResourceSpecification.from_config(values.get("limit", {})),
            request=ResourceSpecification.from_config(values.get("request", {})),
        )


@dataclass(frozen=True)
class Job:
    cron: TargetProperty[dict]
    job: dict

    @staticmethod
    def from_config(values: dict):
        if not values:
            return None
        return Job(
            cron=TargetProperty.from_config(values.get("cron", {})),
            job=without_keys(values, {"cron"}),
        )


@dataclass(frozen=True)
class Kubernetes:
    port_mappings: dict[int, int]
    liveness_probe: Optional[Probe]
    startup_probe: Optional[Probe]
    metrics: Optional[Metrics]
    resources: Resources
    job: Optional[Job]
    command: Optional[TargetProperty[str]]
    args: Optional[TargetProperty[str]]
    labels: Optional[list[KeyValueProperty]]
    deployment_strategy: Optional[dict]
    pod_security_context: Optional[dict]
    security_context: Optional[dict]

    @staticmethod
    def from_config(values: dict):
        return Kubernetes(
            port_mappings=values.get("portMappings", {}),
            liveness_probe=Probe.from_config(values.get("livenessProbe", {})),
            startup_probe=Probe.from_config(values.get("startupProbe", {})),
            metrics=Metrics.from_config(values.get("metrics", {})),
            resources=Resources.from_config(values.get("resources", {})),
            job=Job.from_config(values.get("job", {})),
            command=TargetProperty.from_config(values.get("command", {})),
            args=TargetProperty.from_config(values.get("args", {})),
            labels=list(map(KeyValueProperty.from_config, values.get("labels", []))),
            deployment_strategy=values.get("deploymentStrategy", {}),
            pod_security_context=values.get("podSecurityContext", None),
            security_context=values.get("securityContext", None),
        )


@dataclass(frozen=True)
class KubernetesCommon:
    namespace: TargetProperty[str]

    @staticmethod
    def from_config(values: dict):
        return KubernetesCommon(
            namespace=TargetProperty.from_config(values.get("namespace", {})),
        )


@dataclass(frozen=True)
class TraefikAdditionalRoute:
    name: str
    middlewares: list[str]
    entrypoints: list[str]

    @staticmethod
    def from_config(values: Optional[dict]):
        if not values:
            return None
        return TraefikAdditionalRoute(
            name=values.get("name", ""),
            middlewares=values.get("middlewares", []),
            entrypoints=values.get("entrypoints", []),
        )


@dataclass(frozen=True)
class TraefikHost:
    host: TargetProperty[str]
    service_port: Optional[int]
    has_swagger: bool
    tls: Optional[TargetProperty[str]]
    whitelists: TargetProperty[list[str]]
    priority: Optional[TargetProperty[int]]
    insecure: bool
    additional_route: Optional[str]
    syntax: Optional[TargetProperty[str]]

    @staticmethod
    def from_config(values: dict):
        return TraefikHost(
            host=TargetProperty.from_config(values.get("host", {})),
            service_port=values.get("servicePort"),
            has_swagger=values.get("hasSwagger", True),
            tls=TargetProperty.from_config(values.get("tls", {})),
            whitelists=TargetProperty.from_config(values.get("whitelists", {})),
            priority=TargetProperty.from_config(values.get("priority", {})),
            insecure=values.get("insecure", False),
            additional_route=values.get("additionalRoute", None),
            syntax=TargetProperty.from_config(values.get("syntax", {})),
        )


@dataclass
class DagsterSecret:
    name: str

    @staticmethod
    def from_config(values: dict):
        return DagsterSecret(name=values.get("name", ""))


@dataclass(frozen=True)
class Dagster:
    repo: str
    secrets: List[DagsterSecret]
    readiness_probe_script: Optional[str]

    @staticmethod
    def from_config(values: dict):
        return Dagster(
            repo=values.get("repo", ""),
            secrets=[DagsterSecret.from_config(v) for v in values.get("secrets", [])],
            readiness_probe_script=values.get("readinessProbeScript"),
        )


@dataclass(frozen=True)
class Traefik:
    hosts: list[TraefikHost]
    ingress_routes: Optional[TargetProperty[dict]]
    middlewares: Optional[TargetProperty[list[dict]]]

    @staticmethod
    def from_config(values: dict):
        hosts = values.get("hosts")
        return Traefik(
            hosts=(list(map(TraefikHost.from_config, hosts) if hosts else [])),
            ingress_routes=TargetProperty.from_config(values.get("ingressRoutes", {})),
            middlewares=TargetProperty.from_config(values.get("middlewares", {})),
        )


@dataclass(frozen=True)
class Deployment:
    name: str
    properties: Optional[Properties]
    _kubernetes: Optional[Kubernetes]
    traefik: Optional[Traefik]

    @staticmethod
    def from_config(values: dict):
        props = values.get("properties")
        kubernetes = values.get("kubernetes")
        traefik = values.get("traefik")

        return Deployment(
            name=values["name"].lower(),
            properties=Properties.from_config(props) if props else None,
            _kubernetes=Kubernetes.from_config(kubernetes) if kubernetes else None,
            traefik=Traefik.from_config(traefik) if traefik else None,
        )

    def has_kubernetes(self) -> bool:
        return self._kubernetes is not None

    @property
    def kubernetes(self) -> Kubernetes:
        if not self._kubernetes:
            raise KeyError(
                f"Deployment '{self.name}' does not have kubernetes configuration"
            )

        return self._kubernetes


@dataclass(frozen=True)
class Project:
    name: str
    description: str
    path: str
    pipeline: Optional[str]
    stages: Stages
    maintainer: list[str]
    deployments: list[Deployment]
    dependencies: Optional[Dependencies]
    kubernetes: Optional[KubernetesCommon]
    _dagster: Optional[Dagster]

    def __lt__(self, other):
        return self.path < other.path

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self):
        return hash(self.path)

    def namespace(self, target: Target) -> str:
        return (
            self.kubernetes.namespace.get_value(target)
            if self.kubernetes and self.kubernetes.namespace
            else self.name
        )

    @property
    def dagster(self) -> Dagster:
        if self._dagster is None:
            raise KeyError(f"Project '{self.name}' does not have dagster configuration")
        return self._dagster

    @staticmethod
    def project_yaml_file_name() -> str:
        return "project.yml"

    @staticmethod
    def traefik_yaml_file_name(deployment_name: str) -> str:
        return f"{deployment_name}-traefik.yml"

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
        kubernetes_values = values.get("kubernetes", {})
        dagster = values.get("dagster")
        deployment_old = values.get("deployment", {})
        if (
            deployment_old
        ):  # Deprecated, only used for old tags. Remove in a month or so after this commit
            deployment_old["name"] = values["name"]
            deployment_list = [deployment_old]

            old_namespace = deployment_old.get("namespace")
            if old_namespace:
                kubernetes_values["namespace"] = {}
                kubernetes_values["namespace"]["all"] = old_namespace

            dagster_old = deployment_old.get("dagster")
            if dagster_old:
                dagster = dagster_old
        else:
            deployment_list = values.get("deployments", [])
        deployments = [
            Deployment.from_config(deployment) for deployment in deployment_list
        ]
        dependencies = values.get("dependencies")

        return Project(
            name=values["name"],
            description=values["description"],
            path=str(project_path),
            pipeline=values.get("pipeline"),
            stages=Stages.from_config(values.get("stages", {})),
            maintainer=values.get("maintainer", []),
            deployments=deployments,
            dependencies=(
                Dependencies.from_config(dependencies) if dependencies else None
            ),
            _dagster=Dagster.from_config(dagster) if dagster else None,
            kubernetes=KubernetesCommon.from_config(kubernetes_values),
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

            deployment_old = yaml_values.get(
                "deployment"
            )  # deprecated, can be removed in a month
            deployments = (
                [deployment_old]
                if deployment_old
                else yaml_values.get("deployments", [])
            )
            for deployment in deployments:
                deployment_name = deployment.get("name") or yaml_values.get("name", "")
                traefik_config = load_traefik_config(
                    project_path.parent
                    / Project.traefik_yaml_file_name(deployment_name),
                    loader,
                )
                if traefik_config:
                    deployment["traefik"] = traefik_config["traefik"]
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

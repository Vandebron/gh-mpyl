"""Docker related utility methods"""

from dataclasses import dataclass
from typing import Dict, Optional

from ruamel.yaml import yaml_object, YAML

from ...project import Project
from ...steps.models import Input, ArtifactSpec

yaml = YAML()


@yaml_object(yaml)
@dataclass
class DockerImageSpec(ArtifactSpec):
    yaml_tag = "!DockerImageSpec"
    image: str


@dataclass(frozen=True)
class DockerComposeConfig:
    period_seconds: int
    failure_threshold: int

    @property
    def total_duration(self):
        return self.period_seconds * self.failure_threshold

    @staticmethod
    def from_yaml(config: dict):
        compose_config = config.get("docker", {}).get("compose")
        if not compose_config:
            raise KeyError("docker.compose needs to be defined")
        return DockerComposeConfig(
            period_seconds=int(compose_config["periodSeconds"]),
            failure_threshold=int(compose_config["failureThreshold"]),
        )


@dataclass(frozen=True)
class DockerCacheConfig:
    cache_to: str
    cache_from: str

    @staticmethod
    def from_dict(config: Dict):
        return DockerCacheConfig(config["to"], config["from"])


@dataclass(frozen=True)
class DockerRegistryConfig:
    host_name: str
    organization: Optional[str]
    user_name: str
    password: str
    provider: Optional[str]
    region: Optional[str]
    cache_from_registry: bool
    custom_cache_config: Optional[DockerCacheConfig]

    @staticmethod
    def from_dict(config: dict):
        try:
            cache_config = config.get("cache", {})
            return DockerRegistryConfig(
                host_name=config["hostName"],
                user_name=config["userName"],
                organization=config.get("organization", None),
                password=config["password"],
                provider=config.get("provider", None),
                region=config.get("region", None),
                cache_from_registry=cache_config.get("cacheFromRegistry", False),
                custom_cache_config=(
                    DockerCacheConfig.from_dict(cache_config["custom"])
                    if "custom" in cache_config
                    else None
                ),
            )
        except KeyError as exc:
            raise KeyError(f"Docker config could not be loaded from {config}") from exc


@dataclass(frozen=True)
class DockerConfig:
    default_registry: str
    registries: list[DockerRegistryConfig]
    root_folder: str
    build_target: Optional[str]
    test_target: Optional[str]
    docker_file_name: str

    @staticmethod
    def from_dict(config: dict):
        try:
            registries: dict = config["docker"]["registries"]
            build_config: dict = config["docker"]["build"]
            return DockerConfig(
                default_registry=config["docker"]["defaultRegistry"],
                registries=[DockerRegistryConfig.from_dict(r) for r in registries],
                root_folder=build_config["rootFolder"],
                build_target=build_config.get("buildTarget", None),
                test_target=build_config.get("testTarget", None),
                docker_file_name=build_config["dockerFileName"],
            )
        except KeyError as exc:
            raise KeyError(f"Docker config could not be loaded from {config}") from exc


def docker_image_tag(step_input: Input) -> str:
    git = step_input.run_properties.versioning
    tag = git.tag if git.tag else f"pr-{git.pr_number}"
    return f"{step_input.project_execution.name.lower()}:{tag}".replace("/", "_")


def registry_for_project(
    docker_config: DockerConfig, project: Project
) -> DockerRegistryConfig:
    host_name = (
        project.docker.host_name if project.docker else docker_config.default_registry
    )
    registry = next(r for r in docker_config.registries if r.host_name == host_name)
    if registry:
        return registry

    raise KeyError(f"Docker config has no registry with host name {host_name}")

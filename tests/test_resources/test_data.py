import dataclasses
import os
from pathlib import Path
from typing import Optional

from attr import dataclass

from src.mpyl.constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
)
from src.mpyl.project import load_project, Target, Project, Stages, Stage
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.steps.models import RunProperties
from src.mpyl.utilities.pyaml_env import parse_config
from tests import root_test_path

resource_path = root_test_path / "test_resources"
config_values = parse_config(resource_path / DEFAULT_CONFIG_FILE_NAME)
properties_values = parse_config(resource_path / DEFAULT_RUN_PROPERTIES_FILE_NAME)


def stub_run_properties(
    config: dict = config_values,
    properties: dict = properties_values,
    deploy_image: Optional[str] = None,
):
    return RunProperties.from_configuration(
        target=Target.PULL_REQUEST,
        run_properties=properties,
        config=config,
        deploy_image=deploy_image,
    )


RUN_PROPERTIES = stub_run_properties()

RUN_PROPERTIES_PROD = dataclasses.replace(
    RUN_PROPERTIES,
    target=Target.PRODUCTION,
    versioning=dataclasses.replace(
        RUN_PROPERTIES.versioning, tag="20230829-1234", pr_number=None
    ),
)


@dataclass(frozen=True)
class TestStage:
    @staticmethod
    def build():
        return Stage(name="build", icon="🏗️")

    @staticmethod
    def test():
        return Stage(name="test", icon="📋")

    @staticmethod
    def deploy():
        return Stage(name="deploy", icon="🚀")

    @staticmethod
    def post_deploy():
        return Stage(name="postdeploy", icon="🧪")


def get_config_values() -> dict:
    return config_values


def get_project() -> Project:
    return safe_load_project(f"{resource_path}/test_projects/test_project.yml")


def get_project_traefik() -> Project:
    return safe_load_project(f"{resource_path}/test_projects/test_project_traefik.yml")


def get_project_execution() -> ProjectExecution:
    return ProjectExecution.run(get_project())


def get_deployment_strategy_project() -> Project:
    return safe_load_project(
        f"{resource_path}/test_projects/test_project_deployment_strategy.yml"
    )


def get_minimal_project() -> Project:
    return safe_load_project(f"{resource_path}/test_projects/test_minimal_project.yml")


def get_project_without_swagger() -> Project:
    return safe_load_project(
        f"{resource_path}/test_projects/test_project_without_swagger.yml"
    )


def get_job_project() -> Project:
    return safe_load_project(f"{resource_path}/test_projects/test_job_project.yml")


def get_cron_job_project() -> Project:
    return safe_load_project(f"{resource_path}/test_projects/test_cron_job_project.yml")


def safe_load_project(name: str) -> Project:
    return load_project(Path(name), validate_project_yaml=True, log=False)


def get_project_with_stages(
    stage_config: dict, path: str = "deployment/project.yml", maintainers=None
):
    if maintainers is None:
        maintainers = ["Team1", "Team2"]
    stages = Stages.from_config(stage_config)
    return Project(
        "test", "Test project", path, None, stages, maintainers, None, None, None, None
    )


def assert_roundtrip(file_path: Path, actual_contents: str, overwrite: bool = False):
    if overwrite:
        if not file_path.exists():
            os.makedirs(file_path.parent, exist_ok=True)

        with open(file_path, "w+", encoding="utf-8") as file:
            file.write(actual_contents)
            assert not overwrite, "Should not commit with overwrite"

    with open(file_path, encoding="utf-8") as file:
        assert actual_contents == file.read()

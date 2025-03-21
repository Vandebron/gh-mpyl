import logging
from logging import Logger

import pytest
from jsonschema import ValidationError
from pyaml_env import parse_config
from ruamel.yaml import YAML

from src.mpyl.constants import DEFAULT_CONFIG_FILE_NAME, RUN_ARTIFACTS_FOLDER
from src.mpyl.project import Project, Stages, Target
from src.mpyl.projects.versioning import yaml_to_string
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.collection import StepsCollection
from src.mpyl.steps.executor import Executor
from src.mpyl.steps.models import (
    RunProperties,
    VersioningProperties,
)
from src.mpyl.steps.output import Output
from tests import root_test_path, test_resource_path
from tests.test_resources import test_data
from tests.test_resources.test_data import assert_roundtrip, RUN_PROPERTIES, TestStage

yaml = YAML()


class TestSteps:
    resource_path = root_test_path / "test_resources"
    executor = Executor(
        logger=logging.getLogger(),
        run_properties=test_data.RUN_PROPERTIES,
        run_plan=RunPlan.empty(),
        steps_collection=StepsCollection(logging.getLogger()),
    )

    docker_image = Output(success=True, message="build success")

    build_project = test_data.get_project_with_stages(
        {"build": "Echo Build"}, path=str(resource_path / "deployment" / "project.yml")
    )

    @staticmethod
    def _roundtrip(output) -> Output:
        output_string = yaml_to_string(output, yaml)
        return yaml.load(output_string)

    def test_output_no_artifact_roundtrip(self):
        output: Output = self._roundtrip(Output(success=True, message="build success"))
        assert output.message == "build success"

    def test_write_output(self):
        build_yaml = yaml_to_string(self.docker_image, yaml)
        assert_roundtrip(
            test_resource_path / "deployment" / RUN_ARTIFACTS_FOLDER / "build.yml",
            build_yaml,
        )

    def test_write_deploy_output(self):
        output = Output(success=True, message="deploy success  success")

        assert_roundtrip(
            test_resource_path / "deployment" / RUN_ARTIFACTS_FOLDER / "deploy.yml",
            yaml_to_string(output, yaml),
        )

    def test_should_return_error_if_stage_not_defined(self):
        steps = Executor(
            logger=Logger.manager.getLogger("logger"),
            run_properties=test_data.RUN_PROPERTIES,
            run_plan=RunPlan.empty(),
        )
        stages = Stages(
            {"build": None, "test": None, "deploy": None, "postdeploy": None}
        )
        project = Project(
            name="test",
            description="Test project",
            path="",
            pipeline=None,
            stages=stages,
            maintainer=[],
            deployments=[],
            dependencies=None,
            kubernetes=None,
            _dagster=None,
        )
        output = steps.execute(
            stage=TestStage.deploy(),
            project=project,
        ).output
        assert not output.success
        assert output.message == "Stage 'deploy' not defined on project 'test'"

    def test_should_return_error_if_config_invalid(self):
        config_values = parse_config(self.resource_path / DEFAULT_CONFIG_FILE_NAME)
        config_values["kubernetes"] = {}
        properties = RunProperties(
            details=RUN_PROPERTIES.details,
            target=Target.PULL_REQUEST,
            versioning=VersioningProperties("", "feature/ARC-123", 1, None),
            config=config_values,
            stages=[],
        )
        with pytest.raises(ValidationError) as excinfo:
            Executor(
                logger=Logger.manager.getLogger("logger"),
                run_properties=properties,
                run_plan=RunPlan.empty(),
            )
        assert "'deploymentStrategy' is a required property" in excinfo.value.message

    def test_should_succeed_if_step_is_known(self):
        project = test_data.get_project_with_stages(
            stage_config={"deploy": "Echo Deploy"},
            path=str(self.resource_path / "metapath" / "project.yml"),
        )
        result = self.executor.execute(
            stage=TestStage.deploy(),
            project=project,
        )
        assert result.output.success
        assert result.output.message == "Deployed project test"

    def test_should_fail_if_step_is_not_known(self):
        project = test_data.get_project_with_stages({"deploy": "Unknown Deploy"})
        result = self.executor.execute(
            stage=TestStage.deploy(),
            project=project,
        )
        assert not result.output.success
        assert (
            result.output.message
            == "Step 'Unknown Deploy' for 'deploy' not known or registered"
        )

    def test_should_fail_if_maintainer_is_not_known(self):
        project = test_data.get_project_with_stages(
            stage_config={"deploy": "Echo Deploy"},
            path="",
            maintainers=["Unknown Team"],
        )

        result = self.executor.execute(
            stage=TestStage.deploy(),
            project=project,
        )
        assert not result.output.success
        assert (
            result.output.message
            == "Maintainer(s) 'Unknown Team' not defined in config"
        )

    def test_should_succeed_if_stage_is_not_known(self):
        project = test_data.get_project_with_stages(stage_config={"test": "Some Test"})
        result = self.executor.execute(
            stage=TestStage.build(),
            project=project,
        )
        assert not result.output.success
        assert result.output.message == "Stage 'build' not defined on project 'test'"

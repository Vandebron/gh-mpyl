import logging

import pytest

from src.mpyl.build import _run_deploy_stage
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.executor import ExecutionException
from src.mpyl.steps.input import Input
from src.mpyl.steps.output import Output
from src.mpyl.steps.step import Meta, Step
from tests import root_test_path
from tests.cli.commands import invoke, config_path, run_properties_path
from tests.cli.commands.health.test_health import TestConsole
from tests.test_resources.test_data import (
    get_minimal_project,
    RUN_PROPERTIES,
    get_project_with_stages,
    TestStage,
    stub_run_properties,
)


class ThrowingStep(Step):
    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Throwing Deploy",
                description="Throwing deploy step to validate error handling",
                version="0.0.1",
                stage=TestStage.deploy().name,
            ),
        )

    def execute(self, step_input: Input) -> Output:
        raise ExecutionException("test", "tester", "deploy", "this is not good")


class TestBuildCli:
    logger = logging.getLogger()
    console = TestConsole()

    def test_run_without_project_in_plan_should_fail(self):
        with pytest.raises(ValueError):
            _run_deploy_stage(
                logger=self.logger,
                console=self.console,
                run_properties=RUN_PROPERTIES,
                run_plan=RunPlan.empty(),
                project_name_to_run="a project not in the run plan",
            )

    def test_run_with_project_in_plan_should_execute_successfully(self):
        project = get_minimal_project()
        run_plan = RunPlan.create(
            all_known_projects={project},
            plan={
                TestStage.deploy(): {(ProjectExecution.run(project))},
            },
        )
        result = _run_deploy_stage(
            logger=self.logger,
            console=self.console,
            run_properties=stub_run_properties(),
            run_plan=run_plan,
            project_name_to_run=project.name,
        )
        assert result._exception is None
        assert result.is_success
        assert result._exception is None

    def test_run_with_failing_project_should_be_handled(self):
        project = get_project_with_stages({"deploy": "Throwing Deploy"})
        run_plan = RunPlan.create(
            all_known_projects={project},
            plan={TestStage.deploy(): {ProjectExecution.run(project)}},
        )

        result = _run_deploy_stage(
            logger=self.logger,
            console=self.console,
            run_properties=stub_run_properties(),
            run_plan=run_plan,
            project_name_to_run=project.name,
        )

        assert not result.has_results
        assert result._exception
        assert result._exception.message == "this is not good"
        assert result._exception.stage == TestStage.deploy().name
        assert result._exception.project_name == "test"
        assert result._exception.step == "Throwing Deploy"

    def test_build_clean_output(self):
        result = invoke(
            args=[
                "build",
                "-e",
                "pull-request",
                "-c",
                str(config_path),
                "-p",
                str(run_properties_path),
                "clean",
            ],
            env={
                "CHANGED_FILES_PATH": f"{root_test_path}/test_resources/changed-files/"
            },
        )

        assert "Nothing to clean" in result.output

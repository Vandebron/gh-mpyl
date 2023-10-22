import logging
import os
import re

from click.testing import CliRunner

from mpyl.steps.build import STAGE_NAME
from src.mpyl import main_group, add_commands
from src.mpyl.build import run_build
from src.mpyl.project import Stage
from src.mpyl.steps import Step, Meta, ArtifactType, Input, Output
from src.mpyl.steps.run import RunResult
from src.mpyl.steps.steps import Steps, StepsCollection
from tests import root_test_path
from tests.test_resources.test_data import (
    get_minimal_project,
    RUN_PROPERTIES,
    get_project_with_stages,
    assert_roundtrip,
    TestStage,
)


class ThrowingStep(Step):
    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Throwing Build",
                description="Throwing build step to validate error handling",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
            produced_artifact=ArtifactType.NONE,
            required_artifact=ArtifactType.NONE,
        )

    def execute(self, step_input: Input) -> Output:
        raise Exception("this is not good")


class TestBuildCommand:
    resource_path = root_test_path / "cli" / "test_resources"
    config_path = root_test_path / "test_resources/mpyl_config.yml"
    run_properties_path = root_test_path / "test_resources/run_properties.yml"
    runner = CliRunner()
    add_commands()

    def test_run_build_without_plan_should_be_successful(self):
        run_properties = RUN_PROPERTIES
        accumulator = RunResult(run_properties=run_properties)
        executor = Steps(
            logging.getLogger(),
            run_properties,
            StepsCollection(logging.getLogger()),
        )
        result = run_build(accumulator, executor, None)
        assert not result.has_results
        assert result.is_success
        assert result.status_line == "🦥 Nothing to do"

    def test_run_build_with_plan_should_execute_successfully(self):
        run_properties = RUN_PROPERTIES

        projects = [get_minimal_project()]
        run_plan = {
            TestStage.build(): projects,
            TestStage.test(): projects,
            TestStage.deploy(): projects,
        }
        accumulator = RunResult(run_properties=run_properties, run_plan=run_plan)
        collection = StepsCollection(logging.getLogger())
        executor = Steps(
            logging.getLogger(),
            run_properties,
            collection,
        )
        result = run_build(accumulator, executor, None)
        assert result.exception is None
        assert result.status_line == "✅ Successful"
        assert result.is_success

        assert result.exception is None

    def test_run_build_throwing_step_should_be_handled(self):
        run_properties = RUN_PROPERTIES

        projects = [get_project_with_stages({"build": "Throwing Build"})]
        run_plan = {TestStage.build(): projects}
        accumulator = RunResult(run_properties=run_properties, run_plan=run_plan)
        logger = logging.getLogger()
        collection = StepsCollection(logger)
        executor = Steps(logger, run_properties, collection)

        result = run_build(accumulator, executor, None)
        assert not result.has_results
        assert result.status_line == "❗ Failed with exception"

        assert result.exception.message == "this is not good"
        assert result.exception.stage == TestStage.build().name
        assert result.exception.project_name == "test"
        assert result.exception.executor == "Throwing Build"

    def test_build_status_output(self):
        os.environ["CHANGE_ID"] = "123"
        cmd = [
            "build",
            "-c",
            str(self.config_path),
            "-p",
            str(self.run_properties_path),
            "status",
        ]
        result = self.runner.invoke(
            main_group,
            cmd,
        )

        without_upgrade_suggestion = re.sub(
            r".*You can upgrade.*", "", result.output
        ).rstrip()
        without_upgrade_suggestion = re.sub("git:.*", "", without_upgrade_suggestion)
        first_lines_only = "\n".join(
            without_upgrade_suggestion.split("\n")[0:2]
        ).rstrip()

        self.maxDiff = None
        assert_roundtrip(self.resource_path / "build_status.txt", first_lines_only)

    def test_build_clean_output(self):
        result = self.runner.invoke(
            main_group,
            [
                "build",
                "-c",
                str(self.config_path),
                "-p",
                str(self.run_properties_path),
                "clean",
                "--filter",
                "non_existing_project",
            ],
        )

        assert "Nothing to clean" in result.output
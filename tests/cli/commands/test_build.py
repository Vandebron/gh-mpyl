import logging

from src.mpyl.build import run_build
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.build import STAGE_NAME
from src.mpyl.steps.executor import Executor, StepsCollection, ExecutionException
from src.mpyl.steps.input import Input
from src.mpyl.steps.output import Output
from src.mpyl.steps.run import RunResult
from src.mpyl.steps.step import Meta, Step
from tests import root_test_path
from tests.cli.commands import invoke, config_path, run_properties_path
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
                name="Throwing Build",
                description="Throwing build step to validate error handling",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
        )

    def execute(self, step_input: Input) -> Output:
        raise ExecutionException("test", "tester", "build", "this is not good")


class TestBuildCli:
    logger = logging.getLogger()

    def test_run_build_without_plan_should_be_successful(self):
        run_properties = RUN_PROPERTIES
        run_plan = RunPlan.empty()

        accumulator = RunResult(run_properties=run_properties, run_plan=run_plan)
        executor = Executor(
            logging.getLogger(),
            run_properties=run_properties,
            run_plan=run_plan,
            steps_collection=StepsCollection(logging.getLogger()),
        )
        result = run_build(self.logger, accumulator, executor)
        assert not result.has_results
        assert result.is_success
        assert result.status_line == "🦥 Nothing to do"

    def test_run_build_with_plan_should_execute_successfully(self):
        project = get_minimal_project()
        project_executions = {ProjectExecution.run(project)}
        run_plan = RunPlan.create(
            all_known_projects={project},
            plan={
                TestStage.build(): project_executions,
                TestStage.test(): project_executions,
                TestStage.deploy(): project_executions,
            },
        )
        run_properties = stub_run_properties()
        accumulator = RunResult(run_properties=run_properties, run_plan=run_plan)
        collection = StepsCollection(logging.getLogger())
        executor = Executor(
            logging.getLogger(),
            run_properties=run_properties,
            run_plan=run_plan,
            steps_collection=collection,
        )
        result = run_build(self.logger, accumulator, executor)
        assert result.exception is None
        assert result.status_line == "✅ Successful"
        assert result.is_success
        assert result.exception is None

    def test_run_build_throwing_step_should_be_handled(self):
        projects = {get_project_with_stages({"build": "Throwing Build"})}
        run_plan = RunPlan.create(
            all_known_projects=projects,
            plan={TestStage.build(): {ProjectExecution.run(p) for p in projects}},
        )
        run_properties = stub_run_properties()
        accumulator = RunResult(run_properties=run_properties, run_plan=run_plan)
        logger = logging.getLogger()
        collection = StepsCollection(logger)
        executor = Executor(
            logger,
            run_properties=run_properties,
            run_plan=run_plan,
            steps_collection=collection,
        )

        result = run_build(self.logger, accumulator, executor)
        assert not result.has_results
        assert result.status_line == "❗ Failed with exception"

        assert result.exception.message == "this is not good"
        assert result.exception.stage == TestStage.build().name
        assert result.exception.project_name == "test"
        assert result.exception.step == "Throwing Build"

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
                "CHANGED_FILES_PATH": f"{root_test_path}/test_resources/repository/changed_files.json"
            },
        )

        assert "Nothing to clean" in result.output

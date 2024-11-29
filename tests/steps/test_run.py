from datetime import datetime

from src.mpyl.project import Project, Stages, Stage
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.executor import ExecutionException, ExecutionResult
from src.mpyl.steps.output import Output
from src.mpyl.steps.run import RunResult
from tests import test_resource_path
from tests.test_resources import test_data
from tests.test_resources.test_data import assert_roundtrip, TestStage


def stub_execution_result(stage: Stage, project: ProjectExecution, success: bool):
    return ExecutionResult(
        stage=stage,
        project=project,
        output=Output(success=success, message="Build failed"),
        timestamp=datetime.fromisoformat("2019-01-04T16:41:24+02:00"),
    )


class TestRunResult:
    expected_markdown_files_path = test_resource_path / "run-result-markdown"

    project_a = ProjectExecution.run(test_data.get_project())
    project_b = ProjectExecution.run(
        Project(
            "test", "Test project", "", None, Stages({}), [], None, None, None, None
        )
    )

    run_plan = RunPlan.create(
        all_known_projects=set(),
        plan={
            TestStage.build(): {project_a, project_b},
            TestStage.test(): {project_b},
            TestStage.deploy(): {project_b},
        },
    )

    def test_to_markdown_should_print_successful_results(self):
        run_result = RunResult.with_result(
            stub_execution_result(
                stage=TestStage.deploy(), project=self.project_b, success=True
            ),
        )
        assert_roundtrip(
            self.expected_markdown_files_path / "run_result_with_successful_result.md",
            run_result.to_markdown(),
        )

    def test_to_markdown_should_print_failed_results(self):
        run_result = RunResult.with_result(
            stub_execution_result(
                stage=TestStage.deploy(), project=self.project_b, success=False
            ),
        )
        assert_roundtrip(
            self.expected_markdown_files_path / "run_result_with_failed_result.md",
            run_result.to_markdown(),
        )

    def test_to_markdown_should_print_exceptions(self):
        run_result = RunResult.with_exception(
            ExecutionException(
                project_name=self.project_b.name,
                executor="a step",
                stage=TestStage.deploy().name,
                message="Something went wrong",
            ),
        )
        assert_roundtrip(
            self.expected_markdown_files_path / "run_result_with_exception.md",
            run_result.to_markdown(),
        )

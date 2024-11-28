from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.run import RunResult
from src.mpyl.steps.executor import  ExecutionException
from tests import root_test_path
from tests.test_resources.test_data import assert_roundtrip, TestStage, RUN_PROPERTIES


class TestMarkdownReporting:
    test_resource_path = root_test_path / "reporting" / "formatting" / "test_resources"

    # def test_should_print_results_as_string(self):
    #     run_result = create_test_result()
    #     simple_report = run_result_to_markdown(run_result)
    #     assert_roundtrip(self.test_resource_path / "markdown_run.md", simple_report)

    def test_should_print_exception(self):
        run_result = RunResult.with_xception(
            ExecutionException(
                "sbtProject", "Build SBT", "Build", "Something went wrong"
            )
        )
        simple_report = run_result.to_markdown(run_properties=RUN_PROPERTIES, run_plan=RunPlan.empty())
        assert_roundtrip(
            self.test_resource_path / "markdown_run_with_exception.md", simple_report
        )

    # def test_should_print_results_with_plan_as_string(self):
    #     run_result = create_test_result_with_plan()
    #     append_results(run_result)
    #     simple_report = run_result_to_markdown(run_result)
    #     assert_roundtrip(
    #         self.test_resource_path / "markdown_run_with_plan.md", simple_report
    #     )
    #
    # def test_should_combine_duplicate_urls(self):
    #     run_result = create_test_result()
    #     run_result.append(
    #         ExecutionResult(
    #             stage=TestStage.test(),
    #             project=test_data.get_project(),
    #             output=Output(success=True, message="Tests successful"),
    #             timestamp=datetime.fromisoformat("2019-01-04T16:41:24+02:00"),
    #         )
    #     )
    #     run_result.append(
    #         ExecutionResult(
    #             stage=TestStage.test(),
    #             project=test_data.get_project(),
    #             output=Output(success=True, message="Tests successful"),
    #             timestamp=datetime.fromisoformat("2019-01-04T16:41:24+02:00"),
    #         )
    #     )
    #     simple_report = run_result_to_markdown(run_result)
    #     assert_roundtrip(
    #         self.test_resource_path / "markdown_run_multiple_urls.md", simple_report
    #     )

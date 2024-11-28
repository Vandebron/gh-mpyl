from datetime import datetime

from src.mpyl.project import Stages, Project
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.executor import ExecutionResult
from src.mpyl.steps.output import Output
from src.mpyl.steps.run import RunResult
from tests import root_test_path
from tests.test_resources import test_data
from tests.test_resources.test_data import TestStage, stub_run_properties

test_resource_path = root_test_path / "reporting" / "formatting" / "test_resources"

#
# def create_test_result() -> RunResult:
#     result = RunResult()
#     append_results(result)
#     return result
#
#
# def append_results(result: RunResult) -> None:
#     other_project = __get_other_project()
#     result.append(
#         ExecutionResult(
#             stage=TestStage.build(),
#             project=test_data.get_project(),
#             output=Output(success=False, message="Build failed"),
#             timestamp=datetime.fromisoformat("2019-01-04T16:41:24+02:00"),
#         )
#     )
#     result.append(
#         ExecutionResult(
#             stage=TestStage.build(),
#             project=other_project,
#             output=Output(success=True, message="Build successful"),
#             timestamp=datetime.fromisoformat("2019-01-04T16:41:26+02:00"),
#         )
#     )
#     result.append(
#         ExecutionResult(
#             stage=TestStage.test(),
#             project=other_project,
#             output=Output(success=True, message="Tests successful"),
#             timestamp=datetime.fromisoformat("2019-01-04T16:41:45+02:00"),
#         )
#     )
#     result.append(
#         ExecutionResult(
#             stage=TestStage.deploy(),
#             project=other_project,
#             output=Output(success=True, message="Deploy successful"),
#             timestamp=datetime.fromisoformat("2019-01-04T16:41:45+02:00"),
#         )
#     )
#

# def __get_other_project():
#     stages = Stages({"build": None, "test": None, "deploy": None, "postdeploy": None})
#     return Project("test", "Test project", "", None, stages, [], None, None, None, None)

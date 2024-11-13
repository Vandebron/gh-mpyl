from datetime import datetime

from src.mpyl.project import Stages, Project
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.models import Output
from src.mpyl.steps.run import RunResult
from src.mpyl.steps.steps import StepResult
from tests import root_test_path
from tests.test_resources import test_data
from tests.test_resources.test_data import TestStage, stub_run_properties

test_resource_path = root_test_path / "reporting" / "formatting" / "test_resources"


def create_test_result() -> RunResult:
    result = RunResult(
        run_properties=test_data.RUN_PROPERTIES, run_plan=RunPlan.empty()
    )
    append_results(result)
    return result


def create_test_result_with_plan() -> RunResult:
    build_projects = [test_data.get_project(), __get_other_project()]
    test_projects = [__get_other_project()]
    deploy_projects = [__get_other_project()]
    return RunResult(
        run_properties=stub_run_properties(),
        run_plan=RunPlan.from_plan(
            {
                TestStage.build(): {ProjectExecution.run(p) for p in build_projects},
                TestStage.test(): {ProjectExecution.run(p) for p in test_projects},
                TestStage.deploy(): {ProjectExecution.run(p) for p in deploy_projects},
            }
        ),
    )


def append_results(result: RunResult) -> None:
    other_project = __get_other_project()
    result.append(
        StepResult(
            stage=TestStage.build(),
            project=test_data.get_project(),
            output=Output(success=False, message="Build failed"),
            timestamp=datetime.fromisoformat("2019-01-04T16:41:24+02:00"),
        )
    )
    result.append(
        StepResult(
            stage=TestStage.build(),
            project=other_project,
            output=Output(success=True, message="Build successful"),
            timestamp=datetime.fromisoformat("2019-01-04T16:41:26+02:00"),
        )
    )
    result.append(
        StepResult(
            stage=TestStage.test(),
            project=other_project,
            output=Output(success=True, message="Tests successful"),
            timestamp=datetime.fromisoformat("2019-01-04T16:41:45+02:00"),
        )
    )
    result.append(
        StepResult(
            stage=TestStage.deploy(),
            project=other_project,
            output=Output(success=True, message="Deploy successful"),
            timestamp=datetime.fromisoformat("2019-01-04T16:41:45+02:00"),
        )
    )


def __get_other_project():
    stages = Stages({"build": None, "test": None, "deploy": None, "postdeploy": None})
    return Project("test", "Test project", "", None, stages, [], None, None, None, None)

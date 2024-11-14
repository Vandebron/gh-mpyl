import tempfile
from pathlib import Path

from src.mpyl.run_plan import RunPlan
from src.mpyl.steps import Input
from src.mpyl.steps.deploy.k8s.chart import ChartBuilder, to_service_chart
from src.mpyl.steps.deploy.k8s.helm import write_chart
from tests.test_resources.test_data import (
    TestStage,
    get_project_execution,
    get_minimal_project,
    stub_run_properties,
)


class TestHelm:
    def test_write_chart(self):
        step_input = Input(
            project_execution=get_project_execution(),
            run_properties=stub_run_properties(
                run_plan=RunPlan.from_plan(
                    {TestStage.deploy(): {get_project_execution()}}
                ),
                all_projects={get_minimal_project()},
                deploy_image="some image",
            ),
        )
        with tempfile.TemporaryDirectory() as tempdir:
            builder = ChartBuilder(step_input)
            write_chart(
                to_service_chart(builder),
                Path(tempdir),
                {},
            )

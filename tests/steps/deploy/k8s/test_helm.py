import tempfile
from pathlib import Path

from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.input import Input
from src.mpyl.steps.deploy.k8s.chart import ChartBuilder, to_service_chart
from src.mpyl.steps.deploy.k8s.helm import write_chart, to_chart_metadata
from tests.test_resources import test_data
from tests.test_resources.test_data import (
    get_project_execution,
    stub_run_properties,
)


class TestHelm:
    def test_write_chart(self):
        step_input = Input(
            project_execution=get_project_execution(),
            run_properties=stub_run_properties(deploy_image="some image"),
            run_plan=RunPlan.empty(),
        )
        with tempfile.TemporaryDirectory() as tempdir:
            builder = ChartBuilder(step_input)
            write_chart(
                to_service_chart(builder),
                Path(tempdir),
                to_chart_metadata("chart_name", test_data.RUN_PROPERTIES),
                {},
            )

import tempfile
from pathlib import Path

from src.mpyl.steps import Input
from src.mpyl.steps.deploy.k8s.chart import ChartBuilder, to_service_chart
from src.mpyl.steps.deploy.k8s.helm import write_chart, to_chart_metadata
from tests.steps.test_models import stub_run_properties
from tests.test_resources import test_data
from tests.test_resources.test_data import (
    get_project_execution,
    config_values,
    properties_values,
    get_minimal_project,
)


class TestHelm:
    def test_write_chart(self):
        output = test_data.get_output()
        step_input = Input(
            project_execution=get_project_execution(),
            run_properties=stub_run_properties(
                config=config_values,
                properties=properties_values,
                all_projects={get_minimal_project()},
            ),
            required_artifact=output.produced_artifact,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            builder = ChartBuilder(step_input)
            write_chart(
                to_service_chart(builder),
                Path(tempdir),
                to_chart_metadata("chart_name", test_data.RUN_PROPERTIES),
                {},
            )

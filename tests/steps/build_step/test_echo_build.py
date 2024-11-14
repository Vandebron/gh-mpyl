import logging

from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.build.echo import BuildEcho
from src.mpyl.steps.input import Input
from tests.test_resources import test_data
from tests.test_resources.test_data import get_project_execution


class TestBuildEcho:
    def test_build_echo(self):
        step_input = Input(
            get_project_execution(),
            run_properties=test_data.RUN_PROPERTIES,
            run_plan=RunPlan.empty(),
        )
        echo = BuildEcho(logger=logging.getLogger())
        output = echo.execute(step_input)
        assert output.success
        assert output.message == "Built dockertest"

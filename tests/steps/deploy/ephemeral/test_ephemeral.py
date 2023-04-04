from pathlib import Path

from src.mpyl.project import load_project
from src.mpyl.steps.models import Input
from src.mpyl.utilities.ephemeral import get_env_variables
from tests import root_test_path
from tests.test_resources import test_data


class TestEphemeral:
    resource_path = root_test_path / 'projects' / 'ephemeral' / 'deployment'

    def test_get_env_variables_for_target(self):
        step_input = Input(load_project(self.resource_path, Path('project.yml'), True), test_data.RUN_PROPERTIES, None)
        assert len(step_input.project.deployment.properties.env) == 4

        env_variables = get_env_variables(step_input.project, test_data.RUN_PROPERTIES.target)
        assert len(env_variables) == 4

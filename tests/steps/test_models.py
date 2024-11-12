import os

import pytest
from jsonschema import ValidationError
from ruamel.yaml import YAML  # type: ignore

from src.mpyl.constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
)
from src.mpyl.steps.models import VersioningProperties
from src.mpyl.utilities.pyaml_env import parse_config
from tests import root_test_path
from tests.test_resources.test_data import stub_run_properties

yaml = YAML()


class TestModels:
    resource_path = root_test_path / "test_resources"

    properties_path = resource_path / DEFAULT_RUN_PROPERTIES_FILE_NAME
    run_properties_values = parse_config(properties_path)
    config_values = parse_config(resource_path / DEFAULT_CONFIG_FILE_NAME)

    def test_should_return_error_if_validation_fails(self):
        with pytest.raises(ValidationError) as excinfo:
            stub_run_properties(
                config=self.config_values,
                properties=parse_config(
                    self.resource_path / "run_properties_invalid.yml"
                ),
            )

        assert "'stages' is a required property" in excinfo.value.message

    def test_should_pass_validation(self):
        os.environ["CHANGE_ID"] = "123"
        valid_run_properties_values = parse_config(
            root_test_path / "../run_properties.yml"
        )
        run_properties = stub_run_properties(
            config=self.config_values,
            properties=valid_run_properties_values,
        )

        assert run_properties

    def test_should_return_error_if_pr_number_or_tag_not_set(self):
        properties = VersioningProperties(
            "reviesion_hash",
            "some_branch",
            None,
            None,
        )
        assert properties.validate() == "Either pr_number or tag need to be set"

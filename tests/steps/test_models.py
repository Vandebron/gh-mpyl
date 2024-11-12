import os

import pytest
from jsonschema import ValidationError
from ruamel.yaml import YAML  # type: ignore

from src.mpyl.cli import MpylCliParameters
from src.mpyl.constants import (
    DEFAULT_CONFIG_FILE_NAME,
    DEFAULT_RUN_PROPERTIES_FILE_NAME,
)
from src.mpyl.project import Project
from src.mpyl.steps.models import VersioningProperties, RunProperties
from src.mpyl.utilities.pyaml_env import parse_config
from tests import root_test_path

yaml = YAML()


def stub_run_properties(
    config: dict,
    properties: dict,
    all_projects: set[Project],
    cli_parameters: MpylCliParameters = MpylCliParameters(),
):
    return RunProperties.from_configuration(
        run_properties=properties,
        config=config,
        all_projects=all_projects,
        cli_tag=cli_parameters.tag or properties["build"]["versioning"].get("tag"),
        deploy_image=cli_parameters.deploy_image,
    )


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
                all_projects=set(),
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
            all_projects=set(),
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

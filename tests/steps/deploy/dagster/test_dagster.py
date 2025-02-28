import dataclasses
from pathlib import Path

from ruamel.yaml import YAML

from src.mpyl.project import Target, load_project
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.deploy.k8s.chart import ChartBuilder
from src.mpyl.steps.deploy.k8s.resources.dagster import to_user_code_values
from src.mpyl.steps.input import Input
from src.mpyl.utilities.helm import get_name_suffix
from src.mpyl.utilities.yaml import yaml_to_string
from tests import root_test_path
from tests.test_resources import test_data
from tests.test_resources.test_data import assert_roundtrip

yaml = YAML()


class TestDagster:
    dagster_project_folder = Path(
        root_test_path, "projects", "dagster-user-code", "deployment"
    )
    resource_path = root_test_path / dagster_project_folder
    generated_values_path = (
        root_test_path / "steps" / "deploy" / "dagster" / "dagster-user-deployments"
    )
    config_resource_path = root_test_path / "test_resources"

    run_properties = test_data.stub_run_properties(deploy_image="docker_host/example-dagster-user-code")

    @staticmethod
    def _roundtrip(
        file_name: Path,
        chart: str,
        actual_values: dict,
        overwrite: bool = False,
    ):
        name_chart = file_name / f"{chart}.yaml"
        assert_roundtrip(name_chart, yaml_to_string(actual_values, yaml), overwrite)

    def test_generate_correct_values_yaml_with_service_account_override(self):
        step_input = Input(
            project=load_project(
                self.resource_path / "project.yml", validate_project_yaml=True
            ),
            run_properties=self.run_properties,
            run_plan=RunPlan.empty(),
        )

        values = to_user_code_values(
            builder=ChartBuilder(step_input),
            release_name="example-dagster-user-code-pr-1234",
            name_suffix=get_name_suffix(self.run_properties),
            run_properties=self.run_properties,
            service_account_override="global_service_account",
        )

        self._roundtrip(
            self.generated_values_path, "values_with_global_service_account", values
        )

    def test_generate_correct_values_yaml_with_production_target(self):
        run_properties = dataclasses.replace(
            test_data.stub_run_properties(target=Target.PRODUCTION, deploy_image="docker_host/example-dagster-user-code"),
            versioning=dataclasses.replace(
                self.run_properties.versioning, tag="20230829-1234", pr_number=None
            ),
        )
        step_input = Input(
            project=load_project(
                Path(self.resource_path, "project.yml"), validate_project_yaml=True
            ),
            run_properties=run_properties,
            run_plan=RunPlan.empty(),
        )

        values = to_user_code_values(
            builder=ChartBuilder(step_input),
            release_name="example-dagster-user-code",
            name_suffix=get_name_suffix(run_properties),
            run_properties=run_properties,
            service_account_override="global_service_account",
        )

        self._roundtrip(self.generated_values_path, "values_with_target_prod", values)

    def test_generate_correct_values_yaml_without_service_account_override(self):
        step_input = Input(
            project=load_project(
                Path(self.resource_path, "project.yml"), validate_project_yaml=True
            ),
            run_properties=self.run_properties,
            run_plan=RunPlan.empty(),
        )

        values = to_user_code_values(
            builder=ChartBuilder(step_input),
            release_name="example-dagster-user-code-pr-1234",
            name_suffix=get_name_suffix(self.run_properties),
            run_properties=self.run_properties,
            service_account_override=None,
        )

        self._roundtrip(
            self.generated_values_path, "values_without_global_service_account", values
        )

    def test_generate_with_sealed_secret_as_extra_manifest(self):
        step_input = Input(
            project=load_project(
                self.dagster_project_folder / "project_with_sealed_secret.yml",
                validate_project_yaml=True,
            ),
            run_properties=self.run_properties,
            run_plan=RunPlan.empty(),
        )

        values = to_user_code_values(
            builder=ChartBuilder(step_input),
            release_name="example-dagster-user-code-pr-1234",
            name_suffix=get_name_suffix(self.run_properties),
            run_properties=self.run_properties,
            service_account_override=None,
        )

        self._roundtrip(
            self.generated_values_path, "values_with_extra_manifest", values
        )

"""
Step to deploy a dagster user code repository to k8s
"""

from functools import reduce
from logging import Logger
from pathlib import Path
from typing import List, Tuple, Optional

from . import STAGE_NAME
from .k8s.chart import ChartBuilder
from .k8s.helm import write_chart, template_chart
from .k8s.resources.dagster import to_user_code_values, Constants
from ..input import Input
from ..output import Output
from ..step import Step, Meta
from ..models import RunProperties
from ...utilities.dagster import DagsterConfig
from ...utilities.docker import DockerConfig
from ...utilities.helm import convert_to_helm_release_name, get_name_suffix
from ...utilities.subprocess import custom_check_output


class DagsterBase:
    def combine_outputs(self, results: List[Output]) -> Output:
        return (
            reduce(
                self.__flatten_output_messages,
                results[1:],
                results[0],
            )
            if len(results) > 1
            else results[0]
        )

    @staticmethod
    def __flatten_output_messages(acc: Output, curr: Output) -> Output:
        return Output(
            success=acc.success and curr.success,
            message=f"{acc.message}\n{curr.message}",
        )

    @staticmethod
    def generate_kubernetes_manifests(
        logger: Logger,
        release_name: str,
        namespace: Optional[str],
        chart_version: str,
        values_path: Path,
    ) -> Output:
        output_path = values_path / Path("chart") / Path("templates")
        template_chart_command = template_chart(
            logger=logger,
            release_name=release_name,
            namespace=namespace,
            chart_name="dagster/dagster-user-deployments",
            chart_version=chart_version,
            values_path=values_path / Path("values.yaml"),
            output_path=output_path,
        )

        if template_chart_command.success is not True:
            return template_chart_command

        helm_output_path = output_path / Path("dagster-user-deployments/templates")

        for file in helm_output_path.iterdir():
            file.rename(output_path / file.name)

        helm_output_path.rmdir()

        return template_chart_command

    @staticmethod
    def write_user_code_helm_values(
        step_input: Input,
        properties: RunProperties,
        global_service_account_override: Optional[str],
    ) -> Tuple[str, Path, dict]:
        builder = ChartBuilder(step_input)

        name_suffix = get_name_suffix(properties)
        release_name = convert_to_helm_release_name(
            step_input.project.name, name_suffix
        )

        user_code_deployment = to_user_code_values(
            builder=builder,
            release_name=release_name,
            name_suffix=name_suffix,
            run_properties=properties,
            service_account_override=global_service_account_override,
            docker_config=DockerConfig.from_dict(properties.config),
        )

        values_path = Path(step_input.project.target_path)

        write_chart(
            chart={},
            chart_path=values_path,
            values=user_code_deployment,
        )

        return release_name, values_path, user_code_deployment


class HelmTemplateDagster(Step, DagsterBase):
    """
    This step only creates a dagster user code helm chart manifest but doesn't use helm to deploy the manifest,
    and doesn't write an entry to the dagster server's configmap
    """

    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Dagster Helm Template",
                description="Creates a dagster user code helm chart",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
        )

    # pylint: disable=R0914
    def execute(self, step_input: Input) -> Output:
        """
        Creates the dagster user-code helm chart manifest
        """
        results = []
        properties = step_input.run_properties
        dagster_config: DagsterConfig = DagsterConfig.from_dict(properties.config)
        add_repo_ouput = custom_check_output(
            self._logger,
            f"helm repo add {dagster_config.base_namespace} {Constants.HELM_CHART_REPO}",
        )
        results.append(add_repo_ouput)
        if not add_repo_ouput.success:
            return self.combine_outputs(results)

        release_name, values_path, user_code_deployment = (
            self.write_user_code_helm_values(
                step_input,
                properties,
                dagster_config.global_service_account_override,
            )
        )
        self._logger.debug(f"Written user code Helm values: {user_code_deployment}")
        self._logger.info(f"Helm values written to {values_path}")

        kubernetes_manifests_generation_result = self.generate_kubernetes_manifests(
            self._logger,
            release_name=release_name,
            namespace=step_input.project.namespace(step_input.run_properties.target),
            chart_version=dagster_config.user_code_helm_chart_version,
            values_path=values_path,
        )

        self._logger.info("Kubernetes manifests written")

        results.append(kubernetes_manifests_generation_result)
        return self.combine_outputs(results)

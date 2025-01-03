"""
Step to deploy a dagster user code repository to k8s
"""

from functools import reduce
from logging import Logger
from pathlib import Path
from typing import List, Tuple, Optional

import yaml
from kubernetes import config, client

from . import STAGE_NAME
from .k8s import (
    helm,
    get_config_map,
    rollout_restart_deployment,
    replace_config_map,
    update_config_map_field,
    get_version_of_deployment,
)
from .k8s.chart import ChartBuilder
from .k8s.cluster import get_cluster_config_for_project
from .k8s.helm import write_chart, template_chart
from .k8s.resources.dagster import to_user_code_values, to_grpc_server_entry, Constants
from ..input import Input
from ..output import Output
from ..step import Step, Meta
from ..models import RunProperties
from ...utilities.dagster import DagsterConfig
from ...utilities.docker import DockerConfig
from ...utilities.helm import convert_to_helm_release_name, get_name_suffix


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
        chart_version: str,
        values_path: Path,
    ) -> Output:
        output_path = values_path / Path("chart") / Path("templates")
        template_chart_command = template_chart(
            logger=logger,
            release_name=release_name,
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
            step_input.project_execution.name, name_suffix
        )

        user_code_deployment = to_user_code_values(
            builder=builder,
            release_name=release_name,
            name_suffix=name_suffix,
            run_properties=properties,
            service_account_override=global_service_account_override,
            docker_config=DockerConfig.from_dict(properties.config),
        )

        values_path = Path(step_input.project_execution.project.target_path)

        write_chart(
            chart={},
            chart_path=values_path,
            values=user_code_deployment,
        )

        return release_name, values_path, user_code_deployment

    @staticmethod
    def add_server_to_server_list(
        user_code_deployment: dict, dagster_config: DagsterConfig
    ) -> Output:
        config_map = get_config_map(
            client.CoreV1Api(),
            dagster_config.base_namespace,
            dagster_config.workspace_config_map,
        )
        dagster_workspace = yaml.safe_load(
            config_map.data[dagster_config.workspace_file_key]
        )

        server_names = [
            w["grpc_server"]["location_name"] for w in dagster_workspace["load_from"]
        ]

        # If the server is new (not in existing workspace.yml), we append it
        user_code_name_to_deploy = user_code_deployment["deployments"][0]["name"]
        if user_code_name_to_deploy not in server_names:
            dagster_workspace["load_from"].append(
                to_grpc_server_entry(
                    host=user_code_name_to_deploy,
                    port=user_code_deployment["deployments"][0]["port"],
                    location_name=user_code_name_to_deploy,
                )
            )
            updated_config_map = update_config_map_field(
                config_map=config_map,
                field=dagster_config.workspace_file_key,
                data=dagster_workspace,
            )
            return replace_config_map(
                client.CoreV1Api(),
                dagster_config.base_namespace,
                dagster_config.workspace_config_map,
                updated_config_map,
            )
        return Output(
            success=True,
            message="Server name already exists in list, no addition needed",
        )

    @staticmethod
    def restart_dagster_instances(
        logger, apps_api, dagster_config: DagsterConfig
    ) -> List[Output]:
        # restarting ui and daemon
        rollout_restart_daemon_output = rollout_restart_deployment(
            logger,
            apps_api,
            dagster_config.base_namespace,
            dagster_config.daemon,
        )

        if rollout_restart_daemon_output.success:
            logger.info(rollout_restart_daemon_output.message)
            rollout_restart_server_output = rollout_restart_deployment(
                logger,
                apps_api,
                dagster_config.base_namespace,
                dagster_config.webserver,
            )
            logger.info(rollout_restart_server_output.message)
            return [rollout_restart_daemon_output, rollout_restart_server_output]
        return [rollout_restart_daemon_output]


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

        add_repo_ouput = helm.add_repo(
            self._logger, dagster_config.base_namespace, Constants.HELM_CHART_REPO
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
            release_name,
            dagster_config.user_code_helm_chart_version,
            values_path,
        )

        self._logger.info("Kubernetes manifests written")

        results.append(kubernetes_manifests_generation_result)
        return self.combine_outputs(results)


class TemplateDagster(Step, DagsterBase):
    """
    This step creates a dagster user code helm chart manifest and writes an entry to the dagster server's configmap
    but doesn't use helm to deploy the manifest.
    """

    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Dagster Template",
                description="Creates a dagster user code helm chart and adds an entry to dagster's K8s ConfigMap",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
        )

    # pylint: disable=R0914
    def execute(self, step_input: Input) -> Output:
        """
        Creates the dagster user-code helm chart manifest and adds an server entry to dagster server's ConfigMap
        """
        results = []
        properties = step_input.run_properties
        context = get_cluster_config_for_project(
            step_input.run_properties, step_input.project_execution.project
        ).context
        dagster_config: DagsterConfig = DagsterConfig.from_dict(properties.config)

        config.load_kube_config(context=context)
        apps_api = client.AppsV1Api()

        add_repo_ouput = helm.add_repo(
            self._logger, dagster_config.base_namespace, Constants.HELM_CHART_REPO
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
            release_name,
            dagster_config.user_code_helm_chart_version,
            values_path,
        )

        self._logger.info("Kubernetes manifests written")

        results.append(kubernetes_manifests_generation_result)

        if kubernetes_manifests_generation_result.success:
            add_server_list_output = self.add_server_to_server_list(
                user_code_deployment, dagster_config
            )
            results.append(add_server_list_output)
            if add_server_list_output.success:
                restart_outputs = self.restart_dagster_instances(
                    self._logger, apps_api, dagster_config
                )
                results.extend(restart_outputs)
        return self.combine_outputs(results)


class DeployDagster(Step, DagsterBase):
    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Dagster Deploy",
                description="Deploy a dagster user code repository to k8s",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
        )

    # pylint: disable=R0914
    def execute(self, step_input: Input) -> Output:
        """
        Deploys the docker image produced in the build stage as a Dagster user-code-deployment
        """
        results = []
        properties = step_input.run_properties
        context = get_cluster_config_for_project(
            step_input.run_properties, step_input.project_execution.project
        ).context
        dagster_config: DagsterConfig = DagsterConfig.from_dict(properties.config)

        config.load_kube_config(context=context)
        apps_api = client.AppsV1Api()

        dagster_version = get_version_of_deployment(
            apps_api=apps_api,
            namespace=dagster_config.base_namespace,
            deployment=dagster_config.webserver,
            version_label="app.kubernetes.io/version",
        )
        self._logger.info(f"Dagster Version: {dagster_version}")

        add_repo_ouput = helm.add_repo(
            self._logger, dagster_config.base_namespace, Constants.HELM_CHART_REPO
        )
        results.append(add_repo_ouput)
        if not add_repo_ouput.success:
            return self.combine_outputs(results)

        update_repo_ouput = helm.update_repo(self._logger)
        results.append(update_repo_ouput)
        if not update_repo_ouput.success:
            return self.combine_outputs(results)

        _, values_path, user_code_deployment = self.write_user_code_helm_values(
            step_input,
            properties,
            dagster_config.global_service_account_override,
        )
        self._logger.debug(f"Written user code Helm values: {user_code_deployment}")
        self._logger.info(f"Helm values written to {values_path}")

        helm_install_result = helm.install_chart_with_values(
            logger=self._logger,
            values_path=values_path / Path("values.yaml"),
            release_name=convert_to_helm_release_name(
                step_input.project_execution.name, get_name_suffix(properties)
            ),
            chart_version=dagster_version,
            chart_name=Constants.CHART_NAME,
            namespace=dagster_config.base_namespace,
            kube_context=context,
        )

        results.append(helm_install_result)
        if helm_install_result.success:
            add_to_server_list_output = self.add_server_to_server_list(
                user_code_deployment, dagster_config
            )
            results.append(add_to_server_list_output)

            if add_to_server_list_output.success:
                restart_outputs = self.restart_dagster_instances(
                    self._logger, apps_api, dagster_config
                )
                results.extend(restart_outputs)

        return self.combine_outputs(results)

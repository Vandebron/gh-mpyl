"""Deploys a job to kubernetes, using HELM"""

from logging import Logger

from . import STAGE_NAME
from .k8s import deploy_helm_chart, RenderedHelmChartSpec
from .k8s.chart import ChartBuilder, to_cron_job_chart, to_job_chart
from .. import Step, Meta
from ..models import Input, Output, ArtifactType, input_to_artifact
from ...steps.deploy.k8s import write_helm_chart


class DeployKubernetesJob(Step):
    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Kubernetes Job Deploy",
                description="Deploy a job to k8s",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
            produced_artifact=ArtifactType.NONE,
            required_artifact=ArtifactType.DOCKER_IMAGE,
        )

    def execute(self, step_input: Input) -> Output:
        builder = ChartBuilder(step_input)
        chart = (
            to_cron_job_chart(builder) if builder.is_cron_job else to_job_chart(builder)
        )
        chart_path = write_helm_chart(
            self._logger,
            chart,
            step_input.project_execution.project.target_path,
            step_input.run_properties,
            builder.release_name,
        )

        if step_input.install:
            return deploy_helm_chart(
                self._logger,
                chart_path,
                step_input,
                builder.release_name,
                delete_existing=True,
            )

        return Output(
            success=True,
            message=f"Helm charts written to {chart_path}",
            produced_artifact=input_to_artifact(
                ArtifactType.HELM_CHART,
                step_input,
                spec=RenderedHelmChartSpec(str(chart_path)),
            ),
        )

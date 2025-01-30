"""Deploys a job to kubernetes, using HELM"""

from logging import Logger

from kubernetes.client import V1Job, V1CronJob

from . import STAGE_NAME
from .k8s import generate_helm_charts, CustomResourceDefinition
from .k8s.chart import ChartBuilder, to_cron_job_chart, to_job_chart
from ..input import Input
from ..output import Output
from ..step import Meta, Step


# DEPRECATED: Only here for backward compatibility with old tags
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
        )

    def execute(self, step_input: Input) -> Output:
        builder = ChartBuilder(step_input)
        chart: dict[str, CustomResourceDefinition | V1Job | V1CronJob] = {}

        for deployment in step_input.project_execution.project.deployments:
            chart.update(builder.to_common_chart(deployment))
            chart.update(
                to_cron_job_chart(builder, deployment)
                if deployment.kubernetes.job and deployment.kubernetes.job.cron
                else to_job_chart(builder, deployment)
            )

        return generate_helm_charts(self._logger, chart, step_input)

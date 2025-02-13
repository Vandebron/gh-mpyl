"""Deploys the docker image produced in the build stage to Kubernetes, using HELM. """

from logging import Logger

from kubernetes.client import V1Job, V1CronJob

from . import STAGE_NAME
from .k8s import generate_helm_charts, CustomResourceDefinition
from .k8s.chart import ChartBuilder, to_service_chart, to_cron_job_chart, to_job_chart
from ..input import Input
from ..output import Output
from ..step import Step, Meta


class DeployKubernetes(Step):
    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Kubernetes Deploy",
                description="Deploy to k8s",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
        )

    def execute(self, step_input: Input) -> Output:
        builder = ChartBuilder(step_input)
        chart: dict[str, CustomResourceDefinition | V1Job | V1CronJob] = {}

        for deployment in step_input.project_execution.project.deployments:
            chart.update(builder.to_common_chart(deployment))

            if deployment.kubernetes.job and deployment.kubernetes.job.cron:
                chart.update(to_cron_job_chart(builder, deployment))
            elif deployment.kubernetes.job:
                chart.update(to_job_chart(builder, deployment))
            else:
                chart.update(to_service_chart(builder, deployment))

        return generate_helm_charts(self._logger, chart, step_input)

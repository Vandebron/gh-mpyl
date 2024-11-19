"""Deploys a job to kubernetes, using HELM"""

from logging import Logger

from . import STAGE_NAME
from .k8s import generate_helm_charts
from .k8s.chart import ChartBuilder, to_cron_job_chart, to_job_chart
from ..input import Input
from ..output import Output
from ..step import Meta, Step


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
        chart = (
            to_cron_job_chart(builder) if builder.is_cron_job else to_job_chart(builder)
        )

        return generate_helm_charts(self._logger, chart, step_input)

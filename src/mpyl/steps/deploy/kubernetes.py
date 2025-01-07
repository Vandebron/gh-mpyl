"""Deploys the docker image produced in the build stage to Kubernetes, using HELM. """

from logging import Logger

from . import STAGE_NAME
from .k8s import generate_helm_charts
from .k8s.chart import ChartBuilder, to_service_chart
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
        chart = to_service_chart(builder)

        return generate_helm_charts(self._logger, chart, step_input)

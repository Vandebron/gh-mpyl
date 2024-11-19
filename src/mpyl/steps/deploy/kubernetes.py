"""Deploys the docker image produced in the build stage to Kubernetes, using HELM. """

import re
from logging import Logger

from . import STAGE_NAME
from .k8s import generate_helm_charts
from .k8s.chart import ChartBuilder, to_service_chart
from ..input import Input
from ..output import Output
from ..step import Step, Meta
from ...project import Target


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

    @staticmethod
    def match_to_url(match: str) -> str:
        return "https://" + next(iter(re.findall(r"`(.*)`", match.split(",")[-1])))

    @staticmethod
    def get_endpoint(builder: ChartBuilder) -> str:
        step_input = builder.step_input
        has_specific_routes_configured = (
            builder.deployment.traefik is not None
            and step_input.run_properties.target == Target.PRODUCTION
        )
        hosts = (
            step_input.project_execution.project.deployment.traefik.hosts
            if step_input.project_execution.project.deployment
            and step_input.project_execution.project.deployment.traefik
            else []
        )
        has_swagger = hosts[0].has_swagger if hosts else True
        return (
            "/"
            if has_specific_routes_configured or not has_swagger
            else "/swagger/index.html"
        )

    def execute(self, step_input: Input) -> Output:
        builder = ChartBuilder(step_input)
        chart = to_service_chart(builder)

        return generate_helm_charts(self._logger, chart, step_input)

""" A step to deploy a job to kubernetes. """

from logging import Logger

from .k8s import deploy_helm_chart
from .k8s.chart import ChartBuilder, to_job_chart
from .. import Step, Meta
from ..models import Input, Output, ArtifactType
from ...project import Stage


class DeployKubernetesJob(Step):

    def __init__(self, logger: Logger) -> None:
        super().__init__(logger, Meta(
            name='Kubernetes Job Deploy',
            description='Deploy a job to k8s',
            version='0.0.1',
            stage=Stage.DEPLOY
        ), produced_artifact=ArtifactType.NONE, required_artifact=ArtifactType.DOCKER_IMAGE)

    def execute(self, step_input: Input) -> Output:
        builder = ChartBuilder(step_input)
        return deploy_helm_chart(self._logger, to_job_chart(builder), step_input, builder.release_name)

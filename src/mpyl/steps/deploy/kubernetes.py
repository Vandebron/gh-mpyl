""" Step that deploys the docker image produced in the build stage to Kubernetes, using HELM. """
import re
from logging import Logger
from typing import Optional

from .k8s import deploy_helm_chart, CustomResourceDefinition, cluster_config
from .k8s.chart import ChartBuilder, to_service_chart
from .. import Step, Meta
from ..models import Input, Output, ArtifactType, input_to_artifact
from ...project import Stage, Target
from ...stages.discovery import find_deploy_set
from ...utilities.repo import RepoConfig

DEPLOYED_SERVICE_KEY = 'url'


class DeployKubernetes(Step):

    def __init__(self, logger: Logger) -> None:
        super().__init__(logger, Meta(
            name='Kubernetes Deploy',
            description='Deploy to k8s',
            version='0.0.1',
            stage=Stage.DEPLOY
        ), produced_artifact=ArtifactType.NONE, required_artifact=ArtifactType.DOCKER_IMAGE)

    @staticmethod
    def match_to_url(match: str) -> str:
        return 'https://' + next(iter(re.findall(r'`(.*)`', match.split(',')[-1])))

    @staticmethod
    def try_extract_hostname(chart: dict[str, CustomResourceDefinition]) -> Optional[str]:
        ingress = chart.get('ingress-https-route')
        if ingress:
            routes = ingress.spec.get('routes', {})
            if routes:
                match = routes[0].get('match')
                return DeployKubernetes.match_to_url(match)
        return None

    def execute(self, step_input: Input) -> Output:
        properties = step_input.run_properties
        builder = ChartBuilder(step_input, find_deploy_set(RepoConfig.from_config(properties.config)))
        chart = to_service_chart(builder)

        target_cluster = cluster_config(properties.target, properties)
        deploy_result = deploy_helm_chart(self._logger, chart, step_input, target_cluster, builder.release_name)
        if deploy_result.success:
            hostname = self.try_extract_hostname(chart)
            spec = {}
            if hostname:
                has_specific_routes_configured: bool = bool(builder.deployment.traefik is not None)
                self._logger.info(f"Service {step_input.project.name} reachable at: {hostname}")

                endpoint = '/' if has_specific_routes_configured else '/swagger/index.html'
                spec[DEPLOYED_SERVICE_KEY] = f'{hostname}{endpoint}'
            artifact = input_to_artifact(ArtifactType.DEPLOYED_HELM_APP, step_input, spec=spec)
            if properties.target == Target.PRODUCTION:
                self._logger.info(
                    f"Release to production successful, updating base images in {Target.PULL_REQUEST_BASE} "
                    f"to make sure the Test environment is in sync with production")
                target_cluster = cluster_config(Target.PRODUCTION, properties)
                deploy_to_prod_result = deploy_helm_chart(self._logger, chart, step_input, target_cluster,
                                                          builder.release_name)
                return Output(success=True, message=deploy_result.message + '\n' + deploy_to_prod_result.message,
                              produced_artifact=artifact)

            return Output(success=True, message=deploy_result.message, produced_artifact=artifact)

        return deploy_result

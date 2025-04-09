from src.mpyl.project import (
    KubernetesCommon,
    Project,
    Stages,
    Target,
    TargetProperty,
)
from src.mpyl.project import Deployment
from src.mpyl.steps.deploy.k8s import substitute_namespaces


class TestDeploySetLinkup:

    @staticmethod
    def _stub_project(name: str, namespace: str) -> Project:
        return Project(
            name=name,
            description="",
            path=f"path/to/{name}",
            pipeline=None,
            stages=Stages.from_config({}),
            maintainer=[],
            deployments=[
                Deployment("http", None, None, None)
            ],  # pylint: disable=duplicate-code
            dependencies=[],
            kubernetes=KubernetesCommon(
                project_id=TargetProperty.from_config({}),
                namespace=TargetProperty.from_config({"all": namespace}),
            ),
            _dagster=None,
        )

    project1 = _stub_project("energy-dashboard", "webapps")
    project2 = _stub_project("nginx", "webapps")
    project3 = _stub_project("main-website", "webapps")

    projects_to_deploy = {project1, project2}
    all_projects = {project1, project2, project3}

    def test_should_link_up_deploy_set(self):
        envs = {
            "KEY_1": "http://energy-dashboard-http.{namespace}.svc.cluster.local:4082",
            "KEY_2": "http://main-website-http.{namespace}.svc.cluster.local:4050",
            "KEY_3": "test-http-{PR-NUMBER}.play-backend.zonnecollectief.nl",
            "KEY_4": "abcd",
        }

        expected_envs = {
            "KEY_1": "http://energy-dashboard-http.pr-1234.svc.cluster.local:4082",
            "KEY_2": "http://main-website-http.webapps.svc.cluster.local:4050",
            "KEY_3": "test-http-1234.play-backend.zonnecollectief.nl",
            "KEY_4": "abcd",
        }

        replaced_envs = substitute_namespaces(
            envs, self.all_projects, self.projects_to_deploy, Target.PULL_REQUEST, 1234
        )

        assert replaced_envs == expected_envs

    def test_should_link_up_to_base_services_if_not_pr(self):
        envs = {
            "KEY_1": "http://energy-dashboard-http.{namespace}.svc.cluster.local:4082",
            "KEY_2": "http://main-website-http.{namespace}.svc.cluster.local:4050",
            "KEY_3": "abcd",
        }
        expected_envs = {
            "KEY_1": "http://energy-dashboard-http.webapps.svc.cluster.local:4082",
            "KEY_2": "http://main-website-http.webapps.svc.cluster.local:4050",
            "KEY_3": "abcd",
        }
        replaced_envs = substitute_namespaces(
            envs, self.all_projects, self.projects_to_deploy, Target.PRODUCTION, None
        )

        assert replaced_envs == expected_envs

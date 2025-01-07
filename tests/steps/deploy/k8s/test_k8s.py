import dataclasses
from pathlib import Path
from typing import cast

import pytest
from kubernetes.client import V1Probe, V1ObjectMeta, V1DeploymentSpec
from pyaml_env import parse_config

from src.mpyl.constants import DEFAULT_CONFIG_FILE_NAME
from src.mpyl.project import Target, Project
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.deploy.k8s.chart import (
    ChartBuilder,
    to_service_chart,
    to_job_chart,
    to_cron_job_chart,
)
from src.mpyl.steps.deploy.k8s.resources import to_yaml, CustomResourceDefinition
from src.mpyl.steps.deploy.k8s.resources.traefik import V1AlphaIngressRoute
from src.mpyl.steps.deploy.kubernetes import DeployKubernetes
from src.mpyl.steps.input import Input
from src.mpyl.utilities.docker import DockerConfig
from tests import root_test_path
from tests.test_resources import test_data
from tests.test_resources.test_data import (
    assert_roundtrip,
    get_project,
    get_deployment_strategy_project,
    get_job_project,
    get_cron_job_project,
    get_minimal_project,
    stub_run_properties,
    RUN_PROPERTIES,
    TestStage,
    get_project_traefik,
)


class TestKubernetesChart:
    resource_path = root_test_path / "test_resources"
    k8s_resources_path = root_test_path / "steps" / "deploy" / "k8s"
    template_path = k8s_resources_path / "chart" / "templates"

    config = parse_config(resource_path / DEFAULT_CONFIG_FILE_NAME)
    liveness_probe_defaults = config["project"]["deployment"]["kubernetes"][
        "livenessProbe"
    ]

    @staticmethod
    def _roundtrip(
        file_name: Path,
        chart: str,
        resources: dict[str, CustomResourceDefinition],
        overwrite: bool = False,
    ):
        name_chart = file_name / f"{chart}.yaml"
        resource = resources[chart]
        assert_roundtrip(name_chart, to_yaml(resource), overwrite)

    @staticmethod
    def _get_builder(project: Project, run_properties=None):
        project_execution = ProjectExecution.run(project)

        if not run_properties:
            run_properties = stub_run_properties(deploy_image="registry/image:123")

        return ChartBuilder(
            step_input=Input(
                project_execution=project_execution,
                run_properties=run_properties,
                run_plan=RunPlan.create(
                    all_known_projects={project, get_minimal_project()},
                    plan={TestStage.deploy(): {project_execution}},
                ),
            ),
        )

    def test_probe_values_should_be_customizable(self):
        project = test_data.get_project()
        probe = project.kubernetes.liveness_probe

        custom_success_threshold = 0
        custom_failure_threshold = 99

        assert probe is not None
        assert probe.values["successThreshold"] == custom_success_threshold
        assert probe.values["failureThreshold"] == custom_failure_threshold

        v1_probe: V1Probe = ChartBuilder._to_probe(
            probe, self.liveness_probe_defaults, target=Target.PULL_REQUEST
        )
        assert v1_probe.success_threshold == custom_success_threshold
        assert v1_probe.failure_threshold == custom_failure_threshold

        assert v1_probe.period_seconds == self.liveness_probe_defaults["periodSeconds"]
        assert v1_probe.grpc.port == 123

    def test_probe_deserialization_failure_should_throw(self):
        project = test_data.get_project()
        probe = project.kubernetes.liveness_probe

        assert probe is not None
        probe.values["httpGet"] = "incorrect"

        with pytest.raises(ValueError) as exc_info:
            ChartBuilder._to_probe(
                probe, self.liveness_probe_defaults, target=Target.PULL_REQUEST
            )
        assert "Invalid value for `port`, must not be `None`" in str(exc_info.value)

    def test_load_docker_config(self):
        yaml_values = parse_config(self.resource_path / DEFAULT_CONFIG_FILE_NAME)
        docker_config = DockerConfig.from_dict(yaml_values)
        assert docker_config.registries[0].host_name == "docker_host"

    def test_should_validate_against_crd_schema(self):
        project = test_data.get_project()
        builder = self._get_builder(project)
        wrappers = builder.create_host_wrappers()
        route = V1AlphaIngressRoute.from_hosts(
            metadata=V1ObjectMeta(),
            host=wrappers[0],
            target=Target.PRODUCTION,
            pr_number=1234,
            namespace="pr-1234",
            cluster_env="test",
            middlewares_override=[],
            entrypoints_override=[],
            http_middleware="http",
            default_tls="default",
        )
        route.spec["tls"] = {"secretName": 1234}

        with pytest.raises(ValueError) as exc_info:
            to_yaml(route)
        assert "Schema validation failed with 1234 is not of type 'string'" in str(
            exc_info.value
        )

    def test_should_not_extend_whitelists_if_none_defined_for_target(self):
        project = test_data.get_project()
        builder = self._get_builder(project)
        wrappers = builder.create_host_wrappers()
        assert test_data.RUN_PROPERTIES.target == Target.PULL_REQUEST
        assert "Test" not in wrappers[0].white_lists

    @pytest.mark.parametrize(
        "template",
        [
            "deployment",
            "service",
            "service-account",
            "sealed-secrets",
            "dockertest-ingress-0-https",
            "dockertest-ingress-0-http",
            "dockertest-ingress-1-https",
            "dockertest-ingress-1-http",
            "dockertest-ingress-intracloud-https-0",
            "dockertest-ingress-0-whitelist",
            "dockertest-ingress-1-whitelist",
            "ingress-routes",
            "middleware-strip-prefix",
            "middleware-strip-prefix-dockertest",
            "prometheus-rule",
            "service-monitor",
            "role",
            "rolebinding",
        ],
    )
    def test_service_chart_roundtrip(self, template):
        builder = self._get_builder(get_project_traefik())
        chart = to_service_chart(builder)
        self._roundtrip(self.template_path / "service", template, chart)
        assert chart.keys() == {
            "service-account",
            "sealed-secrets",
            "deployment",
            "service",
            "dockertest-ingress-0-https",
            "dockertest-ingress-0-http",
            "dockertest-ingress-1-https",
            "dockertest-ingress-1-http",
            "dockertest-ingress-intracloud-https-0",
            "dockertest-ingress-0-whitelist",
            "dockertest-ingress-1-whitelist",
            "ingress-routes",
            "middleware-strip-prefix",
            "middleware-strip-prefix-dockertest",
            "prometheus-rule",
            "service-monitor",
            "role",
            "rolebinding",
        }

    def test_ingress_routes_placeholder_replacement(self):
        ingress_routes = self._get_builder(get_project_traefik()).to_ingress()
        assert (
            ingress_routes.spec["routes"][0]["match"]
            == "placeholder-test-pr-1234-1234-test"
        )
        assert (
            ingress_routes.spec["routes"][0]["middlewares"][0]["name"]
            == "strip-prefix-dockertest"
        )

    def test_middlewares_placeholder_replacement(self):
        middlewares = self._get_builder(get_project_traefik()).to_middlewares()
        assert "middleware-strip-prefix-dockertest" in middlewares
        assert middlewares["middleware-strip-prefix-dockertest"].spec["stripPrefix"][
            "prefixes"
        ] == ["/service2/test/pr-1234/1234"]

    def test_deployment_strategy_roundtrip(self):
        project = get_deployment_strategy_project()
        builder = self._get_builder(project)
        chart = to_service_chart(builder)
        self._roundtrip(self.template_path / "deployment", "deployment", chart)

    def test_default_ingress(self):
        project = get_minimal_project()
        builder = self._get_builder(project)
        chart = to_service_chart(builder)
        self._roundtrip(
            self.template_path / "ingress", "minimalService-ingress-0-https", chart
        )

    def test_production_ingress(self):
        project = get_minimal_project()
        run_properties_prod = stub_run_properties(deploy_image="registry/image:123")
        run_properties_prod = dataclasses.replace(
            run_properties_prod,
            target=Target.PRODUCTION,
            versioning=dataclasses.replace(
                RUN_PROPERTIES.versioning, tag="20230829-1234", pr_number=None
            ),
        )

        builder = self._get_builder(project, run_properties_prod)
        chart = to_service_chart(builder)
        self._roundtrip(
            self.template_path / "ingress-prod", "minimalService-ingress-0-https", chart
        )

    def test_route_parsing(self):
        assert (
            DeployKubernetes.match_to_url("Host(`dockertest-1234.test-backend.nl`)")
            == "https://dockertest-1234.test-backend.nl"
        )
        assert (
            DeployKubernetes.match_to_url(
                "HostRegexp(`{subdomain:(www|blog){1}}.test.host.nl`, `test.host.nl`)"
            )
            == "https://test.host.nl"
        )

    def test_is_cron_job(self):
        cron_builder = self._get_builder(get_cron_job_project())
        assert cron_builder.is_cron_job is True
        builder = self._get_builder(get_job_project())
        assert builder.is_cron_job is False

    @pytest.mark.parametrize(
        "template", ["job", "service-account", "sealed-secrets", "prometheus-rule"]
    )
    def test_job_chart_roundtrip(self, template):
        builder = self._get_builder(get_job_project())
        chart = to_job_chart(builder)
        self._roundtrip(self.template_path / "job", template, chart)

    @pytest.mark.parametrize(
        "template", ["cronjob", "service-account", "sealed-secrets", "prometheus-rule"]
    )
    def test_cron_job_chart_roundtrip(self, template):
        builder = self._get_builder(get_cron_job_project())
        chart = to_cron_job_chart(builder)
        self._roundtrip(self.template_path / "cronjob", template, chart)

    def test_get_endpoint(self):
        project_with_swagger = get_project()
        builder_with_swagger = self._get_builder(project_with_swagger)

        endpoint_with_swagger = DeployKubernetes.get_endpoint(builder_with_swagger)
        assert endpoint_with_swagger == "/swagger/index.html"

        project_without_swagger = test_data.get_project_without_swagger()
        builder_without_swagger = self._get_builder(project_without_swagger)

        endpoint_without_swagger = DeployKubernetes.get_endpoint(
            builder_without_swagger
        )
        assert endpoint_without_swagger == "/"

    def test_passed_deploy_image(self):
        builder = self._get_builder(
            get_minimal_project(),
            stub_run_properties(deploy_image="test-image:latest"),
        )
        assert builder._get_image() == "test-image:latest"
        chart = to_service_chart(builder)
        assert (
            cast(V1DeploymentSpec, chart["deployment"].spec)
            .template.spec.containers[0]
            .image
            == "test-image:latest"
        )

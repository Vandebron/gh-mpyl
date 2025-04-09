from pathlib import Path
from typing import cast, Union

import pytest
from kubernetes.client import V1Probe, V1ObjectMeta, V1DeploymentSpec, V1Job, V1CronJob
from pyaml_env import parse_config

from src.mpyl.constants import DEFAULT_CONFIG_FILE_NAME
from src.mpyl.project import Target, Project
from src.mpyl.run_plan import RunPlan
from src.mpyl.steps.deploy.k8s.chart import (
    ChartBuilder,
    to_service_chart,
    to_job_chart,
    to_cron_job_chart,
)
from src.mpyl.steps.deploy.k8s.resources import to_yaml, CustomResourceDefinition
from src.mpyl.steps.deploy.k8s.resources.traefik import V1AlphaIngressRoute
from src.mpyl.steps.input import Input
from tests import root_test_path
from tests.test_resources import test_data
from tests.test_resources.test_data import (
    assert_roundtrip,
    get_job_project,
    get_cron_job_project,
    get_minimal_project,
    stub_run_properties,
    TestStage,
    get_project_traefik,
    get_deployments_strategy_project,
    get_job_deployments_project,
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
        filename: str,
        resources: dict[str, Union[CustomResourceDefinition, V1Job, V1CronJob]],
        overwrite: bool = False,
    ):
        name_chart = file_name / f"{filename}.yaml"
        resource = resources[filename]
        assert_roundtrip(name_chart, to_yaml(resource), overwrite)

    @staticmethod
    def _get_builder(project: Project, run_properties=None):
        if not run_properties:
            run_properties = stub_run_properties(deploy_image="registry/image:123")

        return ChartBuilder(
            step_input=Input(
                project=project,
                run_properties=run_properties,
                run_plan=RunPlan.create(
                    all_known_projects={project, get_minimal_project()},
                    plan={TestStage.deploy(): {project}},
                ),
            ),
        )

    def test_probe_values_should_be_customizable(self):
        project = test_data.get_project()
        probe = project.deployments[0].kubernetes.liveness_probe

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
        probe = project.deployments[0].kubernetes.liveness_probe

        assert probe is not None
        probe.values["httpGet"] = "incorrect"

        with pytest.raises(ValueError) as exc_info:
            ChartBuilder._to_probe(
                probe, self.liveness_probe_defaults, target=Target.PULL_REQUEST
            )
        assert "Invalid value for `port`, must not be `None`" in str(exc_info.value)

    def test_should_validate_against_crd_schema(self):
        project = test_data.get_project()
        builder = self._get_builder(project)
        wrappers = builder.create_host_wrappers(builder.project.deployments[0])
        route = V1AlphaIngressRoute.from_hosts(
            metadata=V1ObjectMeta(),
            host=wrappers[0],
            target=Target.PRODUCTION,
            pr_number=1234,
            release_name="dockertest",
            namespace="pr-1234",
            default_middlewares=[],
            default_entrypoints=[],
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
        wrappers = builder.create_host_wrappers(project.deployments[0])
        assert test_data.RUN_PROPERTIES.target == Target.PULL_REQUEST
        assert "Test" not in wrappers[0].white_lists

    @pytest.mark.parametrize(
        "template",
        [
            "deployment-dockertest",
            "service-dockertest",
            "service-account",
            "service",
            "sealed-secrets-dockertest",
            "ingress-dockertest-https-0",
            "ingress-dockertest-http-0",
            "ingress-dockertest-https-1",
            "ingress-dockertest-http-1",
            "ingress-dockertest-ingress-intracloud-https-0",
            "middleware-whitelist-0-dockertest",
            "middleware-whitelist-1-dockertest",
            "ingress-routes-dockertest",
            "middleware-strip-prefix-dockertest",
            "prometheus-rule-dockertest",
            "service-monitor-dockertest",
        ],
    )
    def test_service_chart_roundtrip(self, template):
        traefik_project = get_project_traefik()
        builder = self._get_builder(traefik_project)
        chart = builder.to_common_chart(
            traefik_project.deployments[0]
        ) | to_service_chart(builder, builder.project.deployments[0])
        self._roundtrip(
            self.template_path / "service", filename=template, resources=chart
        )
        assert set(chart.keys()) == {
            "service-account",
            "sealed-secrets-dockertest",
            "deployment-dockertest",
            "service",
            "service-dockertest",
            "ingress-dockertest-https-0",
            "ingress-dockertest-http-0",
            "ingress-dockertest-https-1",
            "ingress-dockertest-http-1",
            "ingress-dockertest-ingress-intracloud-https-0",
            "middleware-whitelist-0-dockertest",
            "middleware-whitelist-1-dockertest",
            "ingress-routes-dockertest",
            "middleware-strip-prefix-dockertest",
            "prometheus-rule-dockertest",
            "service-monitor-dockertest",
        }

    def test_ingress_routes_placeholder_replacement(self):
        builder = self._get_builder(get_project_traefik())
        ingress_routes = builder.to_ingress(builder.project.deployments[0])
        assert (
            ingress_routes.spec["routes"][0]["match"]
            == "placeholder-test-pr-1234-1234-test"
        )
        assert (
            ingress_routes.spec["routes"][0]["middlewares"][0]["name"] == "strip-prefix"
        )

    def test_middlewares_placeholder_replacement(self):
        traefik_project = get_project_traefik()
        middlewares = self._get_builder(get_project_traefik()).to_middlewares(
            traefik_project.deployments[0]
        )
        assert "middleware-strip-prefix-dockertest" in middlewares
        assert middlewares["middleware-strip-prefix-dockertest"].spec["stripPrefix"][
            "prefixes"
        ] == ["/service2/test/pr-1234/1234"]

    def test_deployments_strategy_roundtrip(self):
        project = get_deployments_strategy_project()
        builder = self._get_builder(project)
        chart1 = to_service_chart(builder, project.deployments[0])
        chart2 = to_service_chart(builder, project.deployments[1])
        self._roundtrip(
            self.template_path / "deployment",
            "deployment-testdeploymentsstrategyparameters1",
            chart1,
        )
        self._roundtrip(
            self.template_path / "deployment",
            "deployment-testdeploymentsstrategyparameters2",
            chart2,
        )

    def test_multiple_deployments(self):
        project = get_job_deployments_project()
        builder = self._get_builder(project)
        job_chart = to_job_chart(builder, project.deployments[0])
        cron_job_chart = to_cron_job_chart(builder, project.deployments[1])
        self._roundtrip(
            self.template_path / "deployments", "job-jobdeployment", job_chart
        )
        self._roundtrip(
            self.template_path / "deployments",
            "cronjob-cronjobdeployment",
            cron_job_chart,
        )

    def test_default_ingress(self):
        project = get_minimal_project()
        builder = self._get_builder(project)
        chart = to_service_chart(builder, project.deployments[0])
        self._roundtrip(self.template_path / "ingress", "ingress-http-https-0", chart)

    def test_production_ingress(self):
        project = get_minimal_project()
        run_properties_prod = stub_run_properties(
            target=Target.PRODUCTION,
            deploy_image="registry/image:version",
            tag="20230829-1234",
        )
        builder = self._get_builder(project, run_properties_prod)
        chart = to_service_chart(builder, project.deployments[0])
        self._roundtrip(
            self.template_path / "ingress-prod", "ingress-http-https-0", chart
        )

    @pytest.mark.parametrize(
        "template",
        ["job-job", "service-account", "sealed-secrets-job", "prometheus-rule-job"],
    )
    def test_job_chart_roundtrip(self, template):
        job_project = get_job_project()
        builder = self._get_builder(job_project)
        chart = builder.to_common_chart(job_project.deployments[0]) | to_job_chart(
            builder, job_project.deployments[0]
        )
        self._roundtrip(self.template_path / "job", template, chart)

    @pytest.mark.parametrize(
        "template",
        [
            "cronjob-cronjob",
            "service-account",
            "sealed-secrets-cronjob",
            "prometheus-rule-cronjob",
        ],
    )
    def test_cron_job_chart_roundtrip(self, template):
        cron_job_project = get_cron_job_project()
        builder = self._get_builder(cron_job_project)
        chart = builder.to_common_chart(
            cron_job_project.deployments[0]
        ) | to_cron_job_chart(builder, cron_job_project.deployments[0])
        self._roundtrip(self.template_path / "cronjob", template, chart)

    def test_passed_deploy_image(self):
        builder = self._get_builder(
            get_minimal_project(),
            stub_run_properties(deploy_image="test-image:latest"),
        )
        assert builder._get_image() == "test-image:latest"
        chart = to_service_chart(builder, builder.project.deployments[0])
        assert (
            cast(V1DeploymentSpec, chart["deployment-http"].spec)
            .template.spec.containers[0]
            .image
            == "test-image:latest"
        )

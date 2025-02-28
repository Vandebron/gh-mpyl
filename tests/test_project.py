import os
from pathlib import Path

import pytest
from jsonschema import ValidationError

from src.mpyl.project import load_project, Target
from tests import root_test_path
from tests.test_resources.test_data import TestStage


class TestMpylSchema:
    resource_path = root_test_path / "test_resources" / "test_projects"
    project = load_project(
        Path(resource_path, "default", "test_project.yml"),
        validate_project_yaml=True,
    )

    def test_schema_load(self):
        os.environ["CHANGE_ID"] = "123"

        assert self.project.name == "dockertest"
        assert self.project.maintainer, ["Marketplace", "Energy Trading"]
        assert self.project.deployments is not None
        assert self.project.deployments[0].properties is not None
        envs = self.project.deployments[0].properties.env

        simple_env = [x for x in envs if x.key == "SOME_ENV"].pop()
        assert simple_env.key == "SOME_ENV"
        assert simple_env.get_value(Target.ACCEPTANCE) == "Acceptance"
        assert simple_env.get_value(Target.PRODUCTION) == "Production"

        secret_env = [
            x
            for x in self.project.deployments[0].properties.sealed_secrets
            if x.key == "SOME_SEALED_SECRET_ENV"
        ].pop()
        assert secret_env.get_value(Target.PULL_REQUEST).startswith(
            "AgCA5/qvMMp"
        ), "should start with"

        assert self.project.dependencies is not None
        assert self.project.dependencies.for_stage(TestStage.build().name) == [
            "test/docker/"
        ]
        assert self.project.dependencies.for_stage(TestStage.test().name) == [
            "test2/docker/"
        ]
        assert self.project.dependencies.for_stage(TestStage.deploy().name) is None
        assert self.project.dependencies.for_stage(TestStage.post_deploy().name) == [
            "specs/*.js"
        ]

        assert self.project.deployments[0].kubernetes is not None
        assert self.project.deployments[0].kubernetes.port_mappings == {8080: 80}
        assert self.project.deployments[0].kubernetes.liveness_probe is not None
        assert (
            self.project.deployments[0].kubernetes.liveness_probe.path.get_value(
                Target.ACCEPTANCE
            )
            == "/health"
        )
        assert self.project.deployments[0].kubernetes.metrics is not None
        assert self.project.deployments[0].kubernetes.metrics.enabled

        assert self.project.deployments[0].traefik is not None
        host = self.project.deployments[0].traefik.hosts[0]
        assert host.host.get_value(Target.TEST) == "Host(`payments.test.nl`)"
        assert (
            host.host.get_value(Target.PULL_REQUEST)
            == "Host(`payments-{PR-NUMBER}.test.nl`)"
        )
        assert host.tls
        assert host.tls.get_value(Target.TEST) == "le-custom-prod-wildcard-cert"

        assert (
            self.project.deployments[0].properties.env[2].all
            == "minimalService.{namespace}.svc.cluster.local"
        )

    def test_schema_load_validation(self):
        with pytest.raises(ValidationError) as exc:
            load_project(
                self.resource_path / "test_project_invalid.yml",
                validate_project_yaml=True,
            )
        assert exc.value.message == "'maintainer' is a required property"

    def test_target_by_value(self):
        target = Target(Target.PULL_REQUEST)
        assert target == Target.PULL_REQUEST

    def test_project_path(self):
        assert self.project.path == f"{self.resource_path}/default/test_project.yml"

    def test_project_root_path(self):
        assert self.project.root_path == self.resource_path

    def test_project_deployment_path(self):
        assert self.project.deployment_path == self.resource_path / "default"

    def test_project_target_path(self):
        assert self.project.target_path == self.resource_path / "default" / ".mpyl"

    def test_project_test_report_path(self):
        assert (
            self.project.test_report_path
            == self.resource_path / "target" / "test-reports"
        )

    def test_project_yaml_file_name(self):
        assert self.project.project_yaml_file_name() == "project.yml"

    def test_project_overrides_yaml_file_pattern(self):
        assert (
            self.project.project_overrides_yaml_file_pattern()
            == "project-override-*.yml"
        )

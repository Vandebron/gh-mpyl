""" Step that tests the docker image from the target `tester` in Dockerfile-mpl.


## 🧪 Testing inside a container

When unit tests are run within a docker container the test results need to be written to a folder inside it.
This means that the test step _within the docker container_ should not return a system error.
Otherwise, building of the container would stop and the test results would not be committed to a layer.

The test results need to be written to a folder named `$WORKDIR/target/test-reports/` for
`TestDocker.extract_test_results` to find and extract them.


"""
from logging import Logger

from python_on_whales import Container

from .after_test import IntegrationTestAfter
from .before_test import IntegrationTestBefore
from .. import Step, Meta
from ..models import Input, Output, ArtifactType, input_to_artifact, Artifact
from ...project import Stage, Project
from ...utilities.docker import (
    DockerConfig,
    build,
    docker_image_tag,
    docker_file_path,
    docker_copy,
    remove_container,
    create_container,
)
from ...utilities.junit import (
    to_test_suites,
    sum_suites,
    TEST_OUTPUT_PATH_KEY,
    TEST_RESULTS_URL_KEY,
)


class TestDocker(Step):
    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger=logger,
            meta=Meta(
                name="Docker Test",
                description="Test docker image",
                version="0.0.1",
                stage=Stage.TEST,
            ),
            produced_artifact=ArtifactType.JUNIT_TESTS,
            required_artifact=ArtifactType.NONE,
            before=IntegrationTestBefore(logger),
            after=IntegrationTestAfter(logger),
        )

    def execute(self, step_input: Input) -> Output:
        docker_config = DockerConfig.from_dict(step_input.run_properties.config)
        test_target = docker_config.test_target
        if not test_target:
            raise ValueError("docker.testTarget must be specified")

        tag = docker_image_tag(step_input) + "-test"
        project = step_input.project
        dockerfile = docker_file_path(project=project, docker_config=docker_config)
        success = build(
            logger=self._logger,
            root_path=docker_config.root_folder,
            file_path=dockerfile,
            image_tag=tag,
            target=test_target,
        )
        container = create_container(self._logger, tag)

        if success:
            artifact = self.extract_test_results(
                self._logger, project, container, step_input
            )

            suite = to_test_suites(artifact)
            summary = sum_suites(suite)

            output = Output(
                success=summary.is_success,
                message=f"Tests results produced for {project.name} ({summary})",
                produced_artifact=artifact,
            )
        else:
            output = Output(
                success=False,
                message=f"Tests failed to run for {project.name}. No test results have been recorded.",
                produced_artifact=None,
            )

        remove_container(self._logger, container)

        return output

    @staticmethod
    def extract_test_results(
        logger: Logger, project: Project, container: Container, step_input: Input
    ) -> Artifact:
        path_in_container = f"{project.test_report_path}/."
        docker_copy(
            logger=logger,
            container_path=path_in_container,
            dst_path=project.test_report_path,
            container=container,
        )

        return input_to_artifact(
            artifact_type=ArtifactType.JUNIT_TESTS,
            step_input=step_input,
            spec={
                TEST_OUTPUT_PATH_KEY: project.test_report_path,
                TEST_RESULTS_URL_KEY: step_input.run_properties.details.tests_url,
            },
        )

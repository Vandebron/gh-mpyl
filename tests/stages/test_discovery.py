import contextlib
import logging
import os
import shutil
from pathlib import Path

from src.mpyl.constants import RUN_ARTIFACTS_FOLDER
from src.mpyl.plan.discovery import (
    find_projects_to_execute,
    is_project_cached_for_stage,
    is_file_a_dependency,
)
from src.mpyl.project import load_project
from src.mpyl.steps.output import Output
from src.mpyl.utilities.repo import Changeset
from tests import test_resource_path
from tests.projects.find import load_projects
from tests.test_resources.test_data import TestStage

HASHED_CHANGES_OF_JOB = "b88fd790d1180a22de5cd70b99040f96a4485c4692d9b3179deb78dfc95b4ecb"  # this has to be updated
# if the test project.yml changes


@contextlib.contextmanager
def _cache_build_job():
    path = f"tests/projects/job/deployment/{RUN_ARTIFACTS_FOLDER}"

    if not os.path.isdir(path):
        os.makedirs(path)

    try:
        Output(success=True, message="a test output", hash=HASHED_CHANGES_OF_JOB).write(
            target_path=Path(path),
            stage=TestStage.build().name,
        )
        yield path
    finally:
        shutil.rmtree(path)


class TestDiscovery:
    logger = logging.getLogger(__name__)
    project_paths = [
        "tests/projects/job/deployment/project.yml",
        "tests/projects/service/deployment/project.yml",
        "tests/projects/sbt-service/deployment/project.yml",
    ]
    projects = load_projects(list(map(Path, project_paths)))

    def _helper_find_projects_to_execute(
        self,
        files_touched: dict[str, str],
        stage_name: str = TestStage.build().name,
    ):
        return find_projects_to_execute(
            logger=self.logger,
            all_projects=self.projects,
            stage=stage_name,
            changeset=Changeset(
                sha="a git SHA",
                _files_touched=files_touched,
            ),
        )

    def test_changeset_from_files(self):
        changeset = Changeset.from_files(
            self.logger,
            sha="a git commit",
            changed_files_path=Path("tests/test_resources/changed-files/"),
        )
        assert len(changeset.files_touched()) == 12

        # renamed_files is empty
        # ignored_files should be ignored
        for operation, status in {
            "added": "A",
            "copied": "C",
            "deleted": "D",
            "modified": "M",
        }.items():
            assert f"{operation}/file with spaces.py" in changeset.files_touched(
                {status}
            )
            assert f"{operation}/file,with,commas.py" in changeset.files_touched(
                {status}
            )
            assert f"{operation}/file|with|pipes.py" in changeset.files_touched(
                {status}
            )

    def test_find_projects_to_execute_for_each_stage(self):
        changeset = Changeset(
            sha="revision",
            _files_touched={
                "tests/projects/service/file.py": "A",
                "tests/some_file.txt": "A",
            },
        )
        projects = load_projects()
        assert (
            len(
                find_projects_to_execute(
                    self.logger,
                    projects,
                    TestStage.build().name,
                    changeset,
                )
            )
            == 1
        )
        assert (
            len(
                find_projects_to_execute(
                    self.logger,
                    projects,
                    TestStage.test().name,
                    changeset,
                )
            )
            == 0
        )
        assert (
            len(
                find_projects_to_execute(
                    self.logger,
                    projects,
                    TestStage.deploy().name,
                    changeset,
                )
            )
            == 1
        )
        assert (
            len(
                find_projects_to_execute(
                    self.logger,
                    projects,
                    TestStage.post_deploy().name,
                    changeset,
                )
            )
            == 0
        )

    def test_stage_with_files_changed(self):
        project_executions = self._helper_find_projects_to_execute(
            files_touched={
                "tests/projects/job/deployment/project.yml": "M",
            },
        )
        assert len(project_executions) == 1
        job_execution = next(p for p in project_executions if p.project.name == "job")
        assert not job_execution.cached
        assert job_execution.hashed_changes == HASHED_CHANGES_OF_JOB

    def test_stage_with_files_changed_and_existing_cache(self):
        with _cache_build_job():
            project_executions = self._helper_find_projects_to_execute(
                files_touched={
                    "tests/projects/job/deployment/project.yml": "M",
                },
            )
            assert len(project_executions) == 1
            job_execution = next(
                p for p in project_executions if p.project.name == "job"
            )
            assert job_execution.cached
            assert job_execution.hashed_changes == HASHED_CHANGES_OF_JOB

    def test_stage_with_files_changed_but_filtered(self):
        with _cache_build_job():
            project_executions = self._helper_find_projects_to_execute(
                files_touched={
                    "tests/projects/job/deployment/project.yml": "D",
                },
            )
            assert len(project_executions) == 1
            job_execution = next(
                p for p in project_executions if p.project.name == "job"
            )
            assert not job_execution.cached
            # all modified files are filtered out, no hash in current run
            assert not job_execution.hashed_changes

    def test_stage_with_build_dependency_changed(self):
        with _cache_build_job():
            project_executions = self._helper_find_projects_to_execute(
                files_touched={
                    "tests/projects/sbt-service/src/main/scala/vandebron/mpyl/Main.scala": "M"
                },
            )

            # both job and sbt-service should be executed
            assert len(project_executions) == 2

            job_execution = next(
                p for p in project_executions if p.project.name == "job"
            )

            # a build dependency changed, so this project should always run
            assert not job_execution.cached
            # no files changes in the current run
            assert not job_execution.hashed_changes

    def test_stage_with_test_dependency_changed(self):
        project_executions = self._helper_find_projects_to_execute(
            files_touched={"tests/projects/service/file.py": "M"},
        )

        # job should not be executed because it wasn't modified and service is only a test dependency
        assert len(project_executions) == 1
        assert not {p for p in project_executions if p.project.name == "job"}

    def test_stage_with_files_changed_and_dependency_changed(self):
        with _cache_build_job():
            project_executions = self._helper_find_projects_to_execute(
                files_touched={
                    "tests/projects/job/deployment/project.yml": "M",
                    "tests/projects/sbt-service/src/main/scala/vandebron/mpyl/Main.scala": "M",
                },
            )

            # both job and sbt-service should be executed
            assert len(project_executions) == 2

            job_execution = next(
                p for p in project_executions if p.project.name == "job"
            )

            # a build dependency changed, so this project should always run even if there's a cached version available
            assert not job_execution.cached
            assert job_execution.hashed_changes == HASHED_CHANGES_OF_JOB

    def test_should_correctly_check_root_path(self):
        assert not is_file_a_dependency(
            self.logger,
            load_project(
                Path("tests/projects/sbt-service/deployment/project.yml"),
                validate_project_yaml=True,
            ),
            stage=TestStage.build().name,
            path="tests/projects/sbt-service-other/file.py",
        )

    def test_is_stage_cached(self):
        hashed_changes = "a generated test hash"

        def create_test_output(success: bool = True):
            return Output(
                success=success, message="an output message", hash=hashed_changes
            )

        assert not is_project_cached_for_stage(
            logger=self.logger,
            project="a test project",
            stage="deploy",
            output=create_test_output(),
            hashed_changes=hashed_changes,
        ), "should not be cached if the stage is deploy"

        assert not is_project_cached_for_stage(
            logger=self.logger,
            project="a test project",
            stage="a test stage",
            output=None,
            hashed_changes=hashed_changes,
        ), "should not be cached if no output"

        assert not is_project_cached_for_stage(
            logger=self.logger,
            project="a test project",
            stage="a test stage",
            output=create_test_output(success=False),
            hashed_changes=hashed_changes,
        ), "should not be cached if output is not successful"

        assert not is_project_cached_for_stage(
            logger=self.logger,
            project="a test project",
            stage="a test stage",
            output=create_test_output(),
            hashed_changes=None,
        ), "should not be cached if there are no changes in the current run"

        assert not is_project_cached_for_stage(
            logger=self.logger,
            project="a test project",
            stage="a test stage",
            output=create_test_output(),
            hashed_changes="a hash that doesn't match",
        ), "should not be cached if hash doesn't match"

        assert is_project_cached_for_stage(
            logger=self.logger,
            project="a test project",
            stage="a test stage",
            output=create_test_output(),
            hashed_changes=hashed_changes,
        ), "should be cached if hash matches"

    def test_read_output_with_old_artifact_spec(self):
        assert not is_project_cached_for_stage(
            logger=self.logger,
            project="a test project",
            stage="a test stage",
            output=Output.try_read(test_resource_path, "output-with-legacy-artifact"),
            hashed_changes="a generated hash",
        ), "should not be cached, but it shouldn't explode"

    def test_listing_override_files(self):
        touched_files = {"tests/projects/overriden-project/file.py": "A"}
        projects = load_projects()
        projects_for_build = find_projects_to_execute(
            self.logger,
            projects,
            TestStage.build().name,
            Changeset("revision", touched_files),
        )
        projects_for_test = find_projects_to_execute(
            self.logger,
            projects,
            TestStage.test().name,
            Changeset("revision", touched_files),
        )
        projects_for_deploy = find_projects_to_execute(
            self.logger,
            projects,
            TestStage.deploy().name,
            Changeset("revision", touched_files),
        )
        assert len(projects_for_build) == 1
        assert len(projects_for_test) == 1
        assert len(projects_for_deploy) == 2
        assert projects_for_deploy.pop().project.kubernetes.port_mappings == {
            8088: 8088,
            8089: 8089,
        }
        # as the env variables are not key value pair, they are a bit tricky to merge
        # 1 in overriden-project and 1 in parent project
        # assert(len(projects_for_deploy.pop().deployment.properties.env) == 2)

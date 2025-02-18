import logging
from pathlib import Path

from src.mpyl.plan.discovery import (
    find_projects_to_execute,
    is_file_a_dependency,
)
from src.mpyl.project import load_project
from src.mpyl.utilities.repo import Changeset
from tests.projects.find import load_projects
from tests.test_resources.test_data import TestStage


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
            changeset=Changeset(files_touched),
        )

    def test_changeset_from_files(self):
        changeset = Changeset.from_files(
            self.logger,
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
            {
                "tests/projects/service/file.py": "A",
                "tests/some_file.txt": "A",
            }
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
        projects = self._helper_find_projects_to_execute(
            files_touched={
                "tests/projects/job/deployment/project.yml": "M",
            },
        )
        assert len(projects) == 1
        assert next(p for p in projects if p.name == "job")

    def test_stage_with_files_changed_but_filtered(self):
        projects = self._helper_find_projects_to_execute(
            files_touched={
                "tests/projects/job/deployment/project.yml": "D",
            },
        )
        assert len(projects) == 1
        assert next(p for p in projects if p.name == "job")

    def test_stage_with_build_dependency_changed(self):
        projects = self._helper_find_projects_to_execute(
            files_touched={
                "tests/projects/sbt-service/src/main/scala/vandebron/mpyl/Main.scala": "M"
            },
        )

        # both job and sbt-service should be executed
        assert len(projects) == 2
        assert next(p for p in projects if p.name == "job")
        assert next(p for p in projects if p.name == "sbtservice")

    def test_stage_with_test_dependency_changed(self):
        projects = self._helper_find_projects_to_execute(
            files_touched={"tests/projects/service/file.py": "M"},
        )

        # job should not be executed because it wasn't modified and service is only a test dependency
        assert len(projects) == 1
        assert not {p for p in projects if p.name == "job"}

    def test_stage_with_files_changed_and_dependency_changed(self):
        projects = self._helper_find_projects_to_execute(
            files_touched={
                "tests/projects/job/deployment/project.yml": "M",
                "tests/projects/sbt-service/src/main/scala/vandebron/mpyl/Main.scala": "M",
            },
        )

        # both job and sbt-service should be executed
        assert len(projects) == 2
        assert next(p for p in projects if p.name == "job")
        assert next(p for p in projects if p.name == "sbtservice")

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

    def test_listing_override_files(self):
        touched_files = {"tests/projects/overriden-project/file.py": "A"}
        projects = load_projects()
        projects_for_build = find_projects_to_execute(
            self.logger,
            projects,
            TestStage.build().name,
            Changeset(touched_files),
        )
        projects_for_test = find_projects_to_execute(
            self.logger,
            projects,
            TestStage.test().name,
            Changeset(touched_files),
        )
        projects_for_deploy = find_projects_to_execute(
            self.logger,
            projects,
            TestStage.deploy().name,
            Changeset(touched_files),
        )
        assert len(projects_for_build) == 1
        assert len(projects_for_test) == 1
        assert len(projects_for_deploy) == 2
        assert projects_for_deploy.pop().deployments[0].kubernetes.port_mappings == {
            8088: 8088,
            8089: 8089,
        }
        # as the env variables are not key value pair, they are a bit tricky to merge
        # 1 in overriden-project and 1 in parent project
        # assert(len(projects_for_deploy.pop().deployment.properties.env) == 2)

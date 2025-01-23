import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import pytest

from src.mpyl.project import Project, Stages
from src.mpyl.project_execution import ProjectExecution
from src.mpyl.run_plan import RunPlan
from tests.test_resources.test_data import TestStage

build_stage = TestStage.build()
test_stage = TestStage.test()
deploy_stage = TestStage.deploy()


def stub_execution(name: str, cached: bool = False) -> ProjectExecution:
    project = Project(
        name=name,
        description="a project description",
        path=f"path/to/{name}",
        pipeline=None,
        stages=Stages.from_config({}),
        maintainer=[],
        docker=None,
        build=None,
        deployments=[],
        dependencies=None,
        kubernetes=None,
        _dagster=None,
    )
    if cached:
        return ProjectExecution.skip(project)
    return ProjectExecution.run(project)


execution_1 = stub_execution("project 1")
execution_2 = stub_execution("project 2")
cached_execution = stub_execution("a cached project", cached=True)


class TestEmptyPlan:
    run_plan = RunPlan.empty()

    def test_empty(self):
        assert self.run_plan.all_known_projects == set()
        assert not self.run_plan._full_plan
        assert not self.run_plan._selected_plan

    @pytest.mark.parametrize(
        argnames="use_full_plan",
        argvalues=[
            pytest.param(True, id="use_full_plan=True"),
            pytest.param(False, id="use_full_plan=False"),
        ],
    )
    def test_get_all_executions(self, use_full_plan):
        assert self.run_plan._get_all_executions(use_full_plan=use_full_plan) == set()

    @pytest.mark.parametrize(
        argnames="use_full_plan",
        argvalues=[
            pytest.param(True, id="use_full_plan=True"),
            pytest.param(False, id="use_full_plan=False"),
        ],
    )
    def test_get_all_projects(self, use_full_plan):
        assert self.run_plan._get_all_projects(use_full_plan=use_full_plan) == set()

    @pytest.mark.parametrize(
        argnames="stage,use_full_plan",
        argvalues=[
            pytest.param(
                build_stage, True, id=f"stage={build_stage.name}, use_full_plan=True"
            ),
            pytest.param(
                build_stage, False, id=f"stage={build_stage.name}, use_full_plan=False"
            ),
            pytest.param(
                test_stage, True, id=f"stage={test_stage.name}, use_full_plan=True"
            ),
            pytest.param(
                test_stage, False, id=f"stage={test_stage.name}, use_full_plan=False"
            ),
            pytest.param(
                deploy_stage, True, id=f"stage={deploy_stage.name}, use_full_plan=True"
            ),
            pytest.param(
                deploy_stage,
                False,
                id=f"stage={deploy_stage.name}, use_full_plan=False",
            ),
        ],
    )
    def test_get_projects_for_stage(self, stage, use_full_plan):
        assert (
            self.run_plan._get_executions_for_stage(
                stage=stage, use_full_plan=use_full_plan
            )
            == set()
        )

    @pytest.mark.parametrize(
        argnames="use_full_plan",
        argvalues=[
            pytest.param(True, id="use_full_plan=True"),
            pytest.param(False, id="use_full_plan=False"),
        ],
    )
    def test_get_all_stages(self, use_full_plan):
        assert not self.run_plan._get_all_stages(use_full_plan=use_full_plan)

    @pytest.mark.parametrize(
        argnames="include_cached_projects",
        argvalues=[
            pytest.param(True, id="include_cached_projects=True"),
            pytest.param(False, id="include_cached_projects=False"),
        ],
    )
    def test_has_projects_to_run(self, include_cached_projects):
        assert not self.run_plan._has_projects_to_run(
            include_cached_projects=include_cached_projects,
        )

    def test_get_project_to_execute(self):
        with pytest.raises(ValueError):
            self.run_plan.get_project_to_execute(
                stage_name="any stage", project_name="any project"
            )


class TestFullRunPlan:
    full_plan = {build_stage: {execution_1, execution_2}, deploy_stage: {execution_2}}
    run_plan = RunPlan.create(
        all_known_projects={execution_1.project, execution_2.project}, plan=full_plan
    )

    with NamedTemporaryFile() as temp_file:
        test_run_json = Path(temp_file.name)

        @patch("src.mpyl.run_plan.RUN_PLAN_JSON_FILE", test_run_json)
        def test_write_to_json(self):
            full_plan = {
                build_stage: {execution_1, execution_2},
                test_stage: {execution_1},
                deploy_stage: {execution_2, cached_execution},
            }
            run_plan = RunPlan.create(all_known_projects=set(), plan=full_plan)

            run_plan.write_to_json_file()
            with open(self.test_run_json, encoding="utf-8") as file:
                run_plan_json = json.load(file)

                def get_project_json(name: str):
                    return next(
                        (
                            project
                            for project in run_plan_json
                            if project["service"] == name
                        ),
                        None,
                    )

                project1 = get_project_json("project 1")
                assert project1["build"] is True
                assert project1["test"] is True
                assert project1["deploy"] is False
                project2 = get_project_json("project 2")
                assert project2["build"] is True
                assert project2["test"] is False
                assert project2["deploy"] is True
                cached_project = get_project_json("a cached project")
                assert cached_project["build"] is False
                assert cached_project["test"] is False
                assert cached_project["deploy"] is False
                assert get_project_json("an unknown project") is None

    def test_create(self):
        assert self.run_plan.all_known_projects == {
            execution_1.project,
            execution_2.project,
        }
        assert self.run_plan._full_plan == self.full_plan
        assert self.run_plan._selected_plan == self.full_plan

    @pytest.mark.parametrize(
        argnames="use_full_plan",
        argvalues=[
            pytest.param(True, id="use_full_plan=True"),
            pytest.param(False, id="use_full_plan=False"),
        ],
    )
    def test_get_all_executions(self, use_full_plan):
        assert self.run_plan._get_all_executions(use_full_plan=use_full_plan) == {
            execution_1,
            execution_2,
        }

    @pytest.mark.parametrize(
        argnames="use_full_plan",
        argvalues=[
            pytest.param(True, id="use_full_plan=True"),
            pytest.param(False, id="use_full_plan=False"),
        ],
    )
    def test_get_all_projects(self, use_full_plan):
        assert self.run_plan._get_all_projects(use_full_plan=use_full_plan) == {
            execution_1.project,
            execution_2.project,
        }

    @pytest.mark.parametrize(
        argnames="use_full_plan",
        argvalues=[
            pytest.param(True, id="use_full_plan=True"),
            pytest.param(False, id="use_full_plan=False"),
        ],
    )
    def test_get_projects_for_stage(self, use_full_plan):
        assert self.run_plan._get_executions_for_stage(
            stage=build_stage, use_full_plan=use_full_plan
        ) == {execution_1, execution_2}
        assert (
            self.run_plan._get_executions_for_stage(
                stage=test_stage, use_full_plan=use_full_plan
            )
            == set()
        )
        assert self.run_plan._get_executions_for_stage(
            stage=deploy_stage, use_full_plan=use_full_plan
        ) == {execution_2}

    @pytest.mark.parametrize(
        argnames="use_full_plan",
        argvalues=[
            pytest.param(True, id="use_full_plan=True"),
            pytest.param(False, id="use_full_plan=False"),
        ],
    )
    def test_get_all_stages(self, use_full_plan):
        assert self.run_plan._get_all_stages(use_full_plan=use_full_plan) == [
            build_stage,
            deploy_stage,
        ]

    def test_has_projects_to_run_with_some_cached_projects(self):
        run_plan_with_some_cached_projects = RunPlan.create(
            all_known_projects=set(),
            plan={build_stage: {execution_1, cached_execution}},
        )

        assert run_plan_with_some_cached_projects._has_projects_to_run(
            include_cached_projects=True
        )
        assert run_plan_with_some_cached_projects._has_projects_to_run(
            include_cached_projects=False
        )

    def test_has_projects_to_run_with_only_cached_projects(self):
        run_plan_with_only_cached_projects = RunPlan.create(
            all_known_projects=set(), plan={build_stage: {cached_execution}}
        )

        assert run_plan_with_only_cached_projects._has_projects_to_run(
            include_cached_projects=True
        )
        assert not run_plan_with_only_cached_projects._has_projects_to_run(
            include_cached_projects=False
        )

    def test_get_project_to_execute(self):
        assert (
            self.run_plan.get_project_to_execute(
                stage_name=deploy_stage.name, project_name=execution_2.name
            )
            == execution_2
        )

        with pytest.raises(ValueError):
            self.run_plan.get_project_to_execute(
                stage_name="unknown stage", project_name=execution_1.name
            )
        with pytest.raises(ValueError):
            self.run_plan.get_project_to_execute(
                stage_name=build_stage.name, project_name="unknown project"
            )
        with pytest.raises(ValueError):
            self.run_plan.get_project_to_execute(
                stage_name=deploy_stage.name, project_name=execution_1.name
            )


class TestRunPlanWithSelectedProjectInASingleStage:
    full_plan = {build_stage: {execution_1, execution_2}, deploy_stage: {execution_2}}
    run_plan = RunPlan.create(
        all_known_projects={execution_1.project, execution_2.project}, plan=full_plan
    ).select_project(execution_1.name)

    with NamedTemporaryFile() as temp_file:
        test_run_json = Path(temp_file.name)

        @patch("src.mpyl.run_plan.RUN_PLAN_JSON_FILE", test_run_json)
        def test_write_to_json(self):
            full_plan = {
                build_stage: {execution_1, execution_2},
                test_stage: {execution_1},
                deploy_stage: {execution_2},
            }
            run_plan = RunPlan.create(
                all_known_projects=set(), plan=full_plan
            ).select_project(execution_1.name)

            run_plan.write_to_json_file()
            with open(self.test_run_json, encoding="utf-8") as file:
                run_plan_json = json.load(file)

                def get_project_json(name: str):
                    return next(
                        (
                            project
                            for project in run_plan_json
                            if project["service"] == name
                        ),
                        None,
                    )

                project1 = get_project_json("project 1")
                assert project1["build"] is True
                assert project1["test"] is True
                assert "deploy" not in project1
                assert get_project_json("project 2") is None

    def test_select_project(self):
        assert self.run_plan.all_known_projects == {
            execution_1.project,
            execution_2.project,
        }
        assert self.run_plan._full_plan == self.full_plan
        assert self.run_plan._selected_plan == {build_stage: {execution_1}}

    def test_select_invalid_project(self):
        with pytest.raises(ValueError):
            RunPlan.create(
                all_known_projects=set(), plan=self.full_plan
            ).select_project("a project that does not belong to the run plan")

    def test_get_all_executions(self):
        assert self.run_plan._get_all_executions(use_full_plan=True) == {
            execution_1,
            execution_2,
        }
        assert self.run_plan._get_all_executions(use_full_plan=False) == {execution_1}

    def test_get_all_projects(self):
        assert self.run_plan._get_all_projects(use_full_plan=True) == {
            execution_1.project,
            execution_2.project,
        }
        assert self.run_plan._get_all_projects(use_full_plan=False) == {
            execution_1.project
        }

    def test_get_projects_for_stage(self):
        assert self.run_plan._get_executions_for_stage(
            stage=build_stage, use_full_plan=True
        ) == {execution_1, execution_2}
        assert self.run_plan._get_executions_for_stage(
            stage=build_stage, use_full_plan=False
        ) == {execution_1}
        assert (
            self.run_plan._get_executions_for_stage(
                stage=test_stage, use_full_plan=True
            )
            == set()
        )
        assert (
            self.run_plan._get_executions_for_stage(
                stage=test_stage, use_full_plan=False
            )
            == set()
        )
        assert self.run_plan._get_executions_for_stage(
            stage=deploy_stage, use_full_plan=True
        ) == {execution_2}
        assert (
            self.run_plan._get_executions_for_stage(
                stage=deploy_stage, use_full_plan=False
            )
            == set()
        )

    def test_get_all_stages(self):
        assert self.run_plan._get_all_stages(use_full_plan=True) == [
            build_stage,
            deploy_stage,
        ]
        assert self.run_plan._get_all_stages(use_full_plan=False) == [build_stage]

    def test_has_projects_to_run_with_selected_non_cached_project(self):
        assert self.run_plan._has_projects_to_run(include_cached_projects=True)
        assert self.run_plan._has_projects_to_run(include_cached_projects=False)

    def test_has_projects_to_run_with_selected_cached_project(self):
        run_plan_with_selected_project = RunPlan.create(
            all_known_projects=set(),
            plan={
                build_stage: {cached_execution},
                deploy_stage: {
                    stub_execution("a different cached project", cached=True)
                },
            },
        ).select_project(cached_execution.name)

        assert run_plan_with_selected_project._has_projects_to_run(
            include_cached_projects=True
        )
        assert not run_plan_with_selected_project._has_projects_to_run(
            include_cached_projects=False
        )

    def test_get_project_to_execute(self):
        assert (
            self.run_plan.get_project_to_execute(
                stage_name=build_stage.name, project_name=execution_1.name
            )
            == execution_1
        )

        with pytest.raises(ValueError):
            self.run_plan.get_project_to_execute(
                stage_name=deploy_stage.name, project_name=execution_1.name
            )


class TestRunPlanWithSelectedProjectInMultipleStages:
    full_plan = {build_stage: {execution_1, execution_2}, deploy_stage: {execution_1}}

    run_plan = RunPlan.create(
        all_known_projects={execution_1.project, execution_2.project}, plan=full_plan
    ).select_project(execution_1.name)

    def test_select_project(self):
        assert self.run_plan.all_known_projects == {
            execution_1.project,
            execution_2.project,
        }
        assert self.run_plan._full_plan == self.full_plan
        assert self.run_plan._selected_plan == {
            build_stage: {execution_1},
            deploy_stage: {execution_1},
        }

    def test_select_invalid_project(self):
        with pytest.raises(ValueError):
            RunPlan.create(
                all_known_projects=set(), plan=self.full_plan
            ).select_project("a project that does not belong to the run plan")

    def test_get_all_executions(self):
        assert self.run_plan._get_all_executions(use_full_plan=True) == {
            execution_1,
            execution_2,
        }
        assert self.run_plan._get_all_executions(use_full_plan=False) == {execution_1}

    def test_get_all_projects(self):
        assert self.run_plan._get_all_projects(use_full_plan=True) == {
            execution_1.project,
            execution_2.project,
        }
        assert self.run_plan._get_all_projects(use_full_plan=False) == {
            execution_1.project
        }

    def test_get_all_cached(self):
        execution = stub_execution("project 1")
        execution_cached = stub_execution("project 1", cached=True)
        run_plan = RunPlan.create(
            all_known_projects=set(),
            plan={
                build_stage: {execution},
                test_stage: {execution},
                deploy_stage: {execution_cached},
            },
        )
        assert run_plan._get_all_executions(use_full_plan=True) == {
            execution_cached,
            execution,
        }
        assert run_plan._get_all_projects(use_full_plan=True) == {
            execution.project,
        }

    def test_get_projects_for_stage(self):
        assert self.run_plan._get_executions_for_stage(
            stage=build_stage, use_full_plan=True
        ) == {execution_1, execution_2}
        assert self.run_plan._get_executions_for_stage(
            stage=build_stage, use_full_plan=False
        ) == {execution_1}
        assert (
            self.run_plan._get_executions_for_stage(
                stage=test_stage, use_full_plan=True
            )
            == set()
        )
        assert (
            self.run_plan._get_executions_for_stage(
                stage=test_stage, use_full_plan=False
            )
            == set()
        )
        assert self.run_plan._get_executions_for_stage(
            stage=deploy_stage, use_full_plan=True
        ) == {execution_1}
        assert self.run_plan._get_executions_for_stage(
            stage=deploy_stage, use_full_plan=False
        ) == {execution_1}

    def test_get_all_stages(self):
        assert self.run_plan._get_all_stages(use_full_plan=True) == [
            build_stage,
            deploy_stage,
        ]
        assert self.run_plan._get_all_stages(use_full_plan=False) == [
            build_stage,
            deploy_stage,
        ]

    def test_has_projects_to_run_with_selected_non_cached_project(self):
        assert self.run_plan._has_projects_to_run(include_cached_projects=True)
        assert self.run_plan._has_projects_to_run(include_cached_projects=False)

    def test_has_projects_to_run_with_selected_cached_project(self):
        run_plan_with_selected_project = RunPlan.create(
            all_known_projects=set(),
            plan={
                build_stage: {cached_execution},
                test_stage: {stub_execution("a different cached project", cached=True)},
                deploy_stage: {cached_execution},
            },
        ).select_project(cached_execution.name)

        assert run_plan_with_selected_project._has_projects_to_run(
            include_cached_projects=True
        )
        assert not run_plan_with_selected_project._has_projects_to_run(
            include_cached_projects=False
        )

    def test_get_project_to_execute(self):
        assert (
            self.run_plan.get_project_to_execute(
                stage_name=build_stage.name, project_name=execution_1.name
            )
            == execution_1
        )
        assert (
            self.run_plan.get_project_to_execute(
                stage_name=deploy_stage.name, project_name=execution_1.name
            )
            == execution_1
        )
        with pytest.raises(ValueError):
            self.run_plan.get_project_to_execute(
                stage_name=build_stage.name, project_name=execution_2.name
            )

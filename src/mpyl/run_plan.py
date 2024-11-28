"""This module contains the RunPlan class."""

import json
import logging
import operator
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from rich.console import Console
from rich.markdown import Markdown

from .constants import RUN_ARTIFACTS_FOLDER
from .project import Project, Stage, load_project
from .project_execution import ProjectExecution
from .plan.discovery import find_projects_to_execute, find_projects
from .utilities.repo import Changeset

RUN_PLAN_PICKLE_FILE = Path(RUN_ARTIFACTS_FOLDER) / "run_plan.pickle"
RUN_PLAN_JSON_FILE = Path(RUN_ARTIFACTS_FOLDER) / "run_plan.json"


@dataclass(frozen=True)
class RunPlan:
    all_known_projects: set[Project]
    _full_plan: dict[Stage, set[ProjectExecution]]
    selected_plan: dict[Stage, set[ProjectExecution]]

    @classmethod
    def empty(cls) -> "RunPlan":
        return cls(all_known_projects=set(), _full_plan={}, selected_plan={})

    @classmethod
    def create(
        cls, all_known_projects: set[Project], plan: dict[Stage, set[ProjectExecution]]
    ) -> "RunPlan":
        return cls(
            all_known_projects=all_known_projects, _full_plan=plan, selected_plan=plan
        )

    def select_stage(self, stage_name: str) -> "RunPlan":
        stage = None
        for s in self._get_all_stages(use_full_plan=False):
            if s.name == stage_name:
                stage = s
                break
        if not stage:
            raise ValueError(
                f"Unable to select stage outside of the run plan: '{stage_name}'"
            )

        return RunPlan(
            all_known_projects=self.all_known_projects,
            _full_plan=self._full_plan,
            selected_plan={stage: self.get_projects_for_stage(stage)},
        )

    def select_project(self, project_name: str) -> "RunPlan":
        project = None
        for p in self._get_all_projects(use_full_plan=False):
            if p.name == project_name:
                project = p
                break
        if not project:
            raise ValueError(
                f"Unable to select project outside of the run plan: '{project_name}'"
            )

        selected_plan = {}
        for stage in self._get_all_stages(use_full_plan=False):
            filtered = {
                e
                for e in self.get_projects_for_stage(stage, use_full_plan=False)
                if e.name == project_name
            }
            if filtered:
                selected_plan[stage] = filtered

        return RunPlan(
            all_known_projects=self.all_known_projects,
            _full_plan=self._full_plan,
            selected_plan=selected_plan,
        )

    def has_projects_to_run(self, include_cached_projects: bool) -> bool:
        return any(
            include_cached_projects or not project_execution.cached
            for project_execution in self._get_all_projects(use_full_plan=False)
        )

    def _get_all_stages(self, use_full_plan: bool = False) -> set[Stage]:
        if use_full_plan:
            return set(self._full_plan.keys())
        return set(self.selected_plan.keys())

    def _get_all_projects(self, use_full_plan: bool = False) -> set[ProjectExecution]:
        def flatten(plan: dict[Stage, set[ProjectExecution]]):
            return {
                project_execution
                for project_executions in plan.values()
                for project_execution in project_executions
            }

        if use_full_plan:
            return flatten(self._full_plan)
        return flatten(self.selected_plan)

    def get_projects_for_stage(
        self, stage: Stage, use_full_plan: bool = False
    ) -> set[ProjectExecution]:
        if use_full_plan:
            return self._full_plan.get(stage, set())
        return self.selected_plan.get(stage, set())

    def get_projects_for_stage_name(
        self, stage_name: str, use_full_plan: bool = False
    ) -> set[ProjectExecution]:
        def find_stage(plan: dict[Stage, set[ProjectExecution]]):
            iterator = (
                project_executions
                for stage, project_executions in plan.items()
                if stage.name == stage_name
            )
            return next(iterator, set())

        if use_full_plan:
            return find_stage(self._full_plan)
        return find_stage(self.selected_plan)

    def get_project_to_execute(
        self, stage_name: str, project_name: str
    ) -> ProjectExecution:
        stage = None
        project = None
        for s in self._get_all_stages(use_full_plan=False):
            if s.name == stage_name:
                stage = s
                for p in self.get_projects_for_stage(s, use_full_plan=False):
                    if p.name == project_name:
                        project = p
                        break
                break
        if not stage:
            raise ValueError(
                f"Unable to select stage outside of the run plan: '{stage_name}'"
            )
        if not project:
            raise ValueError(
                f"Unable to select project outside of the run plan: '{project_name}'"
            )
        return project

    def write_to_pickle_file(self):
        logger = logging.getLogger("mpyl")
        os.makedirs(os.path.dirname(RUN_PLAN_PICKLE_FILE), exist_ok=True)
        with open(RUN_PLAN_PICKLE_FILE, "wb") as file:
            logger.info(f"Storing run plan in: {RUN_PLAN_PICKLE_FILE}")
            pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)

    def write_to_json_file(self):
        run_plan: dict = {}

        for stage, executions in self._full_plan.items():
            for execution in executions:
                stages: list[dict[str, Union[str, bool]]] = run_plan.get(
                    execution.project.name, {}
                ).get("stages", [])
                stages.append({"name": stage.name, "cached": execution.cached})

                run_plan.update(
                    {
                        execution.project.name: {
                            "service": execution.project.name,
                            "path": execution.project.path,
                            "artifacts_path": str(execution.project.target_path),
                            "base_path": str(execution.project.root_path),
                            "maintainers": execution.project.maintainer,
                            "pipeline": execution.project.pipeline,
                            "stages": stages,
                        }
                    }
                )

        os.makedirs(os.path.dirname(RUN_PLAN_JSON_FILE), exist_ok=True)
        with open(RUN_PLAN_JSON_FILE, "w", encoding="utf-8") as file:
            json.dump(list(run_plan.values()), file)

    @staticmethod
    def load_from_pickle_file():
        logger = logging.getLogger("mpyl")

        if RUN_PLAN_PICKLE_FILE.is_file():
            logger.info(f"Loading existing run plan: {RUN_PLAN_PICKLE_FILE}")
            with open(RUN_PLAN_PICKLE_FILE, "rb") as file:
                run_plan: RunPlan = pickle.load(file)
                logger.debug(f"Run plan: {run_plan}")
                return run_plan

        else:
            raise ValueError(
                f"Unable to find existing run plan at path {RUN_PLAN_PICKLE_FILE}"
            )

    def print_markdown(self, console: Console, stages: list[Stage]):
        if self.has_projects_to_run(include_cached_projects=True):
            result = ""

            for stage in stages:
                executions = self.get_projects_for_stage(stage)
                if executions:
                    project_names = [
                        f"_{execution.name}{' (cached)' if execution.cached else ''}_"
                        for execution in sorted(
                            executions, key=operator.attrgetter("name")
                        )
                    ]

                    result += (
                        f'{stage.display_string()}:  \n{", ".join(project_names)}  \n'
                    )
                else:
                    result += "🤷 Nothing to do  \n"

            console.print(Markdown("**Execution plan:**  \n" + result))

        else:
            logger = logging.getLogger("mpyl")
            logger.info("No changes detected, nothing to do.")


def discover_run_plan(
    revision: str,
    all_stages: list[Stage],
    changed_files_path: Path,
) -> RunPlan:
    logger = logging.getLogger("mpyl")
    logger.info("Discovering run plan...")

    all_projects = set(
        map(
            lambda p: load_project(
                project_path=p, validate_project_yaml=False, log=True
            ),
            find_projects(),
        )
    )

    changeset = Changeset.from_files(
        logger=logger, sha=revision, changed_files_path=changed_files_path
    )

    plan = {}
    for stage in all_stages:
        project_executions = find_projects_to_execute(
            logger=logger,
            all_projects=all_projects,
            stage=stage.name,
            changeset=changeset,
        )

        logger.debug(
            f"Will execute projects for stage {stage.name}: {[p.name for p in project_executions]}"
        )
        plan.update({stage: project_executions})

    return RunPlan.create(all_projects, plan)

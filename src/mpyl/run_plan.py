"""This module contains the RunPlan class."""

import json
import logging
import operator
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from rich.console import Console
from rich.markdown import Markdown

from .constants import RUN_ARTIFACTS_FOLDER
from .project import Project, Stage, load_project
from .project_execution import ProjectExecution
from .stages.discovery import find_projects_to_execute, find_projects
from .utilities.repo import Changeset

RUN_PLAN_PICKLE_FILE = Path(RUN_ARTIFACTS_FOLDER) / "run_plan.pickle"
RUN_PLAN_JSON_FILE = Path(RUN_ARTIFACTS_FOLDER) / "run_plan.json"


@dataclass(frozen=True)
class RunPlan:
    all_known_projects: set[Project]
    full_plan: dict[Stage, set[ProjectExecution]]
    selected_plan: dict[Stage, set[ProjectExecution]]

    @classmethod
    def empty(cls) -> "RunPlan":
        return cls(all_known_projects=set(), full_plan={}, selected_plan={})

    @classmethod
    def create(
        cls, all_known_projects: set[Project], plan: dict[Stage, set[ProjectExecution]]
    ) -> "RunPlan":
        return cls(
            all_known_projects=all_known_projects, full_plan=plan, selected_plan=plan
        )

    def select_stage(self, stage: Stage) -> "RunPlan":
        return RunPlan(
            all_known_projects=self.all_known_projects,
            full_plan=self.full_plan,
            selected_plan={stage: self.get_projects_for_stage(stage)},
        )

    def select_projects(self, projects: set[Project]) -> "RunPlan":
        selected_plan = {}

        for stage, executions in self.selected_plan.items():
            selected_plan[stage] = {e for e in executions if e.project in projects}

        return RunPlan(
            all_known_projects=self.all_known_projects,
            full_plan=self.full_plan,
            selected_plan=selected_plan,
        )

    def has_projects_to_run(
        self, include_cached_projects: bool, use_full_plan: bool = False
    ) -> bool:
        return any(
            include_cached_projects or not project_execution.cached
            for project_execution in self.get_all_projects(use_full_plan)
        )

    def get_all_projects(self, use_full_plan: bool = False) -> set[ProjectExecution]:
        def flatten(plan: dict[Stage, set[ProjectExecution]]):
            return {
                project_execution
                for project_executions in plan.values()
                for project_execution in project_executions
            }

        if use_full_plan:
            return flatten(self.full_plan)
        return flatten(self.selected_plan)

    def get_projects_for_stage(
        self, stage: Stage, use_full_plan: bool = False
    ) -> set[ProjectExecution]:
        if use_full_plan:
            return self.full_plan.get(stage, set())
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
            return find_stage(self.full_plan)
        return find_stage(self.selected_plan)

    def write_to_pickle_file(self):
        logger = logging.getLogger("mpyl")
        os.makedirs(os.path.dirname(RUN_PLAN_PICKLE_FILE), exist_ok=True)
        with open(RUN_PLAN_PICKLE_FILE, "wb") as file:
            logger.info(f"Storing run plan in: {RUN_PLAN_PICKLE_FILE}")
            pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)

    def write_to_json_file(self):
        run_plan: dict = {}

        for stage, executions in self.full_plan.items():
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
    def load_from_pickle_file(
        selected_projects: Optional[set[Project]],
        selected_stage: Optional[Stage],
    ):
        logger = logging.getLogger("mpyl")

        if RUN_PLAN_PICKLE_FILE.is_file():
            logger.info(f"Loading existing run plan: {RUN_PLAN_PICKLE_FILE}")
            with open(RUN_PLAN_PICKLE_FILE, "rb") as file:
                run_plan: RunPlan = pickle.load(file)
                logger.debug(f"Run plan: {run_plan}")
                if selected_stage:
                    run_plan = run_plan.select_stage(selected_stage)
                    logger.info(f"Selected stage: {selected_stage.name}")
                    logger.debug(f"Run plan: {run_plan}")
                if selected_projects:
                    run_plan = run_plan.select_projects(selected_projects)
                    logger.info(
                        f"Selected projects: {set(p.name for p in selected_projects)}"
                    )
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
                if not executions:
                    result += "🤷 Nothing to do  \n"

                project_names = [
                    f"_{execution.name}{' (cached)' if execution.cached else ''}_"
                    for execution in sorted(executions, key=operator.attrgetter("name"))
                ]

                result += f'{stage.icon} {stage.name.capitalize()}:  \n{", ".join(project_names)}  \n'

            console.print(Markdown("**Execution plan:**  \n" + result))

        else:
            logger = logging.getLogger("mpyl")
            logger.info("No changes detected, nothing to do.")


def discover_run_plan(
    revision: str,
    all_stages: list[Stage],
    changed_files_path: str,
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

    changeset = Changeset.from_file(
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

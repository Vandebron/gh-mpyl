"""This module contains the RunPlan class."""

import json
import logging
import operator
import os
import pickle
from dataclasses import dataclass
from pathlib import Path

from .constants import RUN_ARTIFACTS_FOLDER
from .project import Project, Stage, load_project
from .plan.discovery import find_projects_to_execute, find_projects
from .utilities.repo import Changeset

RUN_PLAN_PICKLE_FILE = Path(RUN_ARTIFACTS_FOLDER) / "run_plan.pickle"
RUN_PLAN_JSON_FILE = Path(RUN_ARTIFACTS_FOLDER) / "run_plan.json"
RUN_PLAN_SUMMARY_FILE = Path(RUN_ARTIFACTS_FOLDER) / "run_plan_summary.md"


@dataclass(frozen=True)
class RunPlan:
    all_known_projects: set[Project]
    _full_plan: dict[Stage, set[Project]]
    _selected_plan: dict[Stage, set[Project]]

    @classmethod
    def empty(cls) -> "RunPlan":
        return cls(all_known_projects=set(), _full_plan={}, _selected_plan={})

    @classmethod
    def create(
        cls, all_known_projects: set[Project], plan: dict[Stage, set[Project]]
    ) -> "RunPlan":
        return cls(
            all_known_projects=all_known_projects, _full_plan=plan, _selected_plan=plan
        )

    def select_project(self, project_name: str) -> "RunPlan":
        selected_project = None
        for project in self._get_all_projects():
            if project.name == project_name:
                selected_project = project
                break
        if not selected_project:
            raise ValueError(
                f"Unable to select project outside of the run plan: '{project_name}'"
            )

        selected_plan = {}
        for stage in self._get_all_stages():
            filtered = {
                project
                for project in self._get_projects_for_stage(stage)
                if project.name == project_name
            }
            if filtered:
                selected_plan[stage] = filtered

        return RunPlan(
            all_known_projects=self.all_known_projects,
            _full_plan=self._full_plan,
            _selected_plan=selected_plan,
        )

    def _get_all_stages(self, use_full_plan: bool = False) -> list[Stage]:
        if use_full_plan:
            return list(self._full_plan.keys())
        return list(self._selected_plan.keys())

    def _get_all_projects(self, use_full_plan: bool = False) -> set[Project]:
        def flatten(plan: dict[Stage, set[Project]]):
            return {p for projects_in_stage in plan.values() for p in projects_in_stage}

        if use_full_plan:
            return flatten(self._full_plan)
        return flatten(self._selected_plan)

    def _get_projects_for_stage(
        self, stage: Stage, use_full_plan: bool = False
    ) -> set[Project]:
        if use_full_plan:
            return self._full_plan.get(stage, set())
        return self._selected_plan.get(stage, set())

    def get_projects_for_stage_name(
        self, stage_name: str, use_full_plan: bool = False
    ) -> set[Project]:
        def find_stage(plan: dict[Stage, set[Project]]):
            iterator = (
                projects for stage, projects in plan.items() if stage.name == stage_name
            )
            return next(iterator, set())

        if use_full_plan:
            return find_stage(self._full_plan)
        return find_stage(self._selected_plan)

    def get_project_to_execute(self, stage_name: str, project_name: str) -> Project:
        selected_stage = None
        selected_project = None
        for stage in self._get_all_stages():
            if stage.name == stage_name:
                selected_stage = stage
                for project in self._get_projects_for_stage(stage):
                    if project.name == project_name:
                        selected_project = project
                        break
                break
        if not selected_stage:
            raise ValueError(
                f"Unable to select stage outside of the run plan: '{stage_name}'"
            )
        if not selected_project:
            raise ValueError(
                f"Unable to select project outside of the run plan: '{project_name}'"
            )
        return selected_project

    def write_to_pickle_file(self):
        logger = logging.getLogger("mpyl")
        os.makedirs(os.path.dirname(RUN_PLAN_PICKLE_FILE), exist_ok=True)
        with open(RUN_PLAN_PICKLE_FILE, "wb") as file:
            logger.info(f"Storing run plan in: {RUN_PLAN_PICKLE_FILE}")
            pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)

    def write_to_summary_file(self):
        def get_icon(project: Project, stage_name: str):
            if project.pipeline == "docker":
                return "🐳"
            if project.pipeline == "sbt":
                projects_for_stage = self.get_projects_for_stage_name(stage_name)
                project_for_stage = next(
                    (p for p in projects_for_stage if p.name == project.name),
                    None,
                )
                if project_for_stage:
                    return "☕️"
            return ""

        def is_project_in_stage(project: Project, stage_name: str):
            return any(
                project.name == project_for_stage.name
                for project_for_stage in self.get_projects_for_stage_name(stage_name)
            )

        summary = "| 👷 Project | 🏗 Build | 🧪 Test | 🚀 Deploy | 🦺 Post-deploy |\n"
        summary += "| ---------- | :------: | :-----: | :-------: | :------------: |\n"

        all_projects = self._get_all_projects()
        if len(all_projects) == 0:
            summary = "Nothing to do 🤷\n"

        for project in sorted(all_projects, key=operator.attrgetter("name")):
            build_plan = get_icon(project, "build")
            test_plan = get_icon(project, "test")
            deploy_plan = "🚀" if is_project_in_stage(project, "deploy") else ""
            postdeploy_plan = (
                "🦺" if is_project_in_stage(project, "post-deploy") else ""
            )

            summary += f"| {project.name} | {build_plan} | {test_plan} | {deploy_plan} | {postdeploy_plan} |\n"

        logger = logging.getLogger("mpyl")
        os.makedirs(os.path.dirname(RUN_PLAN_SUMMARY_FILE), exist_ok=True)
        with open(RUN_PLAN_SUMMARY_FILE, "w", encoding="utf-8") as file:
            logger.info(f"Storing run plan summary in: {RUN_PLAN_SUMMARY_FILE}")
            file.write(summary)

    def write_to_json_file(self):
        run_plan: dict = {}

        for projects in self._selected_plan.values():
            for project in projects:
                stages = {
                    stage.name: project in self._get_projects_for_stage(stage)
                    for stage in self._selected_plan.keys()
                }
                run_plan.update(
                    {
                        project.name: {
                            "service": project.name,
                            "path": project.path,
                            "artifacts_path": str(project.target_path),
                            "base_path": str(project.root_path),
                            "maintainers": project.maintainer,
                            "pipeline": project.pipeline,
                        }
                        | stages
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

    def to_markdown(self) -> str:
        lines = ["**Execution plan:**"]
        if len(self._get_all_projects()) > 0:
            for stage in self._get_all_stages():
                lines.append(f"{stage.to_markdown()}:")
                if projects := self._get_projects_for_stage(stage):
                    project_names = [
                        project.name
                        for project in sorted(projects, key=operator.attrgetter("name"))
                    ]
                    lines.append(", ".join(project_names))
                else:
                    lines.append("")

            return "  \n".join(lines)

        return "No changes detected, nothing to do."


def discover_run_plan(
    logger: logging.Logger,
    all_stages: list[Stage],
    changed_files_path: Path,
) -> RunPlan:
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
        logger=logger, changed_files_path=changed_files_path
    )

    plan = {}
    for stage in all_stages:
        projects = find_projects_to_execute(
            logger=logger,
            all_projects=all_projects,
            stage=stage.name,
            changeset=changeset,
        )

        if projects:
            logger.debug(
                f"Will execute projects for stage {stage.name}: {[p.name for p in projects]}"
            )
            plan.update({stage: projects})

    return RunPlan.create(all_projects, plan)

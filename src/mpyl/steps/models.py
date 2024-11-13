""" Model representation of run-specific configuration. """

import os
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ruamel.yaml import YAML, yaml_object  # type: ignore

from ..project import Project, Stage, Target
from ..project_execution import ProjectExecution
from ..validation import validate

yaml = YAML()


@dataclass(frozen=True)
class VersioningProperties:
    revision: str
    branch: Optional[str]
    pr_number: Optional[int]
    tag: Optional[str]

    def validate(self) -> Optional[str]:
        if not self.pr_number and not self.tag:
            return "Either pr_number or tag need to be set"
        return None

    @property
    def identifier(self) -> str:
        return self.tag if self.tag else f"pr-{self.pr_number}"


@dataclass(frozen=False)
class RunContext:
    build_id: str
    """Uniquely identifies the run. Typically a monotonically increasing number"""
    run_url: str
    """Link back to the run executor"""
    change_url: str
    """Link to changes"""
    tests_url: str
    """Link to test results"""
    user: str
    """Name of of the user that triggered the run"""
    user_email: Optional[str]
    """Email of of the user that triggered the run"""

    @staticmethod
    def from_configuration(run_details: dict):
        return RunContext(
            build_id=run_details["id"],
            run_url=run_details["run_url"],
            change_url=run_details["change_url"],
            tests_url=run_details["tests_url"],
            user=run_details["user"],
            user_email=run_details["user_email"],
        )


@dataclass(frozen=True)
class ConsoleProperties:
    log_level: str
    show_paths: bool
    width: Optional[int]

    @staticmethod
    def from_configuration(config: dict):
        console_config = config["build"]["console"]
        if os.environ.get("RUNNER_DEBUG", "0") == "1":
            log_level = "DEBUG"
        else:
            log_level = console_config.get("logLevel", "INFO")
        width = console_config.get("width", 130)
        return ConsoleProperties(
            log_level=log_level,
            show_paths=console_config.get("showPaths", False),
            width=None if width == 0 else width,
        )


@yaml_object(yaml)
@dataclass(frozen=False)
class RunProperties:
    """Contains information that is specific to a particular run of the pipeline"""

    details: RunContext
    """Run specific details"""
    target: Target
    """The deploy target"""
    versioning: VersioningProperties
    config: dict
    """Globally specified configuration, to be used by specific steps. Complies with the schema as
    specified in `mpyl_config.schema.yml`
     """
    stages: list[Stage]
    """All stage definitions"""
    projects: set[Project]
    """All projects"""
    deploy_image: Optional[str] = None
    """The docker image to deploy"""

    @staticmethod
    def from_configuration(
        target: Target,
        run_properties: dict,
        config: dict,
        all_projects: set[Project],
        cli_tag: Optional[str] = None,
        deploy_image: Optional[str] = None,
    ):
        build_dict = pkgutil.get_data(__name__, "../schema/run_properties.schema.yml")

        if build_dict:
            validate(run_properties, build_dict.decode("utf-8"))

        versioning_config = run_properties["build"]["versioning"]

        tag: Optional[str] = cli_tag or versioning_config.get("tag")
        pr_from_config: Optional[str] = versioning_config.get("pr_number")
        pr_number: Optional[int] = (
            None if tag else (int(pr_from_config) if pr_from_config else None)
        )

        versioning = VersioningProperties(
            revision=versioning_config["revision"],
            branch=versioning_config["branch"],
            pr_number=pr_number,
            tag=tag,
        )

        return RunProperties(
            details=RunContext.from_configuration(run_properties["build"]["run"]),
            target=target,
            versioning=versioning,
            config=config,
            stages=[
                Stage(stage["name"], stage["icon"])
                for stage in run_properties["stages"]
            ],
            projects=all_projects,
            deploy_image=deploy_image,
        )

    def to_stage(self, stage_name: str) -> Stage:
        stage_by_name = next(stage for stage in self.stages if stage.name == stage_name)
        if stage_by_name:
            return stage_by_name
        raise ValueError(f"Stage {stage_name} not found")

    def selected_stage(self, selected_stage_name: Optional[str]):
        return self.to_stage(selected_stage_name) if selected_stage_name else None

    def selected_projects(self, selected_project_names: Optional[str]):
        return (
            {p for p in self.stages if p.name in selected_project_names.split(",")}
            if selected_project_names
            else set()
        )


@yaml_object(yaml)
@dataclass(frozen=False)
class Input:
    project_execution: ProjectExecution
    run_properties: RunProperties
    """Run specific properties"""


@yaml_object(yaml)
@dataclass(frozen=False)  # yaml_object classes can't be frozen
class Output:
    success: bool
    message: str
    hash: Optional[str] = None

    @staticmethod
    def path(target_path: Path, stage: str):
        return Path(target_path, f"{stage}.yml")

    def write(self, target_path: Path, stage: str):
        Path(target_path).mkdir(parents=True, exist_ok=True)
        with Output.path(target_path, stage).open(mode="w+", encoding="utf-8") as file:
            yaml.dump(self, file)

    @staticmethod
    def try_read(target_path: Path, stage: str):
        path = Output.path(target_path, stage)
        if path.exists():
            with open(path, encoding="utf-8") as file:
                return yaml.load(file)
        return None

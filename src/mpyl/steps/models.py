""" Model representation of run-specific configuration. """

import os
import pkgutil
from dataclasses import dataclass
from typing import Optional

from ruamel.yaml import YAML, yaml_object

from ..project import Stage, Target
from ..validation import validate


@dataclass(frozen=True)
class VersioningProperties:
    revision: str
    branch: Optional[str]
    pr_number: Optional[int]
    tag: Optional[str]

    @staticmethod
    def from_run_properties(run_properties: dict):
        _tag = run_properties["build"]["versioning"].get("tag")
        _maybe_pr_number = run_properties["build"]["versioning"].get("pr_number")

        if _tag:
            _pr_number = None
        elif _maybe_pr_number:
            _pr_number = int(_maybe_pr_number)
        else:
            _pr_number = None

        if not _tag and not _pr_number:
            raise ValueError(
                "Either build.versioning.tag or build.versioning.pr_number need to be set"
            )

        return VersioningProperties(
            revision=run_properties["build"]["versioning"]["revision"],
            branch=run_properties["build"]["versioning"]["branch"],
            pr_number=_pr_number,
            tag=_tag,
        )

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


@yaml_object(YAML())
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
    specified in `mpyl_config.schema.yml`"""
    stages: list[Stage]
    """All stage definitions"""
    deploy_image: Optional[str] = None
    """The docker image to deploy"""

    @staticmethod
    def from_configuration(
        target: Target,
        run_properties: dict,
        config: dict,
        deploy_image: Optional[str] = None,
    ):
        return RunProperties(
            details=RunContext.from_configuration(run_properties["build"]["run"]),
            target=target,
            versioning=VersioningProperties.from_run_properties(run_properties),
            config=config,
            stages=[
                Stage(stage["name"], stage["icon"])
                for stage in run_properties["stages"]
            ],
            deploy_image=deploy_image,
        )

    @staticmethod
    def validate(properties: dict):
        schema = pkgutil.get_data(__name__, "../schema/run_properties.schema.yml")
        if schema:
            validate(properties, schema.decode("utf-8"))

    def to_stage(self, stage_name: str) -> Stage:
        stage_by_name = next(stage for stage in self.stages if stage.name == stage_name)
        if stage_by_name:
            return stage_by_name
        raise ValueError(f"Stage {stage_name} not found")

    def selected_stage(self, selected_stage_name: Optional[str]):
        return self.to_stage(selected_stage_name) if selected_stage_name else None

"""Module to initiate run properties"""

import pkgutil
from typing import Optional

from ..project import load_project
from ..stages.discovery import find_projects
from ..steps.models import RunProperties
from ..validation import validate


def validate_run_properties(properties: dict):
    build_dict = pkgutil.get_data(__name__, "../schema/run_properties.schema.yml")

    if build_dict:
        validate(properties, build_dict.decode("utf-8"))


def construct_run_properties(
    config: dict,
    properties: dict,
    tag: Optional[str] = None,
    deploy_image: Optional[str] = None,
) -> RunProperties:
    validate_run_properties(properties)

    all_projects = set(
        map(
            lambda p: load_project(
                project_path=p, validate_project_yaml=False, log=True
            ),
            find_projects(),
        )
    )

    return RunProperties.from_configuration(
        run_properties=properties,
        config=config,
        all_projects=all_projects,
        cli_tag=tag or properties["build"]["versioning"].get("tag"),
        deploy_image=deploy_image,
    )

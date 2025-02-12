""" This module is called on to create a helm chart for your project and install it during the `mpyl.steps.deploy`
step.
"""

import shutil
from logging import Logger
from pathlib import Path
from typing import Optional

import yaml

from .resources import to_yaml, CustomResourceDefinition
from ...output import Output
from ....utilities.subprocess import custom_check_output


def template_chart(
    logger: Logger,
    release_name: str,
    namespace: Optional[str],
    chart_name: str,
    chart_version: str,
    values_path: Path,
    output_path: Path,
) -> Output:
    cmd = (
        f"helm template {release_name} "
        f"{chart_name} "
        f"--version {chart_version} "
        f"-f {values_path} "
        f"--output-dir {output_path}"
    )

    if namespace:
        cmd += f" --namespace {namespace}"

    return custom_check_output(logger, cmd)


def write_chart(
    chart: dict[str, CustomResourceDefinition],
    chart_path: Path,
    values: dict[str, str],
) -> None:
    shutil.rmtree(chart_path, ignore_errors=True)
    template_path = chart_path / Path("templates")
    template_path.mkdir(parents=True, exist_ok=True)

    with open(chart_path / Path("values.yaml"), mode="w+", encoding="utf-8") as file:
        if values == {}:
            file.write(
                "# This file is intentionally left empty. All values in /templates have been pre-interpolated"
            )
        else:
            file.write(yaml.dump(values))

    my_dictionary: dict[str, str] = dict(
        map(lambda item: (item[0], to_yaml(item[1])), chart.items())
    )

    for name, template_content in my_dictionary.items():
        name_with_extension = name + ".yaml"
        with open(
            template_path / name_with_extension, mode="w+", encoding="utf-8"
        ) as file:
            file.write(template_content)


def write_helm_chart(
    logger: Logger,
    chart: dict[str, CustomResourceDefinition],
    target_path: Path,
) -> Path:
    chart_path = Path(target_path) / "chart"
    logger.info(f"Writing HELM chart to {chart_path}")
    write_chart(chart, chart_path, values={})
    return chart_path

""" This module is called on to create a helm chart for your project and install it during the `mpyl.steps.deploy`
step.
"""

import shutil
from logging import Logger
from pathlib import Path

import yaml

from .resources import to_yaml, CustomResourceDefinition
from ...output import Output
from ....utilities.subprocess import custom_check_output


def add_repo(logger: Logger, repo_name: str, repo_url: str) -> Output:
    cmd_add = f"helm repo add {repo_name} {repo_url}"
    return custom_check_output(logger, cmd_add)


def update_repo(logger: Logger) -> Output:
    return custom_check_output(logger, "helm repo update")


def template_chart(
    logger: Logger,
    release_name: str,
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


def __execute_install_cmd(
    logger: Logger,
    chart_name: str,
    name_space: str,
    kube_context: str,
    additional_args: str = "",
) -> Output:
    cmd = f"helm upgrade -i {chart_name} -n {name_space} --kube-context {kube_context} {additional_args}"

    return custom_check_output(logger, cmd)


def install_chart_with_values(
    logger: Logger,
    values_path: Path,
    release_name: str,
    chart_version: str,
    chart_name: str,
    namespace: str,
    kube_context: str,
) -> Output:
    values_path_arg = f"-f {values_path} --version {chart_version} {chart_name}"
    return __execute_install_cmd(
        logger,
        release_name,
        namespace,
        kube_context,
        additional_args=values_path_arg,
    )

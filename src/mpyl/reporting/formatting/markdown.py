"""
Markdown run result formatters
"""

import operator
from typing import Optional

from ...project import Stage
from ...project_execution import ProjectExecution
from ...steps.executor import ExecutionResult
from ...steps.run import RunResult


def wrap_project_name(
    project_execution: ProjectExecution, result: list[ExecutionResult]
):
    project_name = project_execution.name
    encapsulation = "_"
    found_result = next((r for r in result if r.project.name == project_name), None)
    if found_result:
        encapsulation = "*" if found_result.output.success else "~~"

    return f"{encapsulation}{project_name}{' (cached)' if project_execution.cached else ''}{encapsulation}"


def __to_oneliner(
    result: list[ExecutionResult], plan: Optional[set[ProjectExecution]]
) -> str:
    project_names: list[str] = []
    if plan:
        sorted_plans = sorted(plan, key=operator.attrgetter("name"))
        for project_execution in sorted_plans:
            project_names.append(wrap_project_name(project_execution, result))
    else:
        project_names = list(map(lambda r: f"_{r.project.name}_", result))

    return f'{", ".join(project_names)}'


def markdown_for_stage(run_result: RunResult, stage: Stage):
    step_results: list[ExecutionResult] = run_result.results_for_stage(stage)
    plan = run_result.run_plan.get_projects_for_stage(stage)
    if not step_results and not plan:
        return ""

    return f"{stage.icon} {stage.name.capitalize()}:  \n{__to_oneliner(step_results, plan)}  \n"


def run_result_to_markdown(run_result: RunResult) -> str:
    status_line: str = f"{run_result.status_line}  \n"
    return status_line + execution_plan_as_markdown(run_result)


def execution_plan_as_markdown(run_result: RunResult):
    result = ""
    exception = run_result.exception
    if exception:
        result += f"For _{exception.step}_ on _{exception.project_name}_ at stage _{exception.stage}_ \n"
        result += f"\n\n{exception}\n\n"
    elif run_result.failed_results:
        failed_projects = ", ".join(
            set(failed.project.name for failed in run_result.failed_results)
        )
        failed_stage = next(failed.stage.name for failed in run_result.failed_results)
        failed_outputs = ". \n\n".join(
            [failed.output.message for failed in run_result.failed_results]
        )
        result += f"For _{failed_projects}_ at stage _{failed_stage}_ \n"
        result += f"\n\n{failed_outputs}\n\n"
    for stage in run_result.run_properties.stages:
        result += markdown_for_stage(run_result, stage)
    if result == "":
        return "🤷 Nothing to do"
    return result

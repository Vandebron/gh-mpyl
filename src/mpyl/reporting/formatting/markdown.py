"""
Markdown run result formatters
"""

import operator
from typing import Optional

from ...project_execution import ProjectExecution
from ...steps.executor import ExecutionResult


def wrap_project_name(
    project_execution: ProjectExecution, result: list[ExecutionResult]
):
    project_name = project_execution.name
    encapsulation = "_"
    found_result = next((r for r in result if r.project.name == project_name), None)
    if found_result:
        encapsulation = "*" if found_result.output.success else "~~"

    return f"{encapsulation}{project_name}{' (cached)' if project_execution.cached else ''}{encapsulation}"


def to_oneliner(
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

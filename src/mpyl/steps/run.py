"""
Accumulate `mpyl.steps.run.RunResult` from executed `mpyl.steps.step.Step`
"""

import pickle
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .executor import ExecutionResult, ExecutionException
from .models import RunProperties
from ..constants import RUN_ARTIFACTS_FOLDER
from ..project import Stage
from ..reporting.formatting.markdown import to_oneliner
from ..run_plan import RunPlan


@dataclass(frozen=True)
class RunResult:
    _result: Optional[ExecutionResult]
    _exception: Optional[ExecutionException]

    @staticmethod
    def with_result(execution_result: ExecutionResult):
        return RunResult(_result=execution_result, _exception=None)

    @staticmethod
    def with_exception(exception: ExecutionException):
        return RunResult(_result=None, _exception=exception)

    @property
    def status_line(self) -> str:
        if self._exception:
            return "❗ Failed with exception"
        if not self.has_results:
            return "🦥 Nothing to do"
        if self.is_success:
            return "✅ Successful"

        return "❌ Failed"

    @property
    def is_success(self):
        return self._result.output.success if self._result else False

    @property
    def has_results(self):
        return True if self._result else False

    @property
    def failed_result(self) -> Optional[ExecutionResult]:
        return self._result if self._result and not self._result.output.success else None

    def result_for_stage(self, stage: Stage) -> Optional[ExecutionResult]:
        return self._result if self._result and self._result.stage == stage else None

    def write_to_pickle_file(self):
        Path(RUN_ARTIFACTS_FOLDER).mkdir(parents=True, exist_ok=True)
        run_result_file = (
                Path(RUN_ARTIFACTS_FOLDER) / f"run_result-{uuid.uuid4()}.pickle"
        )
        with open(run_result_file, "wb") as file:
            pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)


    def to_markdown(self, run_properties: RunProperties, run_plan: RunPlan) -> str:
        status_line: str = f"{self.status_line}  \n"
        return status_line + self._to_markdown(run_properties, run_plan)


    def _to_markdown(self, run_properties: RunProperties, run_plan: RunPlan) -> str:
        result = ""
        if self._exception:
            result += f"For _{self._exception.step}_ on _{self._exception.project_name}_ at stage _{self._exception.stage}_ \n"
            result += f"\n\n{self._exception}\n\n"

        elif self.failed_results:
            failed_projects = ", ".join(
                set(failed.project.name for failed in self.failed_results)
            )
            failed_stage = next(failed.stage.name for failed in self.failed_results)
            failed_outputs = ". \n\n".join(
                [failed.output.message for failed in self.failed_results]
            )
            result += f"For _{failed_projects}_ at stage _{failed_stage}_ \n"
            result += f"\n\n{failed_outputs}\n\n"

        for stage in run_properties.stages:
            result += self._markdown_for_stage(self, run_plan, stage)

        if result == "":
            return "🤷 Nothing to do"

        return result


    def _markdown_for_stage(self, run_plan: RunPlan, stage: Stage):
        step_results: list[ExecutionResult] = self.results_for_stage(stage)
        plan = run_plan.get_projects_for_stage(stage)
        if not step_results and not plan:
            return ""

        return f"{stage.display_string()}:  \n{to_oneliner(step_results, plan)}  \n"

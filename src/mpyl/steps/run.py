"""
Accumulate `mpyl.steps.run.RunResult` from executed `mpyl.steps.step.Step`
"""

import pickle
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .executor import ExecutionException
from .execution_result import ExecutionResult
from ..constants import RUN_ARTIFACTS_FOLDER
from ..project import Stage
from ..run_plan import RunPlan


@dataclass(frozen=True)
class RunResult:
    _run_plan: RunPlan
    _result: Optional[ExecutionResult]
    _exception: Optional[ExecutionException]

    @staticmethod
    def with_result(run_plan: RunPlan, execution_result: ExecutionResult):
        return RunResult(_run_plan=run_plan, _result=execution_result, _exception=None)

    @staticmethod
    def with_exception(run_plan: RunPlan, exception: ExecutionException):
        return RunResult(_run_plan=run_plan, _result=None, _exception=exception)

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
        return bool(self._result)

    @property
    def failed_result(self) -> Optional[ExecutionResult]:
        return (
            self._result if self._result and not self._result.output.success else None
        )

    def result_for_stage(self, stage: Stage) -> Optional[ExecutionResult]:
        return self._result if self._result and self._result.stage == stage else None

    def write_to_pickle_file(self):
        Path(RUN_ARTIFACTS_FOLDER).mkdir(parents=True, exist_ok=True)
        run_result_file = (
            Path(RUN_ARTIFACTS_FOLDER) / f"run_result-{uuid.uuid4()}.pickle"
        )
        with open(run_result_file, "wb") as file:
            pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)

    def to_markdown(self) -> str:
        status_line = f"{self.status_line}  \n"
        return status_line + self._to_markdown()

    def _to_markdown(self) -> str:
        result = ""
        if self._exception:
            result += (
                f"For _{self._exception.step}_ on _{self._exception.project_name}_"
                f" at stage _{self._exception.stage}_ \n"
            )
            result += f"\n\n{self._exception}\n\n"

        elif self.failed_result:
            result += f"For _{self.failed_result.project.name}_ at stage _{self.failed_result.stage.name}_ \n"
            result += f"\n\n{self.failed_result.output.message}\n\n"

        result += self._run_plan.to_markdown(self._result)

        return "🤷 Nothing to do" if result == "" else result

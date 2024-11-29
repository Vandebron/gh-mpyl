"""
Accumulate `mpyl.steps.run.RunResult` from executed `mpyl.steps.step.Step`
"""

import pickle
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .executor import ExecutionException, ExecutionResult
from ..constants import RUN_ARTIFACTS_FOLDER
from ..project import Stage


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
        lines = []
        if self._exception:
            lines.append(
                f"❗ Project _{self._exception.project_name}_ at stage _{self._exception.stage}_"
            )
            lines.append(self._exception.message)

        elif self.failed_result:
            lines.append(
                f"❌ Project _{self.failed_result.project.name}_ at stage _{self.failed_result.stage.name}_"
            )
            lines.append(self.failed_result.output.message)

        elif self._result:
            lines.append(
                f"✅ Project _{self._result.project.name}_ at stage _{self._result.stage.name}_"
            )

        else:
            lines.append("🤷 Nothing to do")

        return "  \n".join(lines)

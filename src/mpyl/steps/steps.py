""" Entry point of MPyL. Loads all available Step implementations and triggers their execution based on the specified
Project and Stage.
"""

import pkgutil
from dataclasses import dataclass
from datetime import datetime
from logging import Logger
from typing import Optional

from ruamel.yaml import YAML  # type: ignore

from . import Step
from .collection import StepsCollection
from .models import Output, Input, RunProperties
from ..project import Project
from ..project import Stage
from ..project_execution import ProjectExecution
from ..run_plan import RunPlan
from ..validation import validate

yaml = YAML()


class ExecutionException(Exception):
    """Exception thrown when a step execution fails."""

    def __init__(self, project_name: str, executor: str, stage: str, message: str):
        self.project_name = project_name
        self.executor = executor
        self.stage = stage
        self.message = message
        super().__init__(self.message)

    def __reduce__(self):
        return ExecutionException, (
            self.project_name,
            self.executor,
            self.stage,
            self.message,
        )


@dataclass(frozen=True)
class StepResult:
    stage: Stage
    project: Project
    output: Output
    timestamp: datetime = datetime.now()


class Steps:
    """Executor of individual steps within a pipeline."""

    _logger: Logger
    _properties: RunProperties
    _run_plan: RunPlan
    _steps_collection: StepsCollection

    def __init__(
        self,
        logger: Logger,
        properties: RunProperties,
        steps_collection: Optional[StepsCollection] = None,
    ) -> None:
        self._logger = logger
        self._properties = properties
        self._steps_collection = steps_collection or StepsCollection(logger)

        schema_dict = pkgutil.get_data(__name__, "../schema/mpyl_config.schema.yml")

        if schema_dict:
            validate(properties.config, schema_dict.decode("utf-8"))

    def _execute(
        self,
        executor: Step,
        project_execution: ProjectExecution,
        properties: RunProperties,
    ) -> Output:
        self._logger.info(
            f"Executing {executor.meta.name} for '{project_execution.name}'"
        )
        result = executor.execute(
            Input(
                project_execution=project_execution,
                run_properties=properties,
            )
        )
        if result.success:
            self._logger.info(
                f"Execution of {executor.meta.name} succeeded for '{project_execution.name}' with outcome '{result.message}'"  # pylint: disable=line-too-long
            )
        else:
            self._logger.warning(
                f"Execution of {executor.meta.name} failed for '{project_execution.name}' with outcome '{result.message}'"  # pylint: disable=line-too-long
            )
        return result

    def _execute_after_(
        self,
        main_result: Output,
        step: Step,
        project_execution: ProjectExecution,
        stage: Stage,
    ) -> Output:
        after_result = self._execute(
            executor=step,
            project_execution=project_execution,
            properties=self._properties,
        )

        after_result.write(project_execution.project.target_path, stage.name)

        return Output(
            success=main_result.success and after_result.success,
            message=f"{main_result.message}\n{after_result.message}",
        )

    def _validate_project_against_config(self, project: Project) -> Optional[Output]:
        allowed_maintainers = set(
            self._properties.config.get("project", {}).get("allowedMaintainers", [])
        )
        not_allowed = set(project.maintainer).difference(allowed_maintainers)
        if not_allowed:
            return Output(
                success=False,
                message=f"Maintainer(s) '{', '.join(not_allowed)}' not defined in config",
            )
        return None

    def _execute_stage(
        self, stage: Stage, project_execution: ProjectExecution
    ) -> Output:
        step_name = project_execution.project.stages.for_stage(stage.name)
        if step_name is None:
            return Output(
                success=False,
                message=f"Stage '{stage.name}' not defined on project '{project_execution.name}'",
            )

        invalid_maintainers = self._validate_project_against_config(
            project_execution.project
        )
        if invalid_maintainers:
            return invalid_maintainers

        executor: Optional[Step] = self._steps_collection.get_executor(stage, step_name)
        if not executor:
            self._logger.error(
                f"No executor found for {step_name} in stage {stage.name}"
            )

            return Output(
                success=False,
                message=f"Executor '{step_name}' for '{stage.name}' not known or registered",
            )

        try:
            self._logger.info(
                f"Executing {stage.name} {stage.icon} for {project_execution.name}"
            )
            if executor.before:
                before_result = self._execute(
                    executor=executor.before,
                    project_execution=project_execution,
                    properties=self._properties,
                )
                if not before_result.success:
                    return before_result

            result = self._execute(
                executor=executor,
                project_execution=project_execution,
                properties=self._properties,
            )
            result.write(project_execution.project.target_path, stage.name)

            if executor.after and result.success:
                return self._execute_after_(
                    result, executor.after, project_execution, stage
                )

            return result
        except Exception as exc:
            message = str(exc)
            self._logger.warning(
                f"Execution of '{executor.meta.name}' for project '{project_execution.name}' in stage {stage.name} "
                f"failed with exception: {message}",
                exc_info=True,
            )
            raise ExecutionException(
                project_execution.name, executor.meta.name, stage.name, message
            ) from exc

    def execute(self, stage: str, project_execution: ProjectExecution) -> StepResult:
        """
        :param stage: the stage to execute
        :param project_execution: the project execution information
        :return: StepResult
        :raise ExecutionException
        """
        stage_object = self._properties.to_stage(stage)
        step_output = self._execute_stage(
            stage=stage_object, project_execution=project_execution
        )
        return StepResult(
            stage=stage_object, project=project_execution.project, output=step_output
        )

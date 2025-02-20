""" Entry point of MPyL. Loads all available Step implementations and triggers their execution based on the specified
Project and Stage.
"""

import pkgutil
from dataclasses import dataclass
from datetime import datetime
from logging import Logger
from typing import Optional

from .collection import StepsCollection
from .input import Input
from .models import RunProperties
from .output import Output
from .step import Step
from ..project import Project, Stage
from ..run_plan import RunPlan
from ..validation import validate


class ExecutionException(Exception):
    """Exception thrown when a step execution fails."""

    def __init__(self, project_name: str, executor: str, stage: str, message: str):
        self.project_name = project_name
        self.step = executor
        self.stage = stage
        self.message = message
        super().__init__(self.message)

    def __reduce__(self):
        return ExecutionException, (
            self.project_name,
            self.step,
            self.stage,
            self.message,
        )


@dataclass(frozen=True)
class ExecutionResult:
    stage: Stage
    project: Project
    output: Output
    timestamp: datetime = datetime.now()


class Executor:
    """Executor of individual steps within a pipeline."""

    _logger: Logger
    _run_properties: RunProperties
    _run_plan: RunPlan
    _steps_collection: StepsCollection

    def __init__(
        self,
        logger: Logger,
        run_properties: RunProperties,
        run_plan: RunPlan,
        steps_collection: Optional[StepsCollection] = None,
    ) -> None:
        self._logger = logger
        self._run_properties = run_properties
        self._run_plan = run_plan
        self._steps_collection = steps_collection or StepsCollection(logger)

        schema_dict = pkgutil.get_data(__name__, "../schema/mpyl_config.schema.yml")

        if schema_dict:
            validate(run_properties.config, schema_dict.decode("utf-8"))

    def _execute(
        self,
        step: Step,
        project: Project,
    ) -> Output:
        self._logger.info(f"Executing {step.meta.name} for '{project.name}'")
        result = step.execute(
            Input(
                project=project,
                run_properties=self._run_properties,
                run_plan=self._run_plan,
            )
        )
        if result.success:
            self._logger.info(
                f"Execution of {step.meta.name} succeeded for '{project.name}' with outcome '{result.message}'"  # pylint: disable=line-too-long
            )
        else:
            self._logger.warning(
                f"Execution of {step.meta.name} failed for '{project.name}' with outcome '{result.message}'"  # pylint: disable=line-too-long
            )
        return result

    def _execute_after_(
        self,
        main_result: Output,
        step: Step,
        project: Project,
        stage: Stage,
    ) -> Output:
        after_result = self._execute(
            step=step,
            project=project,
        )

        after_result.write(project.target_path, stage.name)

        return Output(
            success=main_result.success and after_result.success,
            message=f"{main_result.message}\n{after_result.message}",
        )

    def _validate_project_against_config(self, project: Project) -> Optional[Output]:
        allowed_maintainers = set(
            self._run_properties.config.get("project", {}).get("allowedMaintainers", [])
        )
        not_allowed = set(project.maintainer).difference(allowed_maintainers)
        if not_allowed:
            return Output(
                success=False,
                message=f"Maintainer(s) '{', '.join(not_allowed)}' not defined in config",
            )
        return None

    def _execute_stage(self, stage: Stage, project: Project) -> Output:
        step_name = project.stages.for_stage(stage.name)
        if step_name is None:
            return Output(
                success=False,
                message=f"Stage '{stage.name}' not defined on project '{project.name}'",
            )

        invalid_maintainers = self._validate_project_against_config(project)
        if invalid_maintainers:
            return invalid_maintainers

        step: Optional[Step] = self._steps_collection.get_step(stage, step_name)
        if not step:
            self._logger.error(
                f"No step found with name '{step_name}' in stage {stage.name}"
            )

            return Output(
                success=False,
                message=f"Step '{step_name}' for '{stage.name}' not known or registered",
            )

        try:
            self._logger.info(f"Executing {stage.to_markdown()} for {project.name}")
            if step.before:
                before_result = self._execute(
                    step=step.before,
                    project=project,
                )
                if not before_result.success:
                    return before_result

            result = self._execute(
                step=step,
                project=project,
            )
            result.write(project.target_path, stage.name)

            if step.after and result.success:
                return self._execute_after_(result, step.after, project, stage)

            return result
        except Exception as exc:
            message = str(exc)
            self._logger.warning(
                f"Execution of '{step.meta.name}' for project '{project.name}' in stage {stage.name} "
                f"failed with exception: {message}",
                exc_info=True,
            )
            raise ExecutionException(
                project.name, step.meta.name, stage.name, message
            ) from exc

    def execute(self, stage: Stage, project: Project) -> ExecutionResult:
        """
        :param stage: the stage to execute
        :param project: the project to execute
        :return: StepResult
        :raise ExecutionException
        """
        step_output = self._execute_stage(stage=stage, project=project)
        return ExecutionResult(
            stage=stage,
            project=project,
            output=step_output,
        )

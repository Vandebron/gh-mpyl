"""Simple MPyL build runner"""

import logging

from .run_plan import RunPlan
from .steps import deploy
from .steps.collection import StepsCollection
from .steps.executor import ExecutionException, ExecutionResult, Executor
from .steps.models import RunProperties
from .steps.output import Output
from .steps.run import RunResult

FORMAT = "%(name)s  %(message)s"


def run_deploy_stage(
    logger: logging.Logger,
    run_properties: RunProperties,
    run_plan: RunPlan,
    project_name_to_run: str,
) -> RunResult:
    try:
        stage = run_properties.to_stage(deploy.STAGE_NAME)
        project_execution = run_plan.get_project_to_execute(
            stage_name=deploy.STAGE_NAME, project_name=project_name_to_run
        )

        executor = Executor(
            logger=logger,
            run_properties=run_properties,
            run_plan=run_plan,
            steps_collection=StepsCollection(logger=logger),
        )

        if project_execution.cached:
            logger.info(
                f"Skipping {project_execution.name} for stage {stage.name} because it is cached"
            )
            execution_result = ExecutionResult(
                stage=stage,
                project=project_execution,
                output=Output(success=True, message="This step was cached"),
            )
        else:
            execution_result = executor.execute(stage, project_execution)

        if not execution_result.output.success:
            logger.warning(f"{stage} failed for {project_execution.name}")

        return RunResult.with_result(execution_result)

    except ExecutionException as exc:
        return RunResult.with_exception(exc)

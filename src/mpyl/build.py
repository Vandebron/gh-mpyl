"""Simple MPyL build runner"""

import datetime
import logging
import time

from jsonschema import ValidationError
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown

from .run_plan import RunPlan
from .reporting.formatting.markdown import run_result_to_markdown
from .steps import deploy
from .steps.collection import StepsCollection
from .steps.models import Output, RunProperties, ConsoleProperties
from .steps.run import RunResult
from .steps.steps import ExecutionException, StepResult, Steps


FORMAT = "%(name)s  %(message)s"


def run_mpyl(
    console_properties: ConsoleProperties,
    run_properties: RunProperties,
    run_plan: RunPlan,
) -> RunResult:
    # why does this create another Console when we already have one created in cli/build.py ?
    console = Console(
        markup=False,
        width=console_properties.width,
        no_color=False,
        log_path=False,
        color_system="256",
    )
    logging.raiseExceptions = False
    log_level = console_properties.log_level
    logging.basicConfig(
        level=log_level,
        format=FORMAT,
        datefmt="[%X]",
        handlers=[RichHandler(markup=False, console=console, show_path=False)],
    )
    print(f"Log level is set to {log_level}")
    logger = logging.getLogger("mpyl")
    start_time = time.time()
    try:
        run_result = RunResult(run_properties=run_properties, run_plan=run_plan)

        if not run_result.has_projects_to_run(include_cached_projects=False):
            logger.info("Nothing to do. Exiting..")
            return run_result

        logger.info("Run plan:")
        console.print(Markdown(f"\n\n{run_result.status_line}  \n"))
        run_plan.print_markdown(console, run_properties.stages)

        try:
            steps = Steps(
                logger=logger,
                properties=run_properties,
                steps_collection=StepsCollection(logger=logger),
            )

            run_result = run_build(
                logger=logger, accumulator=run_result, executor=steps
            )
        except ValidationError as exc:
            console.log(
                f'Schema validation failed {exc.message} at `{".".join(map(str, exc.path))}`'
            )
            raise exc
        except ExecutionException as exc:
            run_result.exception = exc
            console.log(f"Exception during build execution: {exc}")
            console.print_exception()

        console.log(
            f"Completed in {datetime.timedelta(seconds=time.time() - start_time)}"
        )
        console.print(Markdown(run_result_to_markdown(run_result)))
        return run_result

    except Exception as exc:
        console.log(f"Unexpected exception: {exc}")
        console.print_exception()
        raise exc


def run_build(logger: logging.Logger, accumulator: RunResult, executor: Steps):
    try:
        for stage, project_executions in accumulator.run_plan.selected_plan.items():
            for project_execution in project_executions:
                if project_execution.cached:
                    logger.info(
                        f"Skipping {project_execution.name} for stage {stage.name} because it is cached"
                    )
                    result = StepResult(
                        stage=stage,
                        project=project_execution.project,
                        output=Output(success=True, message="This step was cached"),
                    )
                else:
                    result = executor.execute(stage.name, project_execution)
                accumulator.append(result)

                if not result.output.success and stage.name == deploy.STAGE_NAME:
                    logger.warning(f"{stage} failed for {project_execution.name}")
                    return accumulator

            if accumulator.failed_results:
                logger.warning(f"One of the builds failed at Stage {stage.name}")
                return accumulator
        return accumulator
    except ExecutionException as exc:
        accumulator.exception = exc
        return accumulator

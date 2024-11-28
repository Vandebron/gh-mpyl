"""Simple MPyL build runner"""

import datetime
import logging
import time

from jsonschema import ValidationError
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown

from .run_plan import RunPlan
from .steps import deploy
from .steps.collection import StepsCollection
from .steps.executor import ExecutionException, Executor
from .steps.execution_result import ExecutionResult
from .steps.models import RunProperties, ConsoleProperties
from .steps.output import Output
from .steps.run import RunResult

FORMAT = "%(name)s  %(message)s"


def run_deploy_stage(
    console_properties: ConsoleProperties,
    run_properties: RunProperties,
    project_name_to_run: str,
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
        run_plan = RunPlan.load_from_pickle_file()
        console.print(Markdown("**Execution plan:**  \n"))
        console.print(Markdown(run_plan.to_markdown()))

        run_result = _run_deploy_stage(
            logger=logger,
            console=console,
            run_properties=run_properties,
            run_plan=run_plan,
            project_name_to_run=project_name_to_run,
        )

        console.log(
            f"Completed in {datetime.timedelta(seconds=time.time() - start_time)}"
        )
        console.print(Markdown(run_result.to_markdown()))
        return run_result
    except Exception as exc:
        console.log(f"Unexpected exception: {exc}")
        console.print_exception()
        raise exc


def _run_deploy_stage(
    logger: logging.Logger,
    console: Console,
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

        return RunResult.with_result(run_plan, execution_result)

    except ValidationError as exc:
        console.log(
            f'Schema validation failed {exc.message} at `{".".join(map(str, exc.path))}`'
        )
        raise exc

    except ExecutionException as exc:
        return RunResult.with_exception(run_plan, exc)

"""A dummy deploy step."""

from logging import Logger

from . import STAGE_NAME
from ..input import Input
from ..output import Output
from ..step import Step, Meta


class DeployEcho(Step):
    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Echo Deploy",
                description="Dummy deploy step to test the framework",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
        )

    def execute(self, step_input: Input) -> Output:
        self._logger.info(f"Deploying project {step_input.project.name}")
        return Output(
            success=True,
            message=f"Deployed project {step_input.project.name}",
        )

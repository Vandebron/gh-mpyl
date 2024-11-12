""" Dummy build step to test the framework. """

from logging import Logger

from .. import Step, Meta
from ..models import Input, Output, ArtifactType
from . import STAGE_NAME


class BuildEcho(Step):
    def __init__(self, logger: Logger) -> None:
        super().__init__(
            logger,
            Meta(
                name="Echo Build",
                description="Dummy build step to test the framework",
                version="0.0.1",
                stage=STAGE_NAME,
            ),
            produced_artifact=ArtifactType.NONE,
        )

    def execute(self, step_input: Input) -> Output:
        self._logger.info(f"Building project {step_input.project_execution.name}")
        return Output(
            success=True,
            message=f"Built {step_input.project_execution.name}",
            produced_artifact=None,
        )

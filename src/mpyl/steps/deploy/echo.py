"""A dummy deploy step, which produces `mpyl.steps.models.ArtifactType.NONE`."""

from logging import Logger

from . import STAGE_NAME
from .. import Step, Meta
from ..models import Input, Output, ArtifactType


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
            ArtifactType.NONE,
        )

    def execute(self, step_input: Input) -> Output:
        self._logger.info(f"Deploying project {step_input.project_execution.name}")
        return Output(
            success=True,
            message=f"Deployed project {step_input.project_execution.name}",
            produced_artifact=None,
        )

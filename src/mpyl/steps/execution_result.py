""" The result of executing a Step for a specific Project in a certain Stage.
"""

from dataclasses import dataclass
from datetime import datetime

from .output import Output
from ..project import Stage
from ..project_execution import ProjectExecution


@dataclass(frozen=True)
class ExecutionResult:
    stage: Stage
    project: ProjectExecution
    output: Output
    timestamp: datetime = datetime.now()

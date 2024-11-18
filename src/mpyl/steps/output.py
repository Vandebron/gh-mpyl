"""Output produced by a step execution."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ruamel.yaml import yaml_object, YAML


yaml = YAML()


@yaml_object(yaml)
@dataclass(frozen=False)  # yaml_object classes can't be frozen
class Output:
    success: bool
    message: str
    hash: Optional[str] = None

    @staticmethod
    def path(target_path: Path, stage: str):
        return Path(target_path, f"{stage}.yml")

    def write(self, target_path: Path, stage: str):
        Path(target_path).mkdir(parents=True, exist_ok=True)
        with Output.path(target_path, stage).open(mode="w+", encoding="utf-8") as file:
            yaml.dump(self, file)

    @staticmethod
    def try_read(target_path: Path, stage: str):
        path = Output.path(target_path, stage)
        if path.exists():
            with open(path, encoding="utf-8") as file:
                return yaml.load(file)
        return None

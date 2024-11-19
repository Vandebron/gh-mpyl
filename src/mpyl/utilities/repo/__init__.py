"""
Represents the files modified in this unit of change (pull request, etc).
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Changeset:
    sha: str
    """Git hash for this revision"""
    _files_touched: dict[str, str]

    def files_touched(self, status: Optional[set[str]] = None):
        if not status or len(status) == 0:
            return set(self._files_touched.keys())

        return {file for file, s in self._files_touched.items() if s in status}

    @staticmethod
    def from_files(logger: logging.Logger, sha: str, changed_files_path: Path):
        logger.debug(
            f"Creating Changeset based on changed files in {changed_files_path}"
        )
        changed_files = {}

        def add_changed_files(operation: str, change_type: str):
            path = changed_files_path / f"{operation}_files.json"
            if path.is_file():
                with open(path, encoding="utf-8") as file:
                    files = json.load(file)
                    for changed in files:
                        changed_files[changed] = change_type
            else:
                raise ValueError(
                    f"Unable to create Changeset due to missing file {path}"
                )

        add_changed_files("added", "A")
        add_changed_files("copied", "C")
        add_changed_files("deleted", "D")
        add_changed_files("modified", "M")
        add_changed_files("renamed", "R")

        return Changeset(sha=sha, _files_touched=changed_files)

"""
Represents the files modified in this unit of change (pull request, etc).
"""
import json
import logging
from dataclasses import dataclass
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
    def from_file(logger: logging.Logger, sha: str, changed_files_path: str):
        with open(changed_files_path, encoding="utf-8") as file:
            logger.debug(
                f"Creating Changeset based on changed files in {changed_files_path}"
            )
            changed_files = json.load(file)
            return Changeset(sha=sha, _files_touched=changed_files)

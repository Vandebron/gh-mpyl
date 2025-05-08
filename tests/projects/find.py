""" Loads all projects inside a repository. """

from pathlib import Path
from typing import Optional

from src.mpyl.plan.discovery import find_projects
from src.mpyl.project import Project, load_project


def load_projects(paths: Optional[list[Path]] = None) -> set[Project]:
    if not paths:
        paths = find_projects()
    return set(map(lambda p: load_project(p, validate_project_yaml=False), paths))

import traceback

import jsonschema

from src.mpyl.project import load_project
from src.mpyl.plan.discovery import find_projects


class TestProjectLoad:
    def test_load_all_projects(self):
        for project in find_projects():
            try:
                load_project(project, validate_project_yaml=True)
            except jsonschema.exceptions.ValidationError as exc:
                traceback.print_exc()
                assert exc == project

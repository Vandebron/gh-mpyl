import traceback

import jsonschema

from src.mpyl.project import load_project
from src.mpyl.projects import ProjectWithDependents
from src.mpyl.plan.discovery import find_projects
from tests.projects.find import load_projects, find_dependencies


class TestProjectLoad:
    def test_load_all_projects(self):
        for project in find_projects():
            try:
                load_project(project, validate_project_yaml=True)
            except jsonschema.exceptions.ValidationError as exc:
                traceback.print_exc()
                assert exc == project

    def test_load_all_project_dependencies(self):
        projects = load_projects()
        dependencies = list(map(lambda p: find_dependencies(p, projects), projects))
        deps: dict[str, ProjectWithDependents] = dict(
            map(lambda d: (d.name, d), dependencies)
        )

        assert len(deps["job"].dependent_projects) == 1
        assert len(deps["sbtservice"].dependent_projects) == 0

import re

from src.mpyl.cli import create_console_logger
from tests.cli.commands import invoke, config_path, resource_path
from tests.test_resources.test_data import assert_roundtrip


class TestProjectsCli:
    def test_projects_lint_output(self):
        result = invoke(["projects", "-c", str(config_path), "lint"])
        assert result  # Hard to assert details since it depends on the changes in the current branch

    def test_projects_lint_all_output(self):
        result = invoke(["projects", "-c", str(config_path), "lint"])
        assert re.match(
            r"(.|\n)*Validated .* projects\. .* valid, .* invalid\n\nChecking for duplicate project names: \n.*No duplicate project names found",  # pylint: disable=line-too-long
            result.output,
        )

    def test_list_projects_output(self):
        result = invoke(["projects", "-c", str(config_path), "list"])
        assert_roundtrip(resource_path / "list_projects_text.txt", result.output)

    def test_create_console(self):
        console = create_console_logger(show_path=False, max_width=135)
        assert console.width == 135

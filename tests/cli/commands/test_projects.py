import re

from tests.cli.commands import invoke, config_path


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

from click.testing import CliRunner
from src.mpyl import main_group, add_commands
from tests import root_test_path


class TestCli:
    resource_path = root_test_path / "cli" / "test_resources"
    config_path = root_test_path / "test_resources/mpyl_config.yml"
    run_properties_path = root_test_path / "test_resources/run_properties.yml"
    runner = CliRunner()
    add_commands()

    def _test_help_for_command(self, command: str):
        result = self.runner.invoke(
            main_group,
            args=[
                "plan",
                "-c",
                str(self.config_path),
                "-p",
                str(self.run_properties_path),
                command,
                "--help",
            ],
        )
        assert not result.exception

    def test_plan_create(self):
        self._test_help_for_command("create")

    def test_plan_print(self):
        self._test_help_for_command("print")

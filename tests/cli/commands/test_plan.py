from click.testing import CliRunner
from src.mpyl import main_group, add_commands
from tests import root_test_path


class TestCli:
    resource_path = root_test_path / "cli" / "test_resources"
    config_path = root_test_path / "test_resources/mpyl_config.yml"
    run_properties_path = root_test_path / "test_resources/run_properties.yml"
    runner = CliRunner()
    add_commands()

    def test_plan_create(self):
        result = self.runner.invoke(
            main_group,
            args=[
                "plan",
                "-c",
                str(self.config_path),
                "-p",
                str(self.run_properties_path),
                "create",
                "--help",
            ],
        )
        assert not result.exception

    def test_plan_print(self):
        result = self.runner.invoke(
            main_group,
            args=[
                "plan",
                "-c",
                str(self.config_path),
                "-p",
                str(self.run_properties_path),
                "print",
                "--help",
            ],
        )
        assert not result.exception

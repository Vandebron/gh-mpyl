from click.testing import CliRunner
from src.mpyl import add_commands, main_group
from tests import root_test_path

resource_path = root_test_path / "cli" / "test_resources"
config_path = root_test_path / "test_resources/mpyl_config.yml"
run_properties_path = root_test_path / "test_resources/run_properties.yml"


def invoke(args: list[str], env=None):
    if env is None:
        env = {}
    runner = CliRunner()
    add_commands()
    return runner.invoke(cli=main_group, args=list(args), env=env)

from tests.cli.commands import invoke, config_path, run_properties_path


class TestPlanCli:
    def test_plan_discover(self):
        result = invoke(
            [
                "plan",
                "-c",
                str(config_path),
                "-p",
                str(run_properties_path),
                "discover",
                "--help",
            ]
        )
        assert not result.exception

    def test_plan_print(self):
        result = invoke(
            [
                "plan",
                "-c",
                str(config_path),
                "-p",
                str(run_properties_path),
                "print",
                "--help",
            ]
        )
        assert not result.exception

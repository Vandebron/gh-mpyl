from pathlib import Path

from deepdiff import DeepDiff

from src.mpyl.projects.versioning import (
    upgrade_file,
    get_entry_upgrader_index,
    PROJECT_UPGRADERS,
    ProjectUpgraderOne8,
    ProjectUpgraderOne9,
    ProjectUpgraderOne10,
    load_for_roundtrip,
    pretty_print,
    Upgrader,
    CONFIG_UPGRADERS,
    PROPERTIES_UPGRADERS,
)
from src.mpyl.utilities.yaml import yaml_to_string
from tests.test_resources.test_data import assert_roundtrip
from tests.test_resources.test_data import root_test_path


class TestVersioning:
    test_resources_path = root_test_path / "test_resources"
    upgrades_path = test_resources_path / "upgrades"
    diff_path = upgrades_path / "diff"
    latest_release_file = "test_project_1_0_11.yml"

    @staticmethod
    def __roundtrip(
        source: Path, target: Path, upgraders: list[Upgrader], overwrite: bool = False
    ):
        upgraded = upgrade_file(source, upgraders)
        assert upgraded is not None
        assert_roundtrip(target, upgraded, overwrite)

    def test_get_upgrader_index(self):
        assert get_entry_upgrader_index("1.0.8", PROJECT_UPGRADERS) == 0
        assert get_entry_upgrader_index("1.0.9", PROJECT_UPGRADERS) == 1
        assert get_entry_upgrader_index("1.0.7", PROJECT_UPGRADERS) is None

    def test_first_upgrade(self):
        self.__roundtrip(
            self.upgrades_path / "test_project_1_0_8.yml",
            self.upgrades_path / "test_project_1_0_9.yml",
            [ProjectUpgraderOne8(), ProjectUpgraderOne9()],
        )

    def test_namespace_upgrade(self):
        self.__roundtrip(
            self.upgrades_path / "test_project_1_0_9.yml",
            self.upgrades_path / "test_project_1_0_10.yml",
            [ProjectUpgraderOne9(), ProjectUpgraderOne10()],
        )

    def test_full_upgrade(self):
        self.__roundtrip(
            self.upgrades_path / "test_project_1_0_8.yml",
            self.upgrades_path / self.latest_release_file,
            PROJECT_UPGRADERS,
        )

    def test_upgraded_should_match_test_config(self):
        assert_roundtrip(
            self.test_resources_path / "test_project.yml",
            (self.upgrades_path / self.latest_release_file).read_text("utf-8"),
        )

    def test_full_config_upgrade(self):
        self.__roundtrip(
            self.upgrades_path / "mpyl_config_base.yml",
            self.upgrades_path / "mpyl_config_upgraded.yml",
            CONFIG_UPGRADERS,
        )

    def test_full_properties_upgrade(self):
        self.__roundtrip(
            self.upgrades_path / "run_properties_base.yml",
            self.upgrades_path / "run_properties_upgraded.yml",
            PROPERTIES_UPGRADERS,
        )

    def test_diff_pretty_print(self):
        before, _ = load_for_roundtrip(self.diff_path / "before.yml")
        after, _ = load_for_roundtrip(self.diff_path / "after.yml")
        diff = DeepDiff(before, after, view="_delta")

        pretty_diff = pretty_print(diff)
        assert_roundtrip(self.diff_path / "diff.md", pretty_diff)

    # Padding around lists is removed. list: [ 'MPyL', 'Next' ] becomes  list: ['MPyL', 'Next']
    def test_formatting_roundtrip_removes(self):
        formatted = self.diff_path / "formatting_before.yml"
        formatting, yaml = load_for_roundtrip(formatted)
        assert_roundtrip(
            self.diff_path / "formatting_after.yml", yaml_to_string(formatting, yaml)
        )

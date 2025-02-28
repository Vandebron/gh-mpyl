from pathlib import Path

from src.mpyl.projects.versioning import (
    Upgrader,
    upgrade_file,
    get_entry_upgrader_index,
    load_for_roundtrip,
    ProjectUpgraderOne,
    ProjectUpgraderTwo,
)
from src.mpyl.utilities.yaml import yaml_to_string
from tests.test_resources.test_data import assert_roundtrip
from tests.test_resources.test_data import root_test_path


class TestVersioning:
    test_resources_path = root_test_path / "test_resources"
    upgrades_path = test_resources_path / "upgrades"
    diff_path = upgrades_path / "diff"
    latest_release_file = upgrades_path / "test_project_2" / "project.yml"

    @staticmethod
    def __roundtrip(source: Path, target: Path, overwrite: bool = False):
        upgraded = upgrade_file(source)
        assert upgraded is not None
        assert_roundtrip(target, upgraded, overwrite)

    def test_get_upgrader_index(self):
        upgraders: list[Upgrader] = [
            ProjectUpgraderOne(),
            ProjectUpgraderTwo(Path("")),
        ]

        assert get_entry_upgrader_index(1, upgraders) == 0
        assert get_entry_upgrader_index(2, upgraders) == 1
        assert get_entry_upgrader_index(0, upgraders) is None

    def test_full_upgrade(self):
        self.__roundtrip(
            self.upgrades_path / "test_project_1" / "project.yml",
            self.latest_release_file,
        )

    def test_upgraded_should_match_test_project(self):
        assert_roundtrip(
            self.latest_release_file,
            (
                self.test_resources_path
                / "test_projects"
                / "default"
                / "test_project.yml"
            ).read_text("utf-8"),
        )

    # Padding around lists is removed. list: [ 'MPyL', 'Next' ] becomes  list: ['MPyL', 'Next']
    def test_formatting_roundtrip_removes(self):
        formatted = self.diff_path / "formatting_before.yml"
        formatting, yaml = load_for_roundtrip(formatted)
        assert_roundtrip(
            self.diff_path / "formatting_after.yml", yaml_to_string(formatting, yaml)
        )

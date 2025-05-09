import os
from tempfile import TemporaryDirectory

from src.mpyl.backstage.backstage import generate_components


class TestBackstage:
    def test_backstage_component_generation(self):
        with TemporaryDirectory() as d:
            generate_components(d, "")
            assert "services.yaml" in os.listdir(d)
            assert "groups.yaml" in os.listdir(d)

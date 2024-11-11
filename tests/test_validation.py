import pkgutil

from src.mpyl import parse_config
from src.mpyl.validation import validate
from tests.test_resources.test_data import config_values, resource_path


class TestValidation:
    def test_validate_config_schema(self):
        schema_dict = pkgutil.get_data(
            __name__, "../src/mpyl/schema/mpyl_config.schema.yml"
        )
        assert schema_dict is not None

        validate(config_values, schema_dict.decode("utf-8"))

    def test_validate_config_schema_with_unknown_fields(self):
        schema_dict = pkgutil.get_data(
            __name__, "../src/mpyl/schema/mpyl_config.schema.yml"
        )
        assert schema_dict is not None

        config = parse_config(resource_path / "mpyl_config_with_unknown_fields.yml")
        validate(config, schema_dict.decode("utf-8"))

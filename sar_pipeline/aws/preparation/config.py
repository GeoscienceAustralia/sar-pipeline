import os
from ruamel.yaml import YAML
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_BASE_CONFIGS = ["IW_20m_antarctica.yaml", "IW_20m_australia.yaml"]
BASE_CONFIGS_FOLDER = Path(__file__).parents[2] / "configs/ISCE3-RTC"


class RTCConfigManager:
    def __init__(self, base_config: str | None = None, config_path: str | None = None):
        self._validate(base_config, config_path)
        self.base_config = base_config
        if config_path is not None:
            self.file_path = config_path
        if base_config is not None and config_path is None:
            self.file_path = self._get_base_config_path()
        self.yaml = YAML()  # Create a YAML instance
        self.yaml.preserve_quotes = True  # Preserve string formatting
        self.data = self._load_yaml()

    def _validate(self, base_config, config_path):
        assert (
            base_config is not None or config_path is not None
        ), "A `base_config` or `config_path` must be provided"
        if base_config is not None and config_path is not None:
            logger.info(
                "Both `base_config` or `config_path` provided. "
                " config_path will be loaded."
            )

    def _get_base_config_path(self):
        # get the path to the specified base config
        assert (
            self.base_config in VALID_BASE_CONFIGS
        ), "specified base rtc_config is not valid"
        return BASE_CONFIGS_FOLDER / self.base_config

    def _load_yaml(self):
        """Load YAML while preserving comments."""
        with open(self.file_path, "r") as file:
            return self.yaml.load(file)

    def get(self, key, default=None, separator="."):
        """Get a nested value from the YAML data."""
        keys = key.split(separator)  # Support notation for nested keys
        data = self.data  # Start at the root

        for k in keys:
            if not isinstance(data, dict) or k not in data:
                return default  # Return default if key is missing
            data = data[k]  # Move deeper

        return data  # Return the final value

    def set(self, key, value, separator="."):
        """Set a nested value in the YAML data."""
        keys = key.split(separator)  # Support notation for nested keys
        data = self.data  # Start at the root

        for k in keys[:-1]:  # Traverse to the second-to-last key
            if k not in data or not isinstance(data[k], dict):
                data[k] = {}  # Ensure the intermediate key is a dict
            data = data[k]  # Move deeper

        data[keys[-1]] = value  # Set the final key

    def save(self, save_path):
        """Write the updated data back while preserving formatting."""
        with open(save_path, "w") as file:
            self.yaml.dump(self.data, file)

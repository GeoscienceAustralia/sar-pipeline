
import os
from ruamel.yaml import YAML
from pathlib import Path

VALID_CONFIGS = ['IW_20m_antarctica.yaml','IW_20m_australia.yaml']

class RTCConfigManager:
    def __init__(self, base_config):
        self.base_config = base_config
        self.file_path = self._get_base_config_path()
        self.yaml = YAML()  # Create a YAML instance
        self.yaml.preserve_quotes = True  # Preserve string formatting
        self.data = self._load_yaml()

    def _get_base_config_path(self):
        # get the path to the specified base config
        assert self.base_config in VALID_CONFIGS, 'specified base rtc_config is not valid'
        cur_dir = Path(os.path.dirname(os.path.realpath(__file__)))
        return cur_dir.parent / Path(f'configs/ISCE3-RTC/{self.base_config}')
    
    def _load_yaml(self):
        """Load YAML while preserving comments."""
        with open(self.file_path, "r") as file:
            return self.yaml.load(file)

    def get(self, key, default=None):
        """Get a nested value from the YAML data."""
        keys = key.split(".")  # Support dot notation for nested keys
        data = self.data  # Start at the root

        for k in keys:
            if not isinstance(data, dict) or k not in data:
                return default  # Return default if key is missing
            data = data[k]  # Move deeper

        return data  # Return the final value

    def set(self, key, value):
        """Set a nested value in the YAML data."""
        keys = key.split(".")  # Support dot notation for nested keys
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

# # Example Usage
# config = RTCConfigManager("config.yaml")

# # Modify values
# config.set("scene", "new_scene")
# config.set("config", {"resolution": "1080p", "quality": "high"})

# # Save changes
# config.save()

# class rtc_config():
#     def __init__(self, base_config : str):
#         self.base_config = base_config
#     ...

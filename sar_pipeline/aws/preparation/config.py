
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

    def get(self, key):
        """Get a value from the YAML data."""
        return self.data.get(key, None)

    def set(self, key, value):
        """Set a value in the YAML data."""
        self.data[key] = value

    def save(self):
        """Write the updated data back while preserving formatting."""
        with open(self.file_path, "w") as file:
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

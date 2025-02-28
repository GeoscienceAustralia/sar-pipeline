import json
from pathlib import Path

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_STAC_JSON = Path(__file__).parent / 'json-schema/product.json'

class RTCStacManager:
    def __init__(self, file_path: Path = BASE_STAC_JSON):
        """
        Initialize the manager with a specified JSON metadata file.
        :param file_path: Path to the JSON file to load.
        """
        self.file_path = Path(file_path)
        self.metadata = self._load_file()

    def _load_file(self) -> dict:
        """
        Load the JSON metadata file into a dictionary.
        :return: Dictionary containing the metadata.
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {self.file_path}")
        
        with self.file_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def update_value(self, key_path: str, value):
        """
        Update a value in the metadata using a dot-separated key path.
        Example: key_path="properties.title" updates metadata["properties"]["title"]
        :param key_path: Dot-separated path to the key.
        :param value: New value to set.
        """
        keys = key_path.split(".")
        ref = self.metadata

        for key in keys[:-1]:
            if key not in ref or not isinstance(ref[key], dict):
                raise KeyError(f"Key path '{key_path}' is invalid.")
            ref = ref[key]
        
        ref[keys[-1]] = value

    def get_value(self, key_path: str):
        """
        Retrieve a value from the metadata using a dot-separated key path.
        Example: key_path="properties.title" retrieves metadata["properties"]["title"]
        :param key_path: Dot-separated path to the key.
        :return: The value found at the specified key path.
        """
        keys = key_path.split(".")
        ref = self.metadata

        for key in keys:
            if key not in ref:
                raise KeyError(f"Key path '{key_path}' not found.")
            ref = ref[key]
        
        return ref

    def save(self, output_path: str):
        """
        Save the modified metadata to a new file.
        :param output_path: Path to save the updated JSON file.
        """
        output_file = Path(output_path)
        with output_file.open("w", encoding="utf-8") as file:
            json.dump(self.metadata, file, indent=2, ensure_ascii=False)



def make_opera_rtc_stac():
    # point at the directory containing the rtc config and outputs from rtc process
    # and make STAC metadata
    ...
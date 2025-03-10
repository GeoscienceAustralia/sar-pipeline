import json
from pathlib import Path
import pystac
from datetime import datetime

import logging
from sar_pipeline.aws.metadata.h5 import RTCH5Manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_STAC_JSON = Path(__file__).parent / 'json-schema/product.json'

class RTCStacTemplate:
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

    def update_value(self, key_path: str, value, separator='.'):
        """
        Update a value in the metadata using a separated key path.
        Example: key_path="properties.title" updates metadata["properties"]["title"]
        :param key_path: path to the key separated by a `separator`.
        :param value: New value to set.
        :separator: Key string separator
        """
        keys = key_path.split(separator)
        ref = self.metadata

        for key in keys[:-1]:
            if key not in ref or not isinstance(ref[key], dict):
                raise KeyError(f"Key path '{key_path}' is invalid.")
            ref = ref[key]
        
        ref[keys[-1]] = value

    def get_value(self, key_path: str, separator='.'):
        """
        Retreive a value in the metadata using a separated key path.
        Example: key_path="properties.title" updates metadata["properties"]["title"]
        :param key_path: path to the key separated by a `separator`.
        :param value: New value to set.
        :separator: Key string separator
        """
        keys = key_path.split(separator)
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


def burst_stac_metadata_from_h5(
        burst_h5_filepath : Path,
):
    # load the .h5 and stac metadata into manager classes
    burst_h5 = RTCH5Manager(burst_h5_filepath)
    # load the stac template NOTE this may not be required
    stac_template = RTCStacTemplate() # read in the template with required fields

    # get key information for defining pystac item
    id_ = burst_h5_filepath.stem, # get product name from filepath
    start_dt = burst_h5.search_value('identification/zeroDopplerStartTime').decode("utf-8")
    start_dt = datetime.fromisoformat(start_dt.rstrip("Z")) # Convert to datetime
    end_dt = burst_h5.search_value('identification/zeroDopplerEndTime').decode("utf-8")
    end_dt = datetime.fromisoformat(end_dt.rstrip("Z"))

    # set properties based on metadata in the .h5 file
    required_properties = {
        'gsd' : burst_h5.search_value('xCoordinateSpacing'),
        'card4l:noise_removal_applied' : bool(burst_h5.search_value('noiseCorrectionApplied')),
        'card4l:speckle_filtering' : None,
        'card4l:pixel_coordinate_convention' : '',
        'card4l:measurement_type' : '',
        'card4l:measurement_convention' : '',
        'card4l:conversion_eq' : '',
        'card4l:northern_geometric_accuracy' : '',
        'card4l:eastern_geometric_accuracy' : '',
        'card4l:gridding_convention' : ','
    }

    # define the item
    item = pystac.Item(
        id=id_,
        geometry=None,  # Add proper geometry (e.g., bounding box)
        bbox=None,      # Define bounding box
        datetime=start_dt,
        start_datetime=start_dt,
        end_datetime=end_dt,
        properties = required_properties
    )
    

    return item
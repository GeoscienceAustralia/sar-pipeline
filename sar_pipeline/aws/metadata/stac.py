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
        """Initialize the manager with a specified JSON metadata file.

        Parameters
        ----------
        file_path : Path, optional
            Path to the JSON file to load, by default BASE_STAC_JSON
        """
        self.file_path = Path(file_path)
        self.metadata = self._load_file()

    def _load_file(self) -> dict:
        """Load the JSON metadata file into a dictionary.

        Returns
        -------
        dict
            Dictionary containing the metadata.

        Raises
        ------
        FileNotFoundError
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {self.file_path}")
        
        with self.file_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def update_value(self, key_path: str, value, separator='.'):
        """Update a value in the metadata using a separated key path.
        Example: key_path="properties.title" updates metadata["properties"]["title"]

        Parameters
        ----------
        key_path : str
            path to the key separated by a `separator`.
        value : _type_
             New value to set.
        separator : str, optional
            Key string separator, by default '.'

        Raises
        ------
        KeyError
        """

        keys = key_path.split(separator)
        ref = self.metadata

        for key in keys[:-1]:
            if key not in ref or not isinstance(ref[key], dict):
                raise KeyError(f"Key path '{key_path}' is invalid.")
            ref = ref[key]
        
        ref[keys[-1]] = value

    def get_value(self, key_path: str, separator='.'):
        """Retrieve a value in the metadata using a separated key path.
        Example: key_path="properties.title" updates metadata["properties"]["title"]

        Parameters
        ----------
        key_path : str
            path to the key separated by a `separator`.
        separator : str, optional
            Key string separator, by default '.'
        """

        keys = key_path.split(separator)
        ref = self.metadata

        for key in keys:
            if key not in ref:
                raise KeyError(f"Key path '{key_path}' not found.")
            ref = ref[key]
        
        return ref

    def save(self, output_path: str | Path):
        """Save stac dict to path

        Parameters
        ----------
        output_path : str
            save path
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

    # set properties based on metadata in the .h5 file
    required_properties = {
        'gsd' : burst_h5.search_value('xCoordinateSpacing'),
        'card4l:noise_removal_applied' : bool(burst_h5.search_value('noiseCorrectionApplied')),
        'card4l:speckle_filtering' : bool(burst_h5.search_value('filteringApplied')),
        'card4l:pixel_coordinate_convention' : '',
        'card4l:measurement_type' : burst_h5.search_value('outputBackscatterNormalizationConvention'),
        'card4l:measurement_convention' : burst_h5.search_value('outputBackscatterExpressionConvention'),
        'card4l:conversion_eq' : burst_h5.search_value('outputBackscatterDecibelConversionEquation'),
        'card4l:northern_geometric_accuracy' : {
            'bias': burst_h5.search_value('geometricAccuracy/bias/y'), # NOTE not north in 3031
            'std': burst_h5.search_value('geometricAccuracy/stddev/y'), # NOTE not north in 3031
        },
        'card4l:eastern_geometric_accuracy' : {
            'bias': burst_h5.search_value('geometricAccuracy/bias/x'), # NOTE not north in 3031
            'std': burst_h5.search_value('geometricAccuracy/stddev/x'), # NOTE not north in 3031
        },
        'card4l:gridding_convention' : 'geocoded burst', # TODO is this a valid value to set?
    }

    # get key information for defining pystac item
    id_ = burst_h5_filepath.stem, # get product name from filepath
    start_dt = burst_h5.search_value('identification/zeroDopplerStartTime')
    start_dt = datetime.fromisoformat(start_dt.rstrip("Z")) # Convert to datetime
    end_dt = burst_h5.search_value('identification/zeroDopplerEndTime')
    end_dt = datetime.fromisoformat(end_dt.rstrip("Z"))

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
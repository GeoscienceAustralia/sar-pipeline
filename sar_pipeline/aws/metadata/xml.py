from pathlib import Path
from datetime import datetime, timezone
import json
import pandas as pd
from sar_pipeline.aws.metadata.h5 import H5Manager
import xml.etree.ElementTree as ET
import copy
import pyproj
import shapely
from typing import Literal

CURRENT_DIR = Path(__file__).parent.resolve()
XML_TEMPLATE_PATH = CURRENT_DIR / "templates" / "s1nrb.xml"
XML_MAPPING_CSV = CURRENT_DIR / "templates" / "s1nrbXmlMapping.csv"

VALID_XML_METADATA_SOURCES = ["STAC", "JSON", "H5", "HDF5", "FIXED_VALUE", "SPECIAL"]

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class XMLMapper:
    def __init__(
        self,
        stac_path: Path | str,
        h5_path: Path | str,
        polarisations: list,
        backscatter_convention: Literal["gamma0", "sigma0", "beta0"],
        xml_template_path: Path | str = XML_TEMPLATE_PATH,
        mapping_csv_path: Path | str = XML_MAPPING_CSV,
    ):
        """Utility class to create XML metadata from the
        existing STAC JSON and HDF5 metadata files.

        Parameters
        ----------
        stac_path : Path | str
            Path to the stac file
        h5_path : Path | str
            Path to the hdf5 / .h5 file
        polarisations : list
            List of the burst polarisations. Combination of
            HH, HV, VV, VH
        backscatter_convention: Literal["gamma0", "sigma0", "beta0"]
            The normalisation convention of the backscatter products
        xml_template_path : Path | str, optional
            Path to the empty xml template with tags. By default XML_TEMPLATE_PATH
        mapping_csv_path : Path | str, optional
            Path to a mapping CSV that describes the XML_TAG,
            SOURCE_FILE, SOURCE_TAG and UNIT. This enables us to create
            An XML file with the appropriate tags and values. by default XML_MAPPING_CSV.
        """

        self.stac_path = stac_path
        self.h5_path = h5_path
        self.xml_template_path = xml_template_path
        self.mapping_csv_path = mapping_csv_path
        self.stac = self._load_json(Path(stac_path))
        self.polarisations = polarisations
        self.backscatter_convention = backscatter_convention
        self.h5 = H5Manager(Path(h5_path))
        self.xml = self._load_xml(Path(xml_template_path))
        self.mapper_df = self._load_mapping_csv_into_df(Path(mapping_csv_path))

    def _load_json(self, json_path: Path):
        if not json_path.exists:
            raise FileExistsError(f"STAC json file not found: {json_path}")
        else:
            with open(json_path, "r") as f:
                return json.load(f)

    def get_nested_stac_values(
        self, key: str, sep=".", access_links_as_dict: bool = True
    ):
        """Get the requested value from the json. Able to handle nested dicts in
        the json using the specified separator keys. Special logic is also used
        to handle links, as these exist in the stac file as a list of dicts without a key.

        Parameters
        ----------
        key : str
            json dictionary key. '.' separated by default to access nested values. For example
            properties.value
        sep : str
            Separator for nested dict. '.' by default.
        access_links_as_dict : bool, optional
            Treat a 'link' key differently. Links are provided in a list in the
            stac document. access_links_as_dict = True will treat the 'rel' value as the key.
        """
        data = self.stac
        keys = key.split(sep)
        for k in keys:
            if k not in data:
                raise ValueError(
                    f"JSON value could not be obtained from key : '{key}'. Failed to access '{k}'. "
                    f"JSON filepath : {self.stac_path}"
                )
            if k == "links" and access_links_as_dict:
                # iterate through the list of links and create a dict
                # using the rel as the key
                data = {link["rel"]: link for link in data[k]}
            else:
                data = data[k]

        return data

    def _load_xml(self, xml_path):
        if not xml_path.exists:
            raise FileExistsError(f"XML template file not found: {xml_path}")
        else:
            try:
                return ET.parse(xml_path)
            except Exception as e:
                logger.error(
                    f"Failed to parse XML template : {xml_path}",
                    exc_info=True,
                )
                raise

    def _load_mapping_csv_into_df(self, csv_path):
        """load the csv that contains mappings between the
        stac json and .h5 metadata to the xml template"""
        if not csv_path.exists:
            raise FileExistsError(
                f"The the CSV that contains mappings between the stac json / .h5 metadata "
                f"to the xml template could not be found found : {csv_path}"
            )
        else:
            return pd.read_csv(csv_path)

    def duplicate_xml_section(self, xml_tag: str, n_copies: int = 1):
        """
        Duplicate the first occurrence of a given XML section
        and insert the copies directly after the original section.
        """
        root = self.xml.getroot()

        # find the first occurrence
        section = root.find(f".//{xml_tag}")
        if section is None:
            raise ValueError(f"No <{xml_tag}> found in XML.")

        # find the parent
        parent = next((elem for elem in root.iter() if section in list(elem)), None)
        if parent is None:
            raise ValueError(f"Could not find parent for <{xml_tag}>.")

        # find index of original section in parent's children
        children = list(parent)
        index = children.index(section)

        # insert deep copies directly after the original
        for i in range(n_copies):
            new_section = copy.deepcopy(section)
            parent.insert(index + 1 + i, new_section)  # keep incrementing index

    def populate_xml(self):
        """populate the xml template using other metadata files and the
        xml template"""

        # iterate through the rows of the csv
        for _, row in self.mapper_df.iterrows():
            xml_tag = row["XML_TAG"]
            source_file = row["SOURCE_FILE"]
            source_tag = row["SOURCE_TAG"]
            unit = row["UNIT"]
            if not source_file or pd.isna(source_file):
                # no source file, header tag with no mapping
                continue

            if source_file in ["STAC", "JSON"]:
                # get desired tag value from stac json file
                value = self.get_nested_stac_values(source_tag)

            elif source_file in ["HDF5", "H5"]:
                # get desired tag value from hdf5 / .h5 file
                value = self.h5.get_value(source_tag)

            elif source_file == "FIXED_VALUE":
                # value is fixed and already set in the mapping file
                value = source_tag

            elif source_file == "SPECIAL":
                # This is a special value that gets handled elsewhere in the code
                # For example, creating multiple sections for the BackscatterMeasurementData
                # As multiple polarisations may be present in the product
                continue

            else:
                raise ValueError(
                    f"Invalid SOURCE_FILE in mapping file : {source_file}. Must be one of "
                    f"{VALID_XML_METADATA_SOURCES}. Mapping file path : {self.mapping_csv_path}"
                )

            # update the tag value
            template_tag = self.xml.getroot().find(".//" + xml_tag)
            if template_tag is None:
                raise ValueError(
                    f"Could not find mapping XML_TAG in xml template : {xml_tag}"
                )
            if template_tag is not None:
                try:
                    self.xml.getroot().find(".//" + xml_tag).text = str(value)
                except:
                    raise ValueError(
                        "Could not set value in the xml : "
                        f"XML_TAG : {xml_tag}"
                        f"SOURCE_FILE : {source_file}"
                        f"SOURCE_TAG : {source_tag}"
                        f"UNIT : {unit}"
                    )

    def populate_special_xml_mappings(
        self, backscatter_section="BackscatterMeasurementData"
    ):
        """Logic to populate special xml values. These are flagged with
        the SOURCE_FILE = SPECIAL in the xml mapping csv. E.g.
            - backscatter measurement tags, given there
              can be any combination of HH+HV, HH, VV, VV+VH. The tag may
              need to be duplicated and added to the data set.
            - polarisations need to be a string, i.e. HH+HV not a list
              ['HH','HV']
            - projection wkt2 code. Not included in STAC, so is set here.
            - bbox provided as a wkt not list.
            - Sets SourceProcParam/ProcessingDate as a UTC timestamp

        Parameters
        ----------
        backscatter_section : str, optional
            XML Tag for the backscatter, by default 'BackscatterMeasurementData'
        """

        # create the required number of backscatter sections
        if len(self.polarisations) > 1:
            self.duplicate_xml_section(
                backscatter_section, n_copies=len(self.polarisations) - 1
            )
        for i, pol in enumerate(self.polarisations):
            # set the polarisation tag
            tag = "CEOS-ARDProductAttributes/BackscatterMeasurementData/Polarization"
            value = pol
            try:
                self.xml.getroot().findall(".//" + tag)[i].text = str(value)
            except:
                raise ValueError(
                    f"Could not set the polarisation tag : {tag} for pol : {pol}"
                )
            # set the filename tag which is the s3 link for the given file
            tag = "CEOS-ARDProductAttributes/BackscatterMeasurementData/FileName"
            stac_tag = f"assets.{pol}_{self.backscatter_convention}.href"
            value = self.get_nested_stac_values(stac_tag)
            try:
                self.xml.getroot().findall(".//" + tag)[i].text = str(value)
            except:
                raise ValueError(
                    f"Could not set the polarisation filename tag : {tag} for pol : {pol}"
                )

        # set the polarisations as a string separated by '+' for dual pol
        tag = "SourceDataAcquisitionParameters/Polarizations"
        stac_tag = "properties.sar:polarizations"
        value = "+".join(self.get_nested_stac_values(stac_tag))
        try:
            self.xml.getroot().find(".//" + tag).text = str(value)
        except:
            raise ValueError(f"Could not set the 'SPECIAL' tag {tag} in xml")

        # set the wkt2 code for the projection
        tag = 'CEOS-ARDProductAttributes/CoordinateReferenceSystem[@type="WKT"]'
        proj_epsg = self.h5.search_value("data/projection")
        value = pyproj.CRS.from_epsg(proj_epsg).to_wkt()
        try:
            self.xml.getroot().find(".//" + tag).text = str(value)
        except:
            raise ValueError(f"Could not set the 'SPECIAL' tag {tag} in xml")

        # set the extent as wkt
        tag = "CEOS-ARDProductAttributes/ProductGeographicalExtent"
        stac_tag = "bbox"
        value = shapely.box(*self.get_nested_stac_values(stac_tag)).wkt
        try:
            self.xml.getroot().find(".//" + tag).text = str(value)
        except:
            raise ValueError(f"Could not set the 'SPECIAL' tag {tag} in xml")

        # set the SourceProcParam/ProcessingDate as a UTC time by adding 'Z'
        tag = "SourceProcParam/ProcessingDate"
        try:
            value = f"{self.xml.getroot().find(".//" + tag).text}Z"
            self.xml.getroot().find(".//" + tag).text = value
        except:
            raise ValueError(f"Could convert xml tag {tag} to UTC time")

    def save_xml(self, output_path):
        try:
            self.xml.write(output_path, encoding="utf-8", xml_declaration=True)
        except Exception as e:
            logger.error(
                f"Could not save XML file to : {output_path}",
                exc_info=True,
            )
            raise

from datetime import datetime
import pystac_client
from odc.stac import configure_s3_access
from shapely.geometry import Polygon, MultiPolygon
from pystac import Link
from pystac.stac_io import DefaultStacIO
from typing import Union, Any
from urllib.parse import urlparse
import boto3

from sar_pipeline.utils.general import log_timing, format_dt_utc


@log_timing
def query_stac_for_metadata_in_period(
    start_dt: datetime,
    end_dt: datetime,
    geometry: Polygon | MultiPolygon | None,
    collections: list,
    stac_catalog: str,
    query: dict | None = None,
    fields: dict | None = None,
):
    """Query A given STAC API for product metadata that falls within the
    provided time range and geometry.

    Parameters
    ----------
    start_dt : datetime
        search start datetime
    end_dt : datetime
        search end datetime
    geometry : shape | Polygon | MultiPolygon | None
        search geometry
    collections : list, optional
        Collection to search, e.g. ["sentinel-1-slc"]
    stac_catalog : str, optional
        STAC catalog url to search, e.g. "https://stac.dataspace.copernicus.eu/v1/"
        or "https://explorer.dea.ga.gov.au/stac"
    query : dict, optional
        Additional filtering for the products. e.g.
        {"sar:instrument_mode": {"eq": "IW"}}
    fields : dict
        limit the fields of the response. e.g.
        fields={"include": ["id", "properties.sarard:scene_id"]}

    Returns
    -------
    tuple (int, dict)
        Count of matching products and dictionary of stac metadata for the scenes
        matching the criteria.
    """

    stac_client = pystac_client.Client.open(stac_catalog)
    configure_s3_access(cloud_defaults=True, aws_unsigned=True)
    stac_start_dt = format_dt_utc(start_dt)
    stac_end_dt = format_dt_utc(end_dt)
    stac_items = stac_client.search(
        collections=collections,
        datetime=f"{stac_start_dt}/{stac_end_dt}",
        intersects=geometry,
        query=query,
        fields=fields,
    )
    n_stac_items = stac_items.matched()

    return n_stac_items, stac_items


class S3StacIO(DefaultStacIO):
    """Custom StacIO class to read and write from S3 buckets"""

    def __init__(self):
        self.s3 = boto3.resource("s3")
        super().__init__()

    def read_text(self, source: Union[str, Link], *args: Any, **kwargs: Any) -> str:
        """Read text from a source, which can be a string or a Link. If the source is an S3 path, read from S3, otherwise use the default method."""
        parsed = urlparse(source)
        if parsed.scheme == "s3":
            bucket = parsed.netloc
            key = parsed.path[1:]

            obj = self.s3.Object(bucket, key)
            return obj.get()["Body"].read().decode("utf-8")
        else:
            return super().read_text(source, *args, **kwargs)

    def write_text(
        self, dest: Union[str, Link], txt: str, *args: Any, **kwargs: Any
    ) -> None:
        """Write text to a destination, which can be a string or a Link. If the destination is an S3 path, write to S3, otherwise use the default method."""
        parsed = urlparse(dest)
        if parsed.scheme == "s3":
            bucket = parsed.netloc
            key = parsed.path[1:]
            self.s3.Object(bucket, key).put(Body=txt, ContentEncoding="utf-8")
        else:
            super().write_text(dest, txt, *args, **kwargs)

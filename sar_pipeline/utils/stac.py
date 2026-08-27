from datetime import datetime
import pystac_client
from odc.stac import configure_s3_access
from shapely.geometry import Polygon, MultiPolygon
from pystac import Link, Item
from pystac.stac_io import DefaultStacIO
from typing import Union, Any
from urllib.parse import urlparse
import boto3
import tqdm
import tempfile
import stac_geoparquet.arrow
from pathlib import Path
from sar_pipeline.utils.aws import S3Util

from sar_pipeline.utils.general import log_timing, format_dt_utc
from sar_pipeline.utils.aws import find_s3_filepaths_from_suffixes


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


def read_stac_items_from_s3(
    bucket: str,
    prefix: str = "",
    item_suffixes: list[str] = ["stac-item.json"],
    aws_profile: str | None = None,
    num_to_read: int | None = None,
):
    """Reads STAC items from an S3 bucket and prefix, filtering by specified suffixes.

    Parameters
    ----------
    bucket: str
        The name of the S3 bucket to read from.
    prefix: str, Optional
        The prefix within the S3 bucket to search for STAC item JSON files.
    item_suffixes: list[str], Optional
        A list of suffixes to filter the files by (e.g., ["stac-item.json"]).
    aws_profile: str | None, Optional
        AWS profile name to use for authentication. If None, uses default credentials.
    num_to_read: int | None, Optional
        Number of items to read. If None, reads all matching items.

    Returns
    --------
    list[pystac.Item]: A list of pystac.Item objects read from the specified S3 location.

    Raises
    -------
    Exception: If there is an error reading any of the STAC items from S3.
    """

    if aws_profile is not None:
        boto3.setup_default_session(profile_name=aws_profile)

    # Find all STAC item JSON files in the specified S3 bucket and prefix
    item_filepaths_dict = find_s3_filepaths_from_suffixes(
        bucket, prefix, suffixes=item_suffixes
    )

    # Flatten the list of filepaths from the dictionary
    item_filepaths = [
        filepath for filepaths in item_filepaths_dict.values() for filepath in filepaths
    ]

    if num_to_read is not None:
        item_filepaths = item_filepaths[:num_to_read]

    loop = tqdm.tqdm(item_filepaths, desc="Reading STAC items from S3")

    items = []
    for filepath in loop:
        try:
            item = Item.from_file(f"s3://{bucket}/{filepath}")
            items.append(item)
        except Exception as e:
            print(f"Error reading STAC item from {filepath}: {e}")
        loop.set_postfix({"Last read": filepath})

    return items


def create_and_upload_geoparquet(
    items: list[Item], output_path: str | None = None, aws_profile: str | None = None
) -> Any:
    """Converts a list of pystac.Items to pyarrow Table and optionally writes it to an output path.
    The output path could be an s3 url, in which case the file is uploaded to the provided s3 url.

    Parameters
    ----------
    items: list[Item]
        List of pystac.Items to convert and optionally upload
    output_path: str | None, optional
        The output path to write the parquet file. Can be a local path or an S3 URL. Defaults to None.
    aws_profile: str | None, optional
        AWS profile name to use for authentication. If None, uses default credentials. Defaults to None.

    Returns
    -------
    Any:
        The resulting pyarrow Table containing the STAC items.
    """
    record_batch_reader = stac_geoparquet.arrow.parse_stac_items_to_arrow(items)
    table = record_batch_reader.read_all()

    if output_path:
        parsed = urlparse(output_path)
        is_s3 = False
        if parsed and parsed.scheme == "s3":
            bucket = parsed.netloc
            key = parsed.path[1:]
            is_s3 = True
            print(f"Uploading to S3 bucket: {bucket}, key: {key}")
        if is_s3:
            if aws_profile:
                boto3.setup_default_session(profile_name=aws_profile)
            s3uploader = S3Util()
            with tempfile.TemporaryDirectory() as tmpdir:
                local_parquet_path = Path(tmpdir) / "temp.parquet"
                stac_geoparquet.arrow.to_parquet(table, local_parquet_path)
                s3uploader.s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=local_parquet_path.read_bytes(),
                    ContentType="application/octet-stream",
                )
        else:
            stac_geoparquet.arrow.to_parquet(table, output_path)
    return table

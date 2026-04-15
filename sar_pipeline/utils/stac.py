from datetime import datetime
import pystac_client
from odc.stac import configure_s3_access
from shapely.geometry import Polygon, MultiPolygon

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

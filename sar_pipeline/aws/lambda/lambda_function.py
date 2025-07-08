import json
import logging
import os
from datetime import datetime, timedelta

import boto3
import requests
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def convert_filename_to_sceneid(filename):
    """Extracts the scene ID from a Sentinel-1 filename.

    Args:
        filename (str): Sentinel-1 filename, e.g., 'S1A_IW_SLC__1SDV_20240108T191816_20240108T191843_052019_064949_0FD4.SAFE'.

    Returns:
        str: Scene ID, e.g., 'S1A_IW_SLC__1SDV_20240108T191816_20240108T191843_052019_064949_0FD4'.
    """
    scene_id = filename.split(".SAFE")[0]
    return scene_id


def generate_unique_identifier(filename):
    """Extracts the start date and product ID from the filename to generate an identifier. based on the filename.

    Args:
        filename (str): Sentinel-1 filename, e.g., 'S1A_IW_SLC__1SDV_20240108T191816_20240108T191843_052019_064949_0FD4.SAFE'.

    Returns:
        str: identifier in the format StartDateYYYYMMDD_ProductId, e.g., 20240108_0FD4.
    """
    scene_id = convert_filename_to_sceneid(filename)
    start_date = scene_id[17:25]
    product_unique_id = scene_id[-4:]
    base_identifier = f"{start_date}_{product_unique_id}"
    return base_identifier


def get_coords_from_polygon(geometry):
    """
    Extracts the coordinates from geometry type 'Polygon' or the coordinates of the union of geometry type 'MultiPolygon'.

    Args:
        geometry (dict): A GeoJSON-style geometry dictionary with "type" and "coordinates".

    Raises:
        ValueError: If the geometry type is not supported or the union result is invalid.

    Returns:
        list: A list of coordinate lists representing the exterior boundary of the Polygon.
    """
    if geometry["type"] == "MultiPolygon":
        multipolygon = MultiPolygon(
            [Polygon(polygon[0]) for polygon in geometry["coordinates"]]
        )
        unified_polygon = unary_union(multipolygon)
        if isinstance(unified_polygon, Polygon):
            return [list(unified_polygon.exterior.coords)]
        else:
            raise ValueError("The union result is not a valid Polygon.")
    elif geometry["type"] == "Polygon":
        return geometry["coordinates"]
    else:
        raise ValueError(
            f"Unsupported geometry type: {geometry['type']}. Supported types are Polygon or Multipolygon."
        )


def get_coords_from_geojson_file(geojson_file):
    """Extracts and unifies coordinates from a GeoJSON Feature, FeatureCollection, or Geometry.

    Args:
        geojson_file (str): Path to a GeoJSON file.

    Raises:
        ValueError: If the FeatureCollection contains no features.

    Returns:
        list: List of coordinate lists from all polygons.
    """
    with open(geojson_file) as f:
        geojson = json.load(f)

    coords = []

    if geojson.get("type") == "Feature":
        coords.append(get_coords_from_polygon(geojson["geometry"]))
    elif geojson.get("type") == "FeatureCollection":
        if not geojson["features"]:
            raise ValueError("FeatureCollection is empty")
        for feature in geojson["features"]:
            coords.append(get_coords_from_polygon(feature["geometry"]))
    else:
        coords.append(get_coords_from_polygon(geojson))
    return coords


def lambda_handler(event, context):
    logger.info("Lambda function started.")

    default_end = datetime.now()
    default_start = default_end - timedelta(days=1)

    start_datetime = event.get(
        "start_datetime", default_start.strftime("%Y-%m-%dT%H:%M:%S")
    )
    end_datetime = event.get("end_datetime", default_end.strftime("%Y-%m-%dT%H:%M:%S"))
    limit = event.get("limit", 5)
    product_type = event.get("product_type", "IW_SLC__1S")
    output_CRS = event.get("output_CRS", "utm")
    dry_run = event.get("dry_run", False)
    queue_url = event.get("queue_url", "")
    project = event.get("project", "experimental/s1_rtc_c1")

    geojson_key = event.get(
        "geojson_key", "persistent/DEA-non-offshore-product-extent.geojson"
    )
    geojson_file = f"/tmp/{os.path.basename(geojson_key)}"

    s3 = boto3.client("s3")
    bucket = "deant-data-public-dev"

    logger.info(f"Downloading GeoJSON from s3://{bucket}/{geojson_key}")
    s3.download_file(bucket, geojson_key, geojson_file)

    all_coordinates = get_coords_from_geojson_file(geojson_file)
    logger.info(f"Loaded {len(all_coordinates)} geometries from GeoJSON.")

    sqs_client = boto3.client("sqs")
    headers = {"Content-Type": "application/json"}
    datas = []
    messages = []
    url = "https://catalogue.dataspace.copernicus.eu/stac/search"

    for coordinates in all_coordinates:
        payload = {
            "collections": ["SENTINEL-1"],
            "datetime": f"{start_datetime}/{end_datetime}",
            "limit": limit,
            "filter-lang": "cql2-json",
            "filter": {
                "op": "and",
                "args": [
                    {"op": "=", "args": [{"property": "productType"}, product_type]},
                    {
                        "op": "s_intersects",
                        "args": [
                            {"property": "geometry"},
                            {"type": "Polygon", "coordinates": coordinates},
                        ],
                    },
                ],
            },
        }

        current_page = 1
        while True:
            if current_page > 10:
                logger.warning("Reached 10 pages, stopping pagination.")
                break

            logger.info(f"Fetching page {current_page}...")
            payload["page"] = current_page

            try:
                response = requests.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    logger.error(
                        f"Error from STAC API: {response.status_code} {response.text}"
                    )
                    return {"statusCode": response.status_code, "error": response.text}

                data = response.json()
                datas.append(data)
                num_items = len(data.get("features", []))
                logger.info(f"Page {current_page}: {num_items} items fetched.")

                next_link = next(
                    (
                        link
                        for link in data.get("links", [])
                        if link.get("rel") == "next"
                    ),
                    None,
                )
                if not next_link:
                    logger.info("No more pages to fetch.")
                    break
                current_page += 1

            except Exception as e:
                logger.exception("Exception during STAC request:")
                return {"statusCode": 500, "error": str(e)}

    for data in datas:
        for item in data.get("features", []):
            scene_id = convert_filename_to_sceneid(item["id"])
            unique_identifier = generate_unique_identifier(scene_id)
            message_body = {
                "jobName": unique_identifier,
                "sceneId": scene_id,
                "outputCRS": output_CRS,
                "project": project,
            }

            if dry_run:
                messages.append(message_body)
            else:
                if not queue_url:
                    raise ValueError("Missing queue_url in non-dry run mode.")
                sqs_response = sqs_client.send_message(
                    QueueUrl=queue_url, MessageBody=json.dumps(message_body)
                )
                messages.append(
                    {
                        "MessageId": sqs_response["MessageId"],
                        "jobName": unique_identifier,
                    }
                )

    logger.info(f"{len(messages)} scenes processed.")
    return {"statusCode": 200, "body": json.dumps({"messages": messages})}

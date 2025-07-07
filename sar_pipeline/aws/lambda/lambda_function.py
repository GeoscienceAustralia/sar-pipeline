import requests
from datetime import datetime, timedelta
import json
import boto3
import os
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

def convert_filename_to_sceneid(filename):
    scene_id = filename.split('.SAFE')[0]
    return scene_id

def generate_unique_identifier(filename):
    # Remove the file extension (.SAFE) for processing
    scene_id = convert_filename_to_sceneid(filename)

    # Extract start date and product unique ID
    start_date = scene_id[17:25]      # e.g., '20240224'
    product_unique_id = scene_id[-4:] # e.g., 'FDC0'

    base_identifier = f"{start_date}_{product_unique_id}"
    return base_identifier

def union_multipolygon_coordinates(geojson_file):
    with open(geojson_file) as f:
        geojson = json.load(f)

    if geojson.get("type") == "Feature":
        geometry = geojson["geometry"]
    elif geojson.get("type") == "FeatureCollection":
        if not geojson["features"]:
            raise ValueError("FeatureCollection is empty")
        geometry = geojson["features"][0]["geometry"]
    else:
        geometry = geojson

    if geometry["type"] == "MultiPolygon":
        multipolygon = MultiPolygon([Polygon(polygon[0]) for polygon in geometry["coordinates"]])
        unified_polygon = unary_union(multipolygon)
        if isinstance(unified_polygon, Polygon):
            return [[list(unified_polygon.exterior.coords)]]
        else:
            raise ValueError("The union result is not a valid Polygon.")
    elif geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    else:
        raise ValueError(f"Unsupported geometry type: {geometry['type']}")

def extract_coords_from_feature_collection(geojson_file):
    with open(geojson_file) as f:
        geojson = json.load(f)

    if geojson.get("type") == "FeatureCollection":
        coords = []
        for feature in geojson["features"]:
            coords.append(feature["geometry"]["coordinates"])
        return coords
    else:
        raise ValueError("Not a FeatureCollection.")

def lambda_handler(event, context):
    # Time defaults
    default_end = datetime.now()
    default_start = default_end - timedelta(days=1)

    start_datetime = event.get("start_datetime", default_start.strftime("%Y-%m-%dT%H:%M:%S"))
    end_datetime = event.get("end_datetime", default_end.strftime("%Y-%m-%dT%H:%M:%S"))
    limit = event.get("limit", 5)
    product_type = event.get("product_type", "IW_SLC__1S")
    output_CRS = event.get("output_CRS", "utm")
    dry_run = event.get("dry_run", False)
    queue_url = event.get("queue_url", "")

    # GeoJSON input
    geojson_key = event.get("geojson_key", "persistent/DEA-non-offshore-product-extent.geojson")
    geojson_file = f'/tmp/{os.path.basename(geojson_key)}'

    # Download from S3
    s3 = boto3.client('s3')
    bucket = 'deant-data-public-dev'
    s3.download_file(bucket, geojson_key, geojson_file)
    # To get one merged polygon
    all_coordinates = union_multipolygon_coordinates(geojson_file)
    # To get separate polygons from all features
    # all_coordinates = extract_coords_from_feature_collection(geojson_file) 

    # Setup SQS and request headers
    sqs_client = boto3.client('sqs')
    headers = {"Content-Type": "application/json"}
    datas = []
    messages = []
    url = "https://catalogue.dataspace.copernicus.eu/stac/search"

    for coordinates in all_coordinates:
        # Setup the initial query payload
        payload = {
            "collections": ["SENTINEL-1"],
            "datetime": f"{start_datetime}/{end_datetime}",
            "limit": limit,
            "filter-lang": "cql2-json",
            "filter": {
                "op": "and",
                "args": [
                    {
                        "op": "=",
                        "args": [
                            {"property": "productType"},
                            product_type
                        ]
                    },
                    {
                        "op": "s_intersects",
                        "args": [
                            {"property": "geometry"},
                            {
                                "type": "Polygon",
                                "coordinates": coordinates
                            }
                        ]
                    }
                ]
            }
        }

        # PAGINATED REQUEST LOOP
        current_page = 1
        while True:
            if current_page > 10:  # Stop after 10 pages
                print("Reached 10 pages, stopping.")
                break

            print(f"Fetching page {current_page}...")
            
            # Add the page number to the payload
            payload["page"] = current_page

            try:
                response = requests.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    return {
                        "statusCode": response.status_code,
                        "error": response.text
                    }

                data = response.json()
                datas.append(data)
                num_items = len(data.get('features', []))
                print(f"Page {current_page}: {num_items} items fetched.")

                links = data.get("links", [])
                next_link = next((link for link in links if link.get("rel") == "next"), None)

                if next_link is None:
                    print("No more pages to fetch.")
                    break
                else:
                    current_page += 1  # Increment the page number for the next request

            except Exception as e:
                return {
                    "statusCode": 500,
                    "error": str(e)
                }

    # Process all the fetched data
    for data in datas:
        for item in data.get("features", []):
            scene_id = convert_filename_to_sceneid(item["id"])
            unique_identifier = generate_unique_identifier(scene_id)
            message_body = {
                "jobName": unique_identifier,
                "sceneId": scene_id,
                "outputCRS": output_CRS,
                "project": "experimental_for_inland_water_team"
            }

            if dry_run:
                messages.append(message_body)
            else:
                if not queue_url:
                    raise ValueError("Missing queue_url in non-dry run mode.")
                sqs_response = sqs_client.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(message_body)
                )
                messages.append({
                    "MessageId": sqs_response["MessageId"],
                    "jobName": unique_identifier
                })

    print(f"{len(messages)} scenes found.")

    return {
        "statusCode": 200,
        "body": json.dumps({"messages": messages})
    }

import json
import logging
from pathlib import Path
from typing import Any

import pystac.validation
from pystac.validation.stac_validator import JsonSchemaSTACValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# STAC extension schemas (and the remote schemas they reference) vendored with
# the package so validation does not need network access. index.json maps each
# schema URI to its file in this folder. The core STAC and GeoJSON schemas are
# bundled with pystac itself.
LOCAL_STAC_SCHEMA_DIR = Path(__file__).parents[1] / "data" / "stac_schemas"
LOCAL_STAC_SCHEMA_INDEX = LOCAL_STAC_SCHEMA_DIR / "index.json"


def load_local_stac_schemas() -> dict[str, dict[str, Any]]:
    """Load the vendored STAC schemas.

    Returns
    -------
    dict[str, dict[str, Any]]
        Mapping of schema URI to the parsed schema.
    """
    with LOCAL_STAC_SCHEMA_INDEX.open("r") as f:
        index = json.load(f)
    schemas = {}
    for uri, filename in index.items():
        with (LOCAL_STAC_SCHEMA_DIR / filename).open("r") as f:
            schemas[uri] = json.load(f)
    return schemas


def use_local_stac_schemas() -> JsonSchemaSTACValidator:
    """Register a pystac validator whose schema cache is pre-filled with the
    vendored schemas, so `pystac.Item.validate()` does not fetch them over the
    network. Schemas that are not vendored are still fetched as normal.

    Returns
    -------
    JsonSchemaSTACValidator
        The validator registered with pystac.
    """
    validator = JsonSchemaSTACValidator()
    validator.schema_cache.update(load_local_stac_schemas())
    pystac.validation.set_validator(validator)
    logger.info(
        f"Using {len(validator.schema_cache)} local STAC schemas for validation"
    )
    return validator

from dotenv import load_dotenv
import os
import logging
from pathlib import Path
from typing import Union

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


class MissingEnvironmentVariableError(Exception):
    """Exception raised there are missing environment variables."""

    pass


CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[2]


def identify_missing_env_vars(required_env_vars: list) -> list:
    """Check if all required environment variables are available, and report any missing

    Parameters
    ----------
    required_env_vars : list
        List of required environment variables for the current task

    Returns
    -------
    list
        List of missing environment variables. If none missing, returns an empty list
    """

    missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_env_vars:
        logger.warning(
            f"Missing the following required environment variables: {', '.join(missing_env_vars)}"
        )

    return missing_env_vars


def identify_and_load_missing_env_vars(
    required_env_vars: list, dotenv_location: Path = PROJECT_ROOT
):
    """Check if all required environment variables are available.
    If any are missing, attempt to load them from a .env file in the provided location.

    Parameters
    ----------
    required_env_vars : list
        List of required environment variables for the current task
    dotenv_location : Path, optional
        Location to look for the .env file, by default the sar-pipeline project directory

    Raises
    ------
    FileExistsError
        .env file does not exist in provided location
    MissingEnvironmentVariableError
        Required environment variable is missing
    """

    missing_env_vars = identify_missing_env_vars(required_env_vars)

    if missing_env_vars:
        logger.info(
            f"Attempting to load missing environment variables from .env file in {dotenv_location}"
        )

        try:
            loaded_status = load_dotenv(dotenv_location / ".env")

            if not loaded_status:
                # if loading fails, load_dotenv = False
                raise FileExistsError(
                    f"Could not load {dotenv_location / ".env"}. "
                    "Ensure this file exists and contains the required variables."
                )
            else:
                # Check for any remaining missing variables after successfully loading from .env
                missing_env_vars = [
                    var for var in required_env_vars if not os.getenv(var)
                ]
                if missing_env_vars:
                    message = (
                        f".env was found in {dotenv_location} but the following environment variables are still missing: {missing_env_vars}. "
                        f"Add the missing variables to the .env file."
                    )
                    raise MissingEnvironmentVariableError(message)
                else:
                    logger.info("All required environment variables are now loaded.")
        except FileExistsError:
            raise
        except MissingEnvironmentVariableError:
            raise

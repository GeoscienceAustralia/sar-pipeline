from datetime import datetime
from pathlib import Path
import re


def main():
    cophub_dir = Path("/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/")
    config_dir = Path(__file__).parent.parent.joinpath("configuration_files")
    scene_id = "S1A_EW_GRDM_1SDH_20220117T122010_20220117T122115_041500_04EF6B_6437"

    # Regex to extract date and time in the format {YYYY}{MM}{DD}T{HH}{MM}{SS}
    pattern = r"\d{8}T\d{6}"
    matches = re.findall(pattern, scene_id)

     # Regex to extract year, month, day, hour, minute, and second
    detailed_pattern = r"(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})T(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})"
    detailed_matches = [re.match(detailed_pattern, match).groupdict() for match in matches]

    # Extract year and month of first path to provide for file search
    year = detailed_matches[0]["year"]
    month = detailed_matches[0]["month"]

    # Set path on Gadi
    search_path = cophub_dir.joinpath(f"{year}/{year}-{month}/")

    file_path = list(search_path.rglob(f"{scene_id}.zip"))

    if len(file_path) == 1:
        print("Found scene")
        with open(config_dir.joinpath(f"{scene_id}_config.toml"), "w") as f:
            f.write(f'scene = "{file_path[0]}"')
    elif len(file_path) > 1:
        print("More than one file found. Review before proceeding")
    else:
        print("No files found or some other error. Review before proceeding")


if __name__ == "__main__":

    main()
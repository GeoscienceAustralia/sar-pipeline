from pathlib import Path
import pandas as pd
import re
from datetime import datetime

def parse_date(orbit_file_name: str):
    """
    Extracts published_date, start_date, and end_date from the given orbit file.
    Filename example: /g/data/fj7/Copernicus/Sentinel-1/POEORB/S1A/S1A_OPER_AUX_POEORB_OPOD_20141207T123431_V20141115T225944_20141117T005944.EOF
    - Published: 20141207T123431
    - Start: 20141115T225944
    - End: 20141117T005944

    Args:
        file_name (Path): The input file name as a string.

    Returns:
        tuple: a tuple of datetimes for published, start and end of the orbit file
    """
    # Regex pattern to match the dates
    pattern = (r"(?P<published_date>\d{8}T\d{6})_V"
               r"(?P<start_date>\d{8}T\d{6})_"
               r"(?P<stop_date>\d{8}T\d{6})\.EOF")

    # Search for matches in the file name
    match = re.search(pattern, str(orbit_file_name))

    if not match:
        raise ValueError("The input string does not match the expected format.")

    # Extract and parse the dates into datetime objects
    published_date = datetime.strptime(match.group('published_date'), "%Y%m%dT%H%M%S")
    start_date = datetime.strptime(match.group('start_date'), "%Y%m%dT%H%M%S")
    stop_date = datetime.strptime(match.group('stop_date'), "%Y%m%dT%H%M%S")

    return (published_date, start_date, stop_date)

def scan_dir(dir: Path):

    orbit_files = dir.glob('*.EOF')




def main():

    S1_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/")

    ORBIT_DIRS = ["POEORB", "RESORB"]
    SENSORS = ["S1A", "S1B"]

    # orbit_metadata_file = "orbit_metadata.csv"
    # with open(orbit_metadata_file, "w") as f:
    #     f.write("path,sensor,orbit_type,published,start,stop\n")



    generator = 

    for sensor in SENSORS:

        poe_orbit_files = POE_ORBIT_DIR.joinpath(sensor).glob('*.EOF')
        with open(orbit_metadata_file, "a") as f:
            for orbit_file_path in poe_orbit_files:
                published, start, stop = parse_date(str(orbit_file_path))
                
                f.write(f"{str(orbit_file_path)},{sensor},POE,{published},{start},{stop}\n")

        res_orbit_files = RES_ORBIT_DIR.joinpath(sensor).glob('*.EOF')
        with open(orbit_metadata_file, "a") as f:
            for orbit_file_path in res_orbit_files:
                published, start, stop = parse_date(orbit_file_path)
                f.write(f"{str(orbit_file_path)},{sensor},RES,{published},{start},{stop}\n")
    pass

if __name__ == "__main__":

    main()
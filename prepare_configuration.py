from pathlib import Path
import tomli
from pyroSAR import identify
from pyroSAR.S1 import OSV
import re

def main():

    CONFIG_FILE = "S1A_EW_GRDM_1SDH_20220117T122010_20220117T122115_041500_04EF6B_6437_config.toml"
    CONFIG_DIR = Path(__file__).parent.parent.joinpath("configuration_files")
    CONFIG_PATH = CONFIG_DIR.joinpath(CONFIG_FILE)

    ORBIT_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1")

    with open(CONFIG_PATH, "rb") as f:
        config_dict = tomli.load(f)

    scene_path= Path(config_dict["scene"])


    # orbit_file_pattern = r'(?P<sensor>S1[AB])_OPER_AUX_' \
    #                         r'(?P<type>(?:POE|RES)ORB)_OPOD_' \
    #                         r'(?P<publish>[0-9]{8}T[0-9]{6})_V' \
    #                         r'(?P<start>[0-9]{8}T[0-9]{6})_' \
    #                         r'(?P<stop>[0-9]{8}T[0-9]{6})\.EOF'

    if scene_path.exists():
        pyrosar_scene_id = identify(scene_path)
        # timestamp = pyrosar_scene_id.start

        #S1A_OPER_AUX_POEORB_OPOD_20191021T121012_V20190930T225942_20191002T005942.EOF
        ORBIT_PATH = ORBIT_DIR.joinpath(pyrosar_scene_id.sensor)
        orbit_files = ORBIT_PATH.glob('**/*')

        # matches = [re.match(orbit_file_pattern, orbit_file).groupdict() for orbit_file in orbit_files]

        # orbit_file = f"{pyrosar_scene_id.sensor}_OPER_AUX_POEORB_OPOD_"

        # # Find the orbit files that match the given start and end date

        # files = [x for x in locals if self.date(x, 'start') <= timestamp <= self.date(x, 'stop')]

        # ORBIT_PATH = ORBIT_DIR.joinpath(pyrosar_scene_id.sensor)

        # match = OSV(ORBIT_PATH, timeout=300).match(sensor=pyrosar_scene_id.sensor, timestamp=pyrosar_scene_id.start,osvtype="POE")

        # # orbit_file = pyrosar_scene_id.getOSV(osvdir=ORBIT_PATH, osvType='POE', returnMatch=True, useLocal=True)
    else:
        print("Scene not available, download first")


    



    print("done")


if __name__ == "__main__":

    main()
import pystac

RENAME_ASSET_FILETYPES = {
    "_mask.tif": "_mask.tif",
    "_number_of_looks.tif": "_number-of-looks.tif",
    "_rtc_anf_gamma0_to_beta0.tif": "_gamma0-to-beta0-ratio.tif",
    "_rtc_anf_gamma0_to_sigma0.tif": "_gamma0-to-sigma0-ratio.tif",
    "_HH.tif": "_HH-BACKSCATTER-CONVENTION.tif",  # gets replaced in stac.py script
    "_HV.tif": "_HV-BACKSCATTER-CONVENTION.tif",  # gets replaced in stac.py script
    "_VV.tif": "_VV-BACKSCATTER-CONVENTION.tif",  # gets replaced in stac.py script
    "_VH.tif": "_VH-BACKSCATTER-CONVENTION.tif",  # gets replaced in stac.py script
    "_local_incidence_angle.tif": "_local-incidence-angle.tif",
    "_incidence_angle.tif": "_incidence-angle.tif",
    "_interpolated_dem.tif": "_digital-elevation-model.tif",
    ".png": "_thumbnail.png",
}

REQUIRED_ASSET_FILETYPES = {
    "RTC_S1": {
        "gamma0": [
            "_HH-gamma0.tif",
            "_HV-gamma0.tif",
            "_VV-gamma0.tif",
            "_VH-gamma0.tif",
            "_mask.tif",
            "_thumbnail.png",
        ],
        "sigma0": [
            "_HH-sigma0.tif",
            "_HV-sigma0.tif",
            "_VV-sigma0.tif",
            "_VH-sigma0.tif",
            "_mask.tif",
            "_thumbnail.png",
        ],
        "beta0": [
            "_HH-beta0.tif",
            "_HV-beta0.tif",
            "_VV-beta0.tif",
            "_VH-beta0.tif",
            "_mask.tif",
            "_thumbnail.png",
        ],
    },
    "RTC_S1_STATIC": [
        "_number-of-looks.tif",
        "_gamma0-to-beta0-ratio.tif",
        "_gamma0-to-sigma0-ratio.tif",
        "_local-incidence-angle.tif",
        "_incidence-angle.tif",
        "_thumbnail.png",
    ],
}


ASSET_FILETYPE_TO_TITLE = {
    "_mask.tif": "mask",
    "_number-of-looks.tif": "number_of_looks",
    "_gamma0-to-beta0-ratio.tif": "gamma0_to_beta0_ratio",
    "_gamma0-to-sigma0-ratio.tif": "gamma0_to_sigma0_ratio",
    "_HH-gamma0.tif": "HH_gamma0",
    "_HV-gamma0.tif": "HV_gamma0",
    "_VV-gamma0.tif": "VV_gamma0",
    "_VH-gamma0.tif": "VH_gamma0",
    "_HH-sigma0.tif": "HH_sigma0",
    "_HV-sigma0.tif": "HV_sigma0",
    "_VV-sigma0.tif": "VV_sigma0",
    "_VH-sigma0.tif": "VH_sigma0",
    "_HH-beta0.tif": "HH_beta0",
    "_HV-beta0.tif": "HV_beta0",
    "_VV-beta0.tif": "VV_beta0",
    "_VH-beta0.tif": "VH_beta0",
    "_local-incidence-angle.tif": "local_incidence_angle",
    "_incidence-angle.tif": "incidence_angle",
    "_interpolated-dem.tif": "digital_elevation_model",
    "_thumbnail.png": "thumbnail",
}

ASSET_FILETYPE_TO_DESCRIPTION = {
    "_mask.tif": "shadow layover data mask",
    "_number-of-looks.tif": "number of looks",
    "_gamma0-to-beta0-ratio.tif": "backscatter conversion layer, gamma0 to beta0. Eq. beta0 = rtc_anf_gamma0_to_beta0*gamma0",
    "_gamma0-to-sigma0-ratio.tif": "backscatter conversion layer, gamma0 to sigma0. Eq. sigma0 = rtc_anf_sigma0_to_sigma0*gamma0",
    "_HH-gamma0.tif": "HH polarised gamma0 linear backscatter",
    "_HV-gamma0.tif": "HV polarised gamma0 linear backscatter",
    "_VV-gamma0.tif": "VV polarised gamma0 linear backscatter",
    "_VH-gamma0.tif": "VH polarised gamma0 linear backscatter",
    "_HH-sigma0.tif": "HH polarised sigma0 linear backscatter",
    "_HV-sigma0.tif": "HV polarised sigma0 linear backscatter",
    "_VV-sigma0.tif": "VV polarised sigma0 linear backscatter",
    "_VH-sigma0.tif": "VH polarised sigma0 linear backscatter",
    "_HH-beta0.tif": "HH polarised beta0 linear backscatter",
    "_HV-beta0.tif": "HV polarised beta0 linear backscatter",
    "_VV-beta0.tif": "VV polarised beta0 linear backscatter",
    "_VH-beta0.tif": "VH polarised beta0 linear backscatter",
    "_local-incidence-angle.tif": "local incidence angle (LIA)",
    "_incidence-angle.tif": "incidence angle (IA)",
    "_interpolated-dem.tif": "interpolated digital elevation model (DEM)",
    "_thumbnail.png": "thumbnail image for backscatter",
}

ASSET_FILETYPE_TO_ROLES = {
    "_mask.tif": ["data", "auxiliary", "mask", "shadow", "layover"],
    "_number-of-looks.tif": ["data", "auxiliary"],
    "_gamma0-to-beta0-ratio.tif": ["data", "auxiliary", "conversion"],
    "_gamma0-to-sigma0-ratio.tif": ["data", "auxiliary", "conversion"],
    "_HH-gamma0.tif": ["data", "backscatter"],
    "_HV-gamma0.tif": ["data", "backscatter"],
    "_VV-gamma0.tif": ["data", "backscatter"],
    "_VH-gamma0.tif": ["data", "backscatter"],
    "_HH-sigma0.tif": ["data", "backscatter"],
    "_HV-sigma0.tif": ["data", "backscatter"],
    "_VV-sigma0.tif": ["data", "backscatter"],
    "_VH-sigma0.tif": ["data", "backscatter"],
    "_HH-beta0.tif": ["data", "backscatter"],
    "_HV-beta0.tif": ["data", "backscatter"],
    "_VV-beta0.tif": ["data", "backscatter"],
    "_VH-beta0.tif": ["data", "backscatter"],
    "_local-incidence-angle.tif": ["data", "auxiliary"],
    "_incidence-angle.tif": ["data", "auxiliary"],
    "_interpolated-dem.tif": ["data", "ancillary"],
    "_thumbnail.png": ["thumbnail"],
}

ASSET_FILETYPE_TO_MEDIATYPE = {
    "_mask.tif": pystac.media_type.MediaType.COG,
    "_number-of-looks.tif": pystac.media_type.MediaType.COG,
    "_gamma0-to-beta0-ratio.tif": pystac.media_type.MediaType.COG,
    "_gamma0-to-sigma0-ratio.tif": pystac.media_type.MediaType.COG,
    "_HH-gamma0.tif": pystac.media_type.MediaType.COG,
    "_HV-gamma0.tif": pystac.media_type.MediaType.COG,
    "_VV-gamma0.tif": pystac.media_type.MediaType.COG,
    "_VH-gamma0.tif": pystac.media_type.MediaType.COG,
    "_HH-sigma0.tif": pystac.media_type.MediaType.COG,
    "_HV-sigma0.tif": pystac.media_type.MediaType.COG,
    "_VV-sigma0.tif": pystac.media_type.MediaType.COG,
    "_VH-sigma0.tif": pystac.media_type.MediaType.COG,
    "_HH-beta0.tif": pystac.media_type.MediaType.COG,
    "_HV-beta0.tif": pystac.media_type.MediaType.COG,
    "_VV-beta0.tif": pystac.media_type.MediaType.COG,
    "_VH-beta0.tif": pystac.media_type.MediaType.COG,
    "_local-incidence-angle.tif": pystac.media_type.MediaType.COG,
    "_incidence-angle.tif": pystac.media_type.MediaType.COG,
    "_interpolated-dem.tif": pystac.media_type.MediaType.COG,
    "_thumbnail.png": pystac.media_type.MediaType.PNG,
}

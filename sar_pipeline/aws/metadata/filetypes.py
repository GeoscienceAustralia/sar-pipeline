import pystac

REQUIRED_ASSET_FILETYPES = {
    "RTC_S1": [
        "_HH_gamma0.tif",
        "_HV_gamma0.tif",
        "_VV_gamma0.tif",
        "_VH_gamma0.tif",
        "_mask.tif",
        ".png",
    ],
    "RTC_S1_STATIC": [
        "_number_of_looks.tif",
        "_rtc_anf_gamma0_to_beta0.tif",
        "_rtc_anf_gamma0_to_sigma0.tif",
        "_local_incidence_angle.tif",
        "_incidence_angle.tif",
    ],
}

ASSET_FILETYPE_TO_TITLE = {
    "_mask.tif": "mask",
    "_number_of_looks.tif": "number_of_looks",
    "_rtc_anf_gamma0_to_beta0.tif": "gamma0_to_beta0_ratio",
    "_rtc_anf_gamma0_to_sigma0.tif": "gamma0_to_sigma0_ratio",
    "_HH_gamma0.tif": "HH_gamma0",
    "_HV_gamma0.tif": "HV_gamma0",
    "_VV_gamma0.tif": "VV_gamma0",
    "_VH_gamma0.tif": "VH_gamma0",
    "_local_incidence_angle.tif": "local_incidence_angle",
    "_incidence_angle.tif": "incidence_angle",
    "_interpolated_dem.tif": "digital_elevation_model",
    ".png": "thumbnail",
}

ASSET_FILETYPE_TO_DESCRIPTION = {
    "_mask.tif": "shadow layover data mask",
    "_number_of_looks.tif": "number of looks",
    "_rtc_anf_gamma0_to_beta0.tif": "backscatter conversion layer, gamma0 to beta0. Eq. beta0 = rtc_anf_gamma0_to_beta0*gamma0",
    "_rtc_anf_gamma0_to_sigma0.tif": "backscatter conversion layer, gamma0 to sigma0. Eq. sigma0 = rtc_anf_sigma0_to_sigma0*gamma0",
    "_HH_gamma0.tif": "HH polarised gamma0 linear backscatter",
    "_HV_gamma0.tif": "HV polarised gamma0 linear backscatter",
    "_VV_gamma0.tif": "VV polarised gamma0 linear backscatter",
    "_VH_gamma0.tif": "VH polarised gamma0 linear backscatter",
    "_local_incidence_angle.tif": "local incidence angle (LIA)",
    "_incidence_angle.tif": "incidence angle (IA)",
    "_interpolated_dem.tif": "interpolated digital elevation model (DEM)",
    ".png": "thumbnail image for backscatter",
}

ASSET_FILETYPE_TO_ROLES = {
    "_mask.tif": ["data", "auxiliary", "mask", "shadow", "layover"],
    "_number_of_looks.tif": ["data", "auxiliary"],
    "_rtc_anf_gamma0_to_beta0.tif": ["data", "auxiliary", "conversion"],
    "_rtc_anf_gamma0_to_sigma0.tif": ["data", "auxiliary", "conversion"],
    "_HH_gamma0.tif": ["data", "backscatter"],
    "_HV_gamma0.tif": ["data", "backscatter"],
    "_VV_gamma0.tif": ["data", "backscatter"],
    "_VH_gamma0.tif": ["data", "backscatter"],
    "_local_incidence_angle.tif": ["data", "auxiliary"],
    "_incidence_angle.tif": ["data", "auxiliary"],
    "_interpolated_dem.tif": ["data", "ancillary"],
    ".png": ["thumbnail"],
}

ASSET_FILETYPE_TO_MEDIATYPE = {
    "_mask.tif": pystac.media_type.MediaType.COG,
    "_number_of_looks.tif": pystac.media_type.MediaType.COG,
    "_rtc_anf_gamma0_to_beta0.tif": pystac.media_type.MediaType.COG,
    "_rtc_anf_gamma0_to_sigma0.tif": pystac.media_type.MediaType.COG,
    "_HH_gamma0.tif": pystac.media_type.MediaType.COG,
    "_HV_gamma0.tif": pystac.media_type.MediaType.COG,
    "_VV_gamma0.tif": pystac.media_type.MediaType.COG,
    "_VH_gamma0.tif": pystac.media_type.MediaType.COG,
    "_local_incidence_angle.tif": pystac.media_type.MediaType.COG,
    "_incidence_angle.tif": pystac.media_type.MediaType.COG,
    "_interpolated_dem.tif": pystac.media_type.MediaType.COG,
    ".png": pystac.media_type.MediaType.PNG,
}

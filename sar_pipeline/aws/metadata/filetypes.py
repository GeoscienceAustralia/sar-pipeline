import pystac

REQUIRED_ASSET_FILETYPES = {
    "RTC_S1": [
        "_HH.tif",
        "_HV.tif",
        "_VV.tif",
        "_VH.tif",
        ".png",
    ],
    "RTC_S1_STATIC": [
        "_mask.tif",
        "_number_of_looks.tif",
        "_rtc_anf_gamma0_to_beta0.tif",
        "_rtc_anf_gamma0_to_sigma0.tif",
        "_local_incidence_angle.tif",
        "_incidence_angle.tif",
        "_interpolated_dem.tif",
    ],
}

ASSET_FILETYPE_TO_TITLE = {
    "_mask.tif": "mask",
    "_number_of_looks.tif": "number_of_looks",
    "_rtc_anf_gamma0_to_beta0.tif": "gamma0_to_beta0_ratio",
    "_rtc_anf_gamma0_to_sigma0.tif": "gamma0_to_sigma0_ratio",
    "_HH.tif": "HH",
    "_HV.tif": "HV",
    "_VV.tif": "VV",
    "_VH.tif": "VH",
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
    "_HH.tif": "HH polarised backscatter",
    "_HV.tif": "HV polarised backscatter",
    "_VV.tif": "VV polarised backscatter",
    "_VH.tif": "VH polarised backscatter",
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
    "_HH.tif": ["data", "backscatter"],
    "_HV.tif": ["data", "backscatter"],
    "_VV.tif": ["data", "backscatter"],
    "_VH.tif": ["data", "backscatter"],
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
    "_HH.tif": pystac.media_type.MediaType.COG,
    "_HV.tif": pystac.media_type.MediaType.COG,
    "_VV.tif": pystac.media_type.MediaType.COG,
    "_VH.tif": pystac.media_type.MediaType.COG,
    "_local_incidence_angle.tif": pystac.media_type.MediaType.COG,
    "_incidence_angle.tif": pystac.media_type.MediaType.COG,
    "_interpolated_dem.tif": pystac.media_type.MediaType.COG,
    ".png": pystac.media_type.MediaType.PNG,
}

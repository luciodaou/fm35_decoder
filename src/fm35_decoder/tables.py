"""
WMO Code Tables for FM 35-XII TEMP Decoding.
Based on WMO Manual on Codes, WMO-No. 306, Volume I.1.
All tables are precompiled as in-memory Python dictionaries for 0 ms lookup overhead.
"""

from typing import Any, Dict

# WMO Code Table 3931 - Ta: Approximate tenths of degree Celsius and its sign
TABLE_T_3931: Dict[str, Dict[str, Any]] = {
    "0": {"Sign": "+", "TenthsValue": 0.0},
    "1": {"Sign": "-", "TenthsValue": 0.1},
    "2": {"Sign": "+", "TenthsValue": 0.2},
    "3": {"Sign": "-", "TenthsValue": 0.3},
    "4": {"Sign": "+", "TenthsValue": 0.4},
    "5": {"Sign": "-", "TenthsValue": 0.5},
    "6": {"Sign": "+", "TenthsValue": 0.6},
    "7": {"Sign": "-", "TenthsValue": 0.7},
    "8": {"Sign": "+", "TenthsValue": 0.8},
    "9": {"Sign": "-", "TenthsValue": 0.9},
}

# WMO Code Table 0777 - DaDa: Dew-point depression in Celsius
# Codes 00-50: 0.0 to 5.0 C (in tenths of a degree)
# Codes 56-99: 6 to 49 C (in whole degrees, DaDa - 50)
# Code 99 indicates depression of 49 C or more
TABLE_D_0777: Dict[str, Dict[str, Any]] = {}
for i in range(51):
    code_str = f"{i:02d}"
    TABLE_D_0777[code_str] = {"Value": round(i / 10.0, 1), "Description": f"{round(i / 10.0, 1)} °C"}

# 51-55 are reserved / not used in WMO 0777
for i in range(51, 56):
    TABLE_D_0777[f"{i:02d}"] = {"Value": None, "Description": "Not used"}

# 56-99: 6.0 to 49.0 C
for i in range(56, 100):
    val = float(i - 50)
    desc = f"{int(val)} °C or more" if i == 99 else f"{int(val)} °C"
    TABLE_D_0777[f"{i:02d}"] = {"Value": val, "Description": desc}

TABLE_D_0777["//"] = {"Value": None, "Description": "No humidity data available"}

# WMO Code Table 2700 - Nh: Amount of all CL cloud present or CM if no CL
TABLE_Nh_2700: Dict[str, str] = {
    "0": "No clouds",
    "1": "1 okta or less, but not zero",
    "2": "2 oktas",
    "3": "3 oktas",
    "4": "4 oktas",
    "5": "5 oktas",
    "6": "6 oktas",
    "7": "7 oktas or more, but not 8 oktas",
    "8": "8 oktas",
    "9": "Sky obscured, or cloud amount cannot be estimated",
    "/": "No measurement made",
}

# WMO Code Table 0513 - CL: Clouds of the genera Stratocumulus, Stratus, Cumulus, and Cumulonimbus
TABLE_CL_0513: Dict[str, str] = {
    "0": "No CL clouds",
    "1": "Cumulus humilis and/or Cumulus fractus other than of bad weather",
    "2": "Cumulus mediocris or congestus, with or without Cumulus of species in code 1",
    "3": "Cumulonimbus calvus, with or without Cumulus, Stratocumulus or Stratus",
    "4": "Stratocumulus cumulogenitus",
    "5": "Stratocumulus other than cumulogenitus",
    "6": "Stratus nebulosus and/or Stratus fractus other than of bad weather",
    "7": "Stratus fractus and/or Cumulus fractus of bad weather",
    "8": "Cumulus and Stratocumulus other than cumulogenitus, with bases at different levels",
    "9": "Cumulonimbus capillatus, with or without Cumulonimbus calvus, Cumulus, Stratocumulus, Stratus",
    "/": "CL clouds invisible owing to darkness, fog, blowing dust or sand, or other similar phenomena",
}

# WMO Code Table 1600 - h: Height of base of lowest cloud
TABLE_h_1600: Dict[str, str] = {
    "0": "< 50 m (< 150 ft)",
    "1": "50-100 m (150-300 ft)",
    "2": "100-200 m (300-600 ft)",
    "3": "200-300 m (600-1000 ft)",
    "4": "300-600 m (1000-2000 ft)",
    "5": "600-1000 m (2000-3300 ft)",
    "6": "1000-1500 m (3300-5000 ft)",
    "7": "1500-2000 m (5000-6500 ft)",
    "8": "2000-2500 m (6500-8000 ft)",
    "9": "> 2500 m (> 8000 ft), or no clouds",
    "/": "Cloud base height not known or not given",
}

# WMO Code Table 0515 - CM: Clouds of the genera Altocumulus, Altostratus, and Nimbostratus
TABLE_CM_0515: Dict[str, str] = {
    "0": "No CM clouds",
    "1": "Altostratus translucidus",
    "2": "Altostratus opacus or Nimbostratus",
    "3": "Altocumulus translucidus at a single level",
    "4": "Patches of Altocumulus translucidus (lenticular)",
    "5": "Altocumulus translucidus in bands (invading sky)",
    "6": "Altocumulus cumulogenitus",
    "7": "Altocumulus translucidus or opacus in two or more layers",
    "8": "Altocumulus castellanus or floccus",
    "9": "Altocumulus of a chaotic sky (usually at several levels)",
    "/": "CM clouds invisible",
}

# WMO Code Table 0509 - CH: Clouds of the genera Cirrus, Cirrocumulus, and Cirrostratus
TABLE_CH_0509: Dict[str, str] = {
    "0": "No CH clouds",
    "1": "Cirrus fibratus (uncinus)",
    "2": "Cirrus spissatus (dense)",
    "3": "Cirrus spissatus cumulonimbogenitus",
    "4": "Cirrus uncinus or fibratus (invading sky)",
    "5": "Cirrus and Cirrostratus (invading, < 45 deg)",
    "6": "Cirrus and Cirrostratus (invading, > 45 deg)",
    "7": "Cirrostratus covering the whole sky",
    "8": "Cirrostratus not covering the whole sky and not invading",
    "9": "Cirrocumulus alone, or with Cirrus/Cirrostratus",
    "/": "CH clouds invisible",
}

# WMO Code Table 3849 - sr: Solar and infrared radiation correction
TABLE_Sr_3849: Dict[str, str] = {
    "0": "No correction",
    "1": "CIMO solar corrected",
    "2": "CIMO solar and infrared corrected",
    "3": "CIMO cloud corrected",
    "4": "NOAA solar corrected",
    "5": "National solar corrected",
    "6": "National solar and infrared corrected",
    "7": "National cloud corrected",
    "/": "Missing value",
}

# WMO Code Table 3872 - sasa: Tracking technique and status of system used
TABLE_sasa_3872: Dict[str, str] = {
    "00": "No wind finding",
    "01": "Optical theodolite",
    "02": "Radiotheodolite (2.4 GHz)",
    "03": "Radiotheodolite (403 MHz)",
    "04": "Radio direction-finder",
    "05": "Radar (10 cm) without transponder",
    "06": "Radar (10 cm) with transponder",
    "07": "Radar (10 cm)",
    "08": "Radar (5 cm)",
    "09": "Radar (3 cm)",
    "10": "Secondary surveillance radar",
    "11": "Radar with automated tracking",
    "12": "Wind profiler",
    "13": "Loran-C",
    "14": "Argos Doppler",
    "15": "VLF",
    "16": "Omega",
    "17": "GPS (differential)",
    "18": "GPS (relative)",
    "19": "GPS (standalone / autonomous)",
    "20": "VLF-Omega",
    "21": "GLONASS",
    "22": "Galileo",
    "23": "BeiDou",
    "24": "Multi-GNSS (GPS/GLONASS/Galileo)",
    "//": "Tracking system unknown or missing",
}

# WMO Common Code Table C-2 / Code Table 3685 - rara: Radiosonde type
# Contains both historical instruments and modern digital sounding units
TABLE_rara_3685: Dict[str, str] = {
    "00": "Reserved",
    "01": "iMet-1-BB (United States)",
    "02": "No radiosonde - passive target (reflector)",
    "03": "No radiosonde - active target (transponder)",
    "04": "No radiosonde - passive temperature-humidity profiler",
    "05": "No radiosonde - active temperature-humidity profiler",
    "06": "No radiosonde - radio-acoustic sounder",
    "07": "iMet-1-AB (United States)",
    "08": "iMet-2 (United States)",
    "09": "No radiosonde - system unknown or not specified",
    "10": "VIZ type A pressure-commutated (United States)",
    "11": "VIZ type B time-commutated (United States)",
    "12": "RS SDC (Space Data Corporation - United States)",
    "13": "Astor (Australia)",
    "14": "VIZ MARK I MICROSONDE (United States)",
    "15": "EEC Company type 23 (United States)",
    "16": "Elin (Austria)",
    "17": "GRAW G. (Germany)",
    "18": "GRAW DFM-06 (Germany)",
    "19": "GRAW M60 (Germany)",
    "20": "Indian Meteorological Service MK3 (India)",
    "21": "VIZ/Jin Yang MARK I MICROSONDE (Republic of Korea)",
    "22": "Meisei RS2-80 (Japan)",
    "23": "Mesural FMO 1950A (France)",
    "24": "Mesural FMO 1945A (France)",
    "25": "Mesural MH73A (France)",
    "26": "Meteolabor Basora (Switzerland)",
    "27": "AVK-MRZ (Russian Federation)",
    "28": "Meteorit MARZ2-1 (Russian Federation)",
    "29": "Meteorit MARZ2-2 (Russian Federation)",
    "30": "Oki RS2-80 (Japan)",
    "31": "VIZ/Valcom type A pressure-commutated (Canada)",
    "32": "Shanghai Radio (China)",
    "33": "UK Met Office MK3 (UK)",
    "34": "Vinohrady (Czechia)",
    "35": "Vaisala RS18 (Finland)",
    "36": "Vaisala RS21 (Finland)",
    "37": "Vaisala RS80 (Finland)",
    "38": "VIZ LOCATE Loran-C (United States)",
    "39": "Sprenger E076 (Germany)",
    "40": "Sprenger E084 (Germany)",
    "41": "Sprenger E085 (Germany)",
    "42": "Sprenger E086 (Germany)",
    "43": "AIR IS - 4A - 1680 (United States)",
    "44": "AIR IS - 4A - 1680 X (United States)",
    "45": "RS MSS (United States)",
    "46": "AIR IS - 4A - 403 (United States)",
    "47": "Meisei RS2-91 (Japan)",
    "48": "VALCOM (Canada)",
    "49": "VIZ MARK II (United States)",
    "50": "GZK (Russian Federation)",
    "51": "Vaisala RS90 (Finland)",
    "52": "Vaisala RS92 / DigiCORA (Finland)",
    "53": "Meteolabor Snow White (Switzerland)",
    "54": "Sippican MARK II Microsonde (United States)",
    "55": "GRAW DFM-97 (Germany)",
    "56": "Meteomodem M2K2 (France)",
    "57": "Modem M10 (France)",
    "58": "Modem M20 (France)",
    "59": "Lockheed Martin Sippican LMS-6 (United States)",
    "60": "Meisei RS-01G (Japan)",
    "61": "Vaisala RS41 / DigiCORA MW41 (Finland)",
    "62": "Vaisala RS41-SGP (Finland)",
    "63": "GRAW DFM-09 (Germany)",
    "64": "GRAW DFM-17 (Germany)",
    "65": "Meisei iMS-100 (Japan)",
    "66": "InterMet iMet-4 (United States)",
    "67": "InterMet iMet-54 (United States)",
    "68": "Meteo-France Meteomodem GPS (France)",
    "69": "Cangzhou GTS1-2 (China)",
    "70": "Nanjing GTS1-1 (China)",
    "71": "Huayun GTS1 (China)",
    "72": "Taiyuan GTS1 (China)",
    "73": "Shanghai Changji GTS1 (China)",
    "74": "Vaisala RS92-NGP (Finland)",
    "75": "Vaisala RS92-SGP (Finland)",
    "76": "Jinyang RSG-20A (Republic of Korea)",
    "77": "AVK-BAR (Russian Federation)",
    "78": "Radiosonde-1 (Russian Federation)",
    "79": "PAZA-22 (Russian Federation)",
    "80": "Vaisala RS41-SG (Finland)",
    "81": "Vaisala RS41-SGM (Finland)",
    "82": "GRAW DFM-17 GPS (Germany)",
    "83": "Meisei RS-11G (Japan)",
    "99": "Missing or unknown radiosonde type",
    "//": "Radiosonde type missing",
}

# Standard Atmosphere reference geopotential heights (in meters)
# Extended up to 1 hPa (mesosphere) based on US Standard Atmosphere 1976 / ICAO Standard Atmosphere
STANDARD_ATMOSPHERE_HEIGHTS: Dict[int, int] = {
    1000: 111,
    925: 762,
    850: 1457,
    700: 3012,
    500: 5574,
    400: 7185,
    300: 9164,
    250: 10363,
    200: 11784,
    150: 13608,
    100: 16180,
    70: 18440,
    50: 20580,
    30: 23850,
    20: 26500,
    10: 31050,
    7: 33500,
    5: 35800,
    3: 39500,
    2: 42500,
    1: 47800,
}

# Master code dictionary registry for decoder lookup
WMO_TABLES: Dict[str, Any] = {
    "T_3931": TABLE_T_3931,
    "D_0777": TABLE_D_0777,
    "Nh": TABLE_Nh_2700,
    "CL": TABLE_CL_0513,
    "h": TABLE_h_1600,
    "CM": TABLE_CM_0515,
    "CH": TABLE_CH_0509,
    "Sr": TABLE_Sr_3849,
    "sasa": TABLE_sasa_3872,
    "rara": TABLE_rara_3685,
}

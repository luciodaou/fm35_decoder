"""
WMO Code Tables for FM 35-XII TEMP Decoding.
Based on WMO Manual on Codes, WMO-No. 306, Volume I.1.
All tables are precompiled as in-memory Python dictionaries for 0 ms lookup overhead.
"""

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

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
    TABLE_D_0777[f"{i:02d}"] = {"Value": val, "Description": f"{int(val)} °C"}

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

# WMO Code Table 3849 - sr: Solar and infrared radiation correction (WMO-No. 306 Vol I.1, 2019)
TABLE_Sr_3849: Dict[str, str] = {
    "0": "No correction",
    "1": "CIMO solar corrected and CIMO infrared corrected",
    "2": "CIMO solar corrected and infrared corrected",
    "3": "CIMO solar corrected only",
    "4": "Solar and infrared corrected automatically by radiosonde system",
    "5": "Solar corrected automatically by radiosonde system",
    "6": "Solar and infrared corrected as specified by country",
    "7": "Solar corrected as specified by country",
    "/": "Missing value",
}

# WMO Common Code Tables C-2 (rara, code table 3685) and C-7 (sasa, code table 3872).
# Source: official WMO CSVs, https://github.com/wmo-im/CCT (C02.csv, C07.csv) at commit
# 8d5866c2a7b4697d0ac9af332a7706ca931f7fff, vendored in table_codes/. The in-memory
# dictionaries below are generated from those files with build_rara_table / build_sasa_table
# (a test checks they stay identical).

# Assignments dated after this date are not used yet (e.g. C-2 139, assigned from 01/02/2027)
TABLES_BUILD_DATE = date(2026, 10, 6)

_NOT_ASSIGNED = ("not vacant", "vacant", "reserved for bufr only")


def _expand_codes(code: str) -> List[str]:
    """Expands a 2-digit code or range ("55-59") into a list of 2-digit codes."""
    code = code.strip()
    if re.fullmatch(r"\d{2}", code):
        return [code]
    match = re.fullmatch(r"(\d{2})-(\d{2})", code)
    if match:
        return [f"{n:02d}" for n in range(int(match.group(1)), int(match.group(2)) + 1)]
    return []


def _assignment_date(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def build_rara_table(rows: Iterable[Mapping[str, str]], as_of: date = TABLES_BUILD_DATE) -> Dict[str, str]:
    """
    Builds the 2-digit rara table from Common Code Table C-2 rows.
    TEMP reports only the last two digits of C-2. When a code has both a legacy assignment
    (BUFR 0-99) and a newer one (BUFR 101-189), the newer assignment is used, unless it is
    not a real assignment ("Not vacant", "Vacant", "Reserved for BUFR only") or is dated after as_of.
    """
    legacy: Dict[str, str] = {}
    newer: Dict[str, str] = {}
    for row in rows:
        desc = row["RadiosondeSoundingSystemUsed_en"].strip()
        bufr = row["CodeFigureForBUFR"].strip()
        for code in _expand_codes(row["CodeFigureForrara"]):
            if bufr.isdigit() and int(bufr) < 100:
                legacy[code] = desc
            elif desc.lower() not in _NOT_ASSIGNED:
                assigned = _assignment_date(row["DateOfAssignment_en"])
                if assigned is None or assigned <= as_of:
                    newer[code] = desc
    table = {**legacy, **newer}
    return {code: table[code] for code in sorted(table)}


def build_sasa_table(rows: Iterable[Mapping[str, str]]) -> Dict[str, str]:
    """Builds the 2-digit sasa table from Common Code Table C-7 rows (heading rows are skipped)."""
    table: Dict[str, str] = {}
    for row in rows:
        desc = row["TrackingTechniquesStatusOfSystemUsed_en"].strip()
        for code in _expand_codes(row["CodeFigureForsasa"]):
            table[code] = desc
    table["//"] = "Missing"
    return table


# Code table 3685 - rara: Radiosonde/sounding system used (Common Code Table C-2)
TABLE_rara_3685: Dict[str, str] = {
    '00': 'Reserved',
    '01': 'iMet-1-BB (United States)',
    '02': 'No radiosonde - passive target (e.g. reflector)',
    '03': 'No radiosonde - active target (e.g. transponder)',
    '04': 'No radiosonde - passive temperature-humidity profiler',
    '05': 'No radiosonde - active temperature-humidity profiler',
    '06': 'No radiosonde - radio-acoustic sounder',
    '07': 'iMet-1-AB (United States)',
    '08': 'No radiosonde -... (reserved)',
    '09': 'No radiosonde - system unknown or not specified',
    '10': 'Sippican LMS5 w/Chip Thermistor, duct mounted capacitance relative humidity sensor and derived pressure from GPS height',
    '11': 'Sippican LMS6 w/Chip Thermistor, external boom mounted capacitance relative humidity sensor, and derived pressure from GPS height',
    '12': 'Jin Yang RSG-20A with derived pressure from GPS height/GL-5000P (Republic of Korea)',
    '13': 'Vaisala RS92/MARWIN MW32 (Finland)',
    '14': 'Vaisala RS92/DigiCORA MW41 (Finland)',
    '15': 'PAZA-12M/Radiotheodolite-UL (Ukraine)',
    '16': 'PAZA-22/AVK-1 (Ukraine)',
    '17': 'Graw DFM-09 (Germany)',
    '18': 'Graw DFM-06 (Germany)',
    '19': 'Polus-MRZ-N1 (Russian Federation)',
    '20': 'Indian Meteorological Service MK3 (India)',
    '21': 'Jin Yang 1524LA LORAN-C/GL5000 (Republic of Korea)',
    '22': 'Meisei RS-11G GPS radiosonde w/thermistor, capacitance relative humidity sensor, and derived pressure from GPS height (Japan)',
    '23': 'Vaisala RS41/DigiCORA MW41 (Finland)',
    '24': 'Vaisala RS41/AUTOSONDE (Finland)',
    '25': 'Vaisala RS41/MARWIN MW32 (Finland)',
    '26': 'Meteolabor SRS-C34/Argus 37 (Switzerland)',
    '27': 'AVK-MRZ (Russian Federation)',
    '28': 'AVK - AK2-02 (Russian Federation)',
    '29': 'MARL-A or Vektor-M - AK2-02 (Russian Federation)',
    '30': 'Meisei RS-06G (Japan)',
    '31': 'Taiyuan GTS1-1/GFE(L) (China )',
    '32': 'Shanghai GTS1/GFE(L) (China)',
    '33': 'Nanjing GTS1-2/GFE(L) (China)',
    '34': 'iMet-4 GPS radiosonde (USA)',
    '35': 'Meisei iMS-100 GPS radiosonde w/thermistor sensor, capacitance relative humidity sensor, and derived pressure from GPS height (Japan)',
    '36': 'Meisei iMDS-17 GPS dropsonde w/thermistor sensor, capacitance relative humidity sensor, and capacitance pressure sensor (Japan)',
    '37': 'Vaisala RS80 (Finland)',
    '38': 'WEATHEX WxR-301D with derived pressure from GPS (Republic of Korea)',
    '39': 'Sprenger E076 (Germany)',
    '40': 'Sprenger E084 (Germany)',
    '41': 'Vaisala RS41 with pressure derived from GPS height/DigiCORA MW41 (Finland)',
    '42': 'Vaisala RS41 with pressure derived from GPS height/AUTOSONDE (Finland)',
    '43': 'NanJing Daqiao XGP-3G (China)*',
    '44': 'TianJin HuaYunTianYi GTS(U)1 (China)*',
    '45': 'Beijing Changfeng CF-06 (China)*',
    '46': 'Shanghai Changwang GTS3 (China)*',
    '47': 'Meisei RS2-91 (Japan)',
    '48': 'PAZA-22M/MARL-A',
    '49': 'VIZ MARK II (United States)',
    '50': 'Meteolabor SRS-C50/Argus (Switzerland)',
    '51': 'VIZ-B2 (United States)',
    '52': 'Vaisala RS92-NGP/Intermet IMS-2000 (United States)',
    '53': 'AVK - I-2012 (Russian Federation)',
    '54': 'Graw DFM-17 (Germany)',
    '55': 'Meisei RS-01G (Japan)',
    '56': 'M2K2 (France)',
    '57': 'Modem M2K2-DC (France)',
    '58': 'AVK-BAR (Russian Federation)',
    '59': 'Modem M2K2-R 1680 MHz RDF radiosonde with pressure sensor chip (France)',
    '60': 'MARL-A or Vektor-M - I-2012 (Russian Federation)',
    '61': 'Vaisala RS80/Loran/Digicora I, II or Marwin (Finland)',
    '62': 'MARL-A or Vektor-M - MRZ-3MK (Russian Federation)',
    '63': 'Modem M20 radiosonde w/thermistor sensor, capacitance relative humidity sensor, and derived pressure from GPS height (France)',
    '64': 'Modem PilotSonde GPS radiosonde (France)',
    '65': 'Meteosis MTS-01 (Turkiye)',
    '66': 'Vaisala RS80 /Autosonde (Finland)',
    '67': 'Vaisala RS80/Digicora III (Finland)',
    '68': 'AVK-RZM-2 (Russian Federation)',
    '69': 'MARL-A or Vektor-M-RZM-2 (Russian Federation)',
    '70': 'Vaisala RS92/Star (Finland)',
    '71': 'Vaisala RS90/Loran/Digicora I, II or Marwin (Finland)',
    '72': 'Vaisala RS90/PC-Cora (Finland)',
    '73': 'МARL-A (Russian Federation) - ASPAN-15 (Kazakhstan)',
    '74': 'Vaisala RS90/Star (Finland)',
    '75': 'AVK-MRZ-ARMA (Russian Federation)',
    '76': 'AVK-RF95-ARMA (Russian Federation)',
    '77': 'Modem GPSonde M10 (France)',
    '78': 'Vaisala RS90/Digicora III (Finland)',
    '79': 'Vaisala RS92/Digicora I,II or Marwin (Finland)',
    '80': 'Vaisala RS92/Digicora III (Finland)',
    '81': 'Vaisala RS92/Autosonde (Finland)',
    '82': 'Lockheed Martin LMS-6 w/chip thermistor; external boom mounted polymer capacitive relative humidity sensor; capacitive pressure sensor and GPS wind',
    '83': 'Vaisala RS92-D/Intermet IMS 1500 w/silicon capacitive pressure sensor, capacitive wire temperature sensor, twin thin-film heated polymer capacitive relative humidity sensor and RDF wind',
    '84': 'iMet-54/iMet-3200/3400 GPS radiosonde with derived pressure from GPS height (South Africa)',
    '85': 'Sippican MARK IIA with chip thermistor, carbon element and derived pressure from GPS height',
    '86': 'Sippican MARK II with chip thermistor, pressure and carbon element',
    '87': 'Sippican MARK IIA with chip thermistor, pressure and carbon element',
    '88': 'MARL-A or Vektor-M-MRZ (Russian Federation)',
    '89': 'MARL-A or Vektor-M-BAR (Russian Federation)',
    '90': 'Radiosonde not specified or unknown',
    '91': 'Pressure only radiosonde',
    '92': 'Pressure only radiosonde plus transponder',
    '93': 'Pressure only radiosonde plus radar reflector',
    '94': 'No pressure radiosonde plus transponder',
    '95': 'No pressure radiosonde plus radar reflector',
    '96': 'Descending radiosonde',
    '97': 'iMet-2/iMet-1500 RDF radiosonde with pressure sensor chip (South Africa)',
    '98': 'iMet-2/iMet-1500 GPS radiosonde with derived pressure from GPS height (South Africa)',
    '99': 'iMet-2/iMet-3200 GPS radiosonde with derived pressure from GPS height (South Africa)',
}

# Code table 3872 - sasa: Tracking technique/status of system used (Common Code Table C-7)
TABLE_sasa_3872: Dict[str, str] = {
    '00': 'No wind finding',
    '01': 'Automatic with auxiliary optical direction finding',
    '02': 'Automatic with auxiliary radio direction finding',
    '03': 'Automatic with auxiliary ranging',
    '04': 'Not used',
    '05': 'Automatic with multiple VLF-Omega signals',
    '06': 'Automatic cross chain Loran-C',
    '07': 'Automatic with auxiliary wind profiler',
    '08': 'Automatic satellite navigation',
    '09': 'Reserved',
    '10': 'Reserved',
    '11': 'Reserved',
    '12': 'Reserved',
    '13': 'Reserved',
    '14': 'Reserved',
    '15': 'Reserved',
    '16': 'Reserved',
    '17': 'Reserved',
    '18': 'Reserved',
    '19': 'Tracking technique not specified',
    '20': 'Vessel stopped',
    '21': 'Vessel diverted from original destination',
    '22': "Vessel's arrival delayed",
    '23': 'Container damaged',
    '24': 'Power failure to container',
    '25': 'Reserved for future use',
    '26': 'Reserved for future use',
    '27': 'Reserved for future use',
    '28': 'Reserved for future use',
    '29': 'Other problems',
    '30': 'Major power problems',
    '31': 'UPS inoperative',
    '32': 'Receiver hardware problems',
    '33': 'Receiver software problems',
    '34': 'Processor hardware problems',
    '35': 'Processor software problems',
    '36': 'NAVAID system damaged',
    '37': 'Shortage of lifting gas',
    '38': 'Reserved',
    '39': 'Other problems',
    '40': 'Mechanical defect',
    '41': 'Material defect (hand launcher)',
    '42': 'Power failure',
    '43': 'Control failure',
    '44': 'Pneumatic/hydraulic failure',
    '45': 'Other problems',
    '46': 'Compressor problems',
    '47': 'Balloon problems',
    '48': 'Balloon release problems',
    '49': 'Launcher damaged',
    '50': 'R/S receiver antenna defect',
    '51': 'NAVAID antenna defect',
    '52': 'R/S receiver cabling (antenna) defect',
    '53': 'NAVAID antenna cabling defect',
    '54': 'Reserved',
    '55': 'Reserved',
    '56': 'Reserved',
    '57': 'Reserved',
    '58': 'Reserved',
    '59': 'Other problems',
    '60': 'ASAP communications defect',
    '61': 'Communications facility rejected data',
    '62': 'No power at transmitting antenna',
    '63': 'Antenna cable broken',
    '64': 'Antenna cable defect',
    '65': 'Message transmitted power below normal',
    '66': 'Reserved',
    '67': 'Reserved',
    '68': 'Reserved',
    '69': 'Other problems',
    '70': 'All systems in normal operation',
    '71': 'Reserved',
    '72': 'Reserved',
    '73': 'Reserved',
    '74': 'Reserved',
    '75': 'Reserved',
    '76': 'Reserved',
    '77': 'Reserved',
    '78': 'Reserved',
    '79': 'Reserved',
    '80': 'Reserved',
    '81': 'Reserved',
    '82': 'Reserved',
    '83': 'Reserved',
    '84': 'Reserved',
    '85': 'Reserved',
    '86': 'Reserved',
    '87': 'Reserved',
    '88': 'Reserved',
    '89': 'Reserved',
    '90': 'Reserved',
    '91': 'Reserved',
    '92': 'Reserved',
    '93': 'Reserved',
    '94': 'Reserved',
    '95': 'Reserved',
    '96': 'Reserved',
    '97': 'Reserved',
    '98': 'Reserved',
    '99': 'Status of system and its components not specified',
    '//': 'Missing',
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

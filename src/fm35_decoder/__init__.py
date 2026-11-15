"""
Decoder of WMO FM 35 TEMP and FM 32 PILOT upper-air reports (and their ship and dropsonde
forms), based on the GEMPAK upper-air decoder.
"""

from .bulletin import Bulletin, iter_bulletins, iter_reports
from .decoder import decode, decode_full, decode_soundings, iter_decoded_reports, to_dataframes
from .merge import merge_parts, merge_reports
from .models import (
    DecodeError,
    LevelType,
    MergedSounding,
    MissingLayer,
    Platform,
    ReportPart,
    SoundingLevel,
    SoundingReport,
    SoundingSystem,
    StationMetadata,
    WindUnit,
    WmoHeader,
)
from .parts import parse_report
from .stations import load_station_table

__version__ = "2.0.2"

__all__ = [
    "Bulletin",
    "DecodeError",
    "LevelType",
    "MergedSounding",
    "MissingLayer",
    "Platform",
    "ReportPart",
    "SoundingLevel",
    "SoundingReport",
    "SoundingSystem",
    "StationMetadata",
    "WindUnit",
    "WmoHeader",
    "decode",
    "decode_full",
    "decode_soundings",
    "iter_bulletins",
    "iter_decoded_reports",
    "iter_reports",
    "load_station_table",
    "merge_parts",
    "merge_reports",
    "parse_report",
    "to_dataframes",
]

"""
Entry points: decoding a stream of bulletins into soundings, and `decode`, which takes the
parts of one sounding and returns two DataFrames as in version 1.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, Union

import pandas as pd

from .bulletin import iter_bulletins, iter_reports
from .groups import KT_TO_MS
from .merge import merge_parts, merge_reports
from .models import (
    DecodeError,
    LevelType,
    MergedSounding,
    ReportPart,
    SoundingLevel,
    SoundingReport,
    StationMetadata,
    WindUnit,
)
from .parts import parse_report
from .tables import WMO_TABLES, load_wmo_tables

__all__ = ["decode", "decode_full", "decode_soundings", "iter_decoded_reports", "to_dataframes", "load_wmo_tables"]

log = logging.getLogger("fm35_decoder")

MAIN_COLUMNS = ["Pressure", "Height", "Temp", "DewPoint", "WindDir", "WindSpeed", "Source", "Derived"]
SPECIAL_COLUMNS = ["Symbol", "Subject", "Description", "Value", "Part"]

_DERIVED_NAMES = {
    "pressure_hpa": "Pressure",
    "height_m": "Height",
    "temp_c": "Temp",
    "dewpoint_c": "DewPoint",
    "wind_dir_deg": "WindDir",
    "wind_speed_ms": "WindSpeed",
}


def iter_decoded_reports(
    source: Union[str, Iterable[str]], reference_time: Optional[datetime] = None
) -> Iterator[SoundingReport]:
    """
    Decodes every report of a text, a file object or an iterable of lines, one at a time:
    bulletins, then the reports of each, then the parts. A report whose header cannot be
    decoded is logged and left out, and the reports after it are still decoded.
    """
    for bulletin in iter_bulletins(source):
        for text in iter_reports(bulletin.text):
            try:
                yield parse_report(text, bulletin.header, reference_time)
            except DecodeError as error:
                log.warning("report left out: %s", error)


def decode_soundings(
    source: Union[str, Iterable[str]],
    reference_time: Optional[datetime] = None,
    station_table: Optional[Dict[str, StationMetadata]] = None,
    interpolate: bool = False,
) -> List[MergedSounding]:
    """
    Decodes every report of `source` and merges the parts of each sounding (same station and
    same time, rounded to 3 hours). `reference_time` is when the reports were received: it
    gives the year and the month of the observations (now, when not given).
    """
    return merge_reports(iter_decoded_reports(source, reference_time), station_table, interpolate)


def _speed(speed_ms: float, unit: str) -> float:
    return round(speed_ms / KT_TO_MS, 1) if unit == "kt" else round(speed_ms, 1)


def _wind_text(level: SoundingLevel, unit: WindUnit) -> str:
    assert level.wind_dir_deg is not None and level.wind_speed_ms is not None
    return f"{int(level.wind_dir_deg)}/{round(_speed(level.wind_speed_ms, unit.value))}{unit.value}"


def _special_rows(report: SoundingReport, tables: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    unit = report.wind_unit
    above = report.part.above_100hpa

    def add(symbol: str, subject: str, description: str, value: str) -> None:
        rows.append({"Symbol": symbol, "Subject": subject, "Description": description, "Value": value})

    def pressure(level: SoundingLevel) -> str:
        return f"{level.pressure_hpa:.1f}hPa" if above else f"{level.pressure_hpa:g}hPa"

    for level in report.of_type(LevelType.TROPOPAUSE):
        add("PtPtPt", "Tropopause", "Pressure", pressure(level))
        if level.temp_c is not None:
            add("TtTtTt", "Tropopause", "Temperature", f"{level.temp_c}C")
        if level.dewpoint_c is not None:
            add("DtDt", "Tropopause", "Dewpoint", f"{level.dewpoint_c}C")
        if level.wind_speed_ms is not None:
            add("dtdtftft", "Tropopause", "Wind", _wind_text(level, unit))

    for level in report.of_type(LevelType.MAX_WIND):
        add("PmPmPm", "Max Wind", "Pressure", pressure(level))
        add("dmdmfmfmfm", "Max Wind", "Wind", _wind_text(level, unit))
        for symbol, description, shear in (
            ("vbvb", "Shear Below", level.shear_below_ms),
            ("vava", "Shear Above", level.shear_above_ms),
        ):
            if shear is not None:
                add(symbol, "Max Wind", description, f"{round(_speed(shear, unit.value)):02d}{unit.value}")

    for layer in report.missing_layers:
        description = "Temperature" if layer.kind is LevelType.SIG_TEMP else "Wind"
        add("nn///", "Missing Data", description, f"{layer.bottom_hpa:g}-{layer.top_hpa:g}hPa")

    system = report.sounding_system
    if system is not None:
        for symbol, description, key, code in (
            ("sr", "Solar Corr", "Sr", system.radiation_correction),
            ("rara", "Sonde Type", "rara", system.radiosonde),
            ("sasa", "Tracking", "sasa", system.tracking),
        ):
            if code is not None:
                add(symbol, "Solar/Inst", description, tables.get(key, {}).get(code, code))
        if system.launch_time is not None:
            add("8GGgg", "Solar/Inst", "Time", system.launch_time)

    if report.cloud_group is not None:
        for (symbol, description), code in zip(
            (("Nh", "Amount"), ("CL", "Low Type"), ("h", "Base Height"), ("CM", "Mid Type"), ("CH", "High Type")),
            report.cloud_group,
        ):
            add(symbol, "Cloud", description, tables.get(symbol, {}).get(code, code))

    for row in rows:
        row["Part"] = report.part.value
    return rows


def to_dataframes(sounding: MergedSounding, wind_unit: str = "kt") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    A merged sounding as two DataFrames.

    - df_main: the profile, surface first, with Pressure (hPa), Height (m), Temp and DewPoint
      (C), WindDir (degrees), WindSpeed (in `wind_unit`, "kt" or "m/s"), Source (the kind of
      level) and Derived (the columns of the row that were computed, not reported).
    - df_special: tropopause, maximum wind, layers of missing data, sounding system and cloud
      entries as text, with the part each came from. Winds are given there as reported.
    """
    if wind_unit not in ("kt", "m/s"):
        raise ValueError(f"wind_unit must be 'kt' or 'm/s', got {wind_unit!r}")
    main = pd.DataFrame(
        [
            {
                "Pressure": lv.pressure_hpa,
                "Height": lv.height_m,
                "Temp": lv.temp_c,
                "DewPoint": lv.dewpoint_c,
                "WindDir": lv.wind_dir_deg,
                "WindSpeed": None if lv.wind_speed_ms is None else _speed(lv.wind_speed_ms, wind_unit),
                "Source": lv.level_type.value,
                "Derived": ",".join(_DERIVED_NAMES[name] for name in lv.derived),
            }
            for lv in sounding.profile
        ],
        columns=MAIN_COLUMNS,
    )
    for column in MAIN_COLUMNS[:6]:
        main[column] = main[column].astype(float)

    rows = [row for report in sounding.reports for row in _special_rows(report, WMO_TABLES)]
    special = pd.DataFrame(rows, columns=SPECIAL_COLUMNS)
    if not special.empty:
        # The 31313 and cloud sections repeat in every part: the first copy is kept
        key = SPECIAL_COLUMNS[:4]
        repeated = special.duplicated(subset=key) & special["Subject"].isin(["Solar/Inst", "Cloud"])
        special = special[~repeated]
        clouds = special[special["Subject"] == "Cloud"]
        order = {"h": 0, "Nh": 1, "CL": 2, "CM": 3, "CH": 4}
        clouds = clouds.sort_values(by="Symbol", key=lambda col: col.map(order), kind="stable")
        special = pd.concat([clouds, special[special["Subject"] != "Cloud"]]).reset_index(drop=True)
    return main, special


def decode(
    ttaa: Optional[str] = None,
    ttbb: Optional[str] = None,
    ttcc: Optional[str] = None,
    ttdd: Optional[str] = None,
    *,
    wind_unit: str = "kt",
    interpolate: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Decodes the parts of one TEMP sounding and returns (df_main, df_special), described in
    `to_dataframes`.

    Each argument is the text of a part, starting at its name (TTAA, TTBB, TTCC, TTDD), or a
    whole bulletin: every report found is used, the part named by the argument first. All
    reports are taken as one sounding; use `decode_soundings` for a text with several
    stations or times. With `interpolate`, temperature, dew point and wind are filled between
    the observed levels and named in the Derived column.
    """
    for name, value in (("ttaa", ttaa), ("ttbb", ttbb), ("ttcc", ttcc), ("ttdd", ttdd)):
        if value is not None and not isinstance(value, str):
            raise TypeError(f"Message argument '{name}' must be a string or None, got {type(value).__name__}")

    named: Dict[ReportPart, SoundingReport] = {}
    others: Dict[ReportPart, SoundingReport] = {}
    for name, value in (("TTAA", ttaa), ("TTBB", ttbb), ("TTCC", ttcc), ("TTDD", ttdd)):
        if not value:
            continue
        for report in iter_decoded_reports(value):
            if report.part.value == name:
                named.setdefault(report.part, report)
            else:
                others.setdefault(report.part, report)
    sounding = merge_parts({**others, **named}.values(), interpolate=interpolate)
    return to_dataframes(sounding, wind_unit)


decode_full = decode

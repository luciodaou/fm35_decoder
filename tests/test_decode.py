"""decode(): the parts of one sounding as two DataFrames."""

import os
import re

import numpy as np
import pandas as pd
import pytest

import fm35_decoder
from fm35_decoder import decode, decode_full
from fm35_decoder.tables import WMO_TABLES, load_wmo_tables

from samples import SBGL_TTAA, SBGL_TTBB, SBGL_TTCC, SBGL_TTDD, TTAA_CG

HERE = os.path.dirname(__file__)


def demo_parts():
    namespace = {}
    with open(os.path.join(HERE, "demo.mt.py")) as handle:
        exec(handle.read(), namespace)
    return [namespace[name] for name in ("ttaa", "ttbb", "ttcc", "ttdd")]


def specials(df_special):
    return [tuple(r) for r in df_special[["Part", "Symbol", "Value"]].itertuples(index=False)]


def test_columns_and_order():
    df_main, df_special = decode(SBGL_TTAA, SBGL_TTBB, SBGL_TTCC, SBGL_TTDD)
    assert list(df_main.columns) == [
        "Pressure", "Height", "Temp", "DewPoint", "WindDir", "WindSpeed", "Source", "Derived",
    ]
    assert list(df_special.columns) == ["Symbol", "Subject", "Description", "Value", "Part"]
    assert df_main["Pressure"].is_monotonic_decreasing and len(df_main) == 99
    assert set(df_main["Source"]) == {"Surface", "Standard", "SigTemp", "SigWind"}
    assert decode_full is decode


def test_wind_speed_units():
    """Speeds are in knots unless m/s is asked for; the reported value comes back unchanged."""
    knots, _ = decode(SBGL_TTAA)
    mps, _ = decode(SBGL_TTAA, wind_unit="m/s")
    assert knots.set_index("Pressure").loc[200.0, "WindSpeed"] == 78.0
    assert mps.set_index("Pressure").loc[200.0, "WindSpeed"] == round(78 * 1852 / 3600, 1)
    with pytest.raises(ValueError, match="wind_unit"):
        decode(SBGL_TTAA, wind_unit="km/h")


def test_report_in_metres_per_second():
    """YY without 50 added: df_main converts to knots, df_special gives the wind as reported."""
    df_main, df_special = decode(TTAA_CG.replace("TTAA 80121", "TTAA 30121"))
    assert df_main.set_index("Pressure").loc[700.0, "WindSpeed"] == round(28 * 3600 / 1852, 1)
    assert ("TTAA", "dmdmfmfmfm", "240/83m/s") in specials(df_special)


def test_derived_column_names_what_was_not_reported():
    df_main, _ = decode(SBGL_TTAA, SBGL_TTBB)
    rows = df_main.set_index("Pressure")
    assert rows.loc[850.0, "Derived"] == ""
    assert rows.loc[949.0, "Derived"] == "Height,Temp,DewPoint"
    assert rows.loc[915.0, "Derived"] == "Height,WindDir,WindSpeed"
    plain, _ = decode(SBGL_TTAA, SBGL_TTBB, interpolate=False)
    rows = plain.set_index("Pressure")
    assert rows.loc[949.0, "Derived"] == "Height" and np.isnan(rows.loc[949.0, "Temp"])


def test_special_entries():
    _, df_special = decode(SBGL_TTAA, SBGL_TTBB, SBGL_TTCC, SBGL_TTDD)
    assert specials(df_special) == [
        ("TTBB", "h", "1000-1500 m (3300-5000 ft)"),  # 856//: h is code figure 6
        ("TTBB", "Nh", "8 oktas"),
        ("TTBB", "CL", "Stratocumulus other than cumulogenitus"),
        ("TTBB", "CM", "CM clouds invisible"),
        ("TTBB", "CH", "CH clouds invisible"),
        ("TTAA", "PtPtPt", "102hPa"),
        ("TTAA", "TtTtTt", "-73.7C"),
        ("TTAA", "DtDt", "-85.7C"),
        ("TTAA", "dtdtftft", "240/35kt"),
        ("TTAA", "PmPmPm", "213hPa"),
        ("TTAA", "dmdmfmfmfm", "250/83kt"),
        ("TTAA", "vbvb", "18kt"),
        ("TTAA", "vava", "12kt"),
        ("TTAA", "sr", "Solar and infrared corrected automatically by radiosonde system"),
        ("TTAA", "rara", "Vaisala RS41/DigiCORA MW41 (Finland)"),
        ("TTAA", "sasa", "Automatic satellite navigation"),
        ("TTAA", "8GGgg", "23:31"),
        ("TTCC", "PtPtPt", "42.6hPa"),
        ("TTCC", "TtTtTt", "-64.9C"),
        ("TTCC", "DtDt", "-89.9C"),
        ("TTCC", "dtdtftft", "65/13kt"),
    ]


def test_specials_name_their_part():
    """A tropopause in Part A and another in Part C are both kept; the 31313 section is listed once."""
    ttcc = "TTCC 80123 83612 70873 72159 27518 88906 77162 26018 77999 31313 42308 81137="
    _, df_special = decode(TTAA_CG.replace("88999", "88110 75362 30027"), None, ttcc, None)
    trop = df_special[df_special["Symbol"] == "PtPtPt"]
    assert list(zip(trop["Part"], trop["Value"])) == [("TTAA", "110hPa"), ("TTCC", "90.6hPa")]
    assert (df_special["Symbol"] == "8GGgg").sum() == 1


def test_repeated_max_wind_rows_kept():
    _, df_special = decode(TTAA_CG.replace("43131", "43131 66120 24083 43131"))
    assert list(df_special[df_special["Subject"] == "Max Wind"]["Value"]) == [
        "146hPa", "240/83kt", "31kt", "31kt", "120hPa", "240/83kt", "31kt", "31kt",
    ]


def test_missing_layers_are_listed():
    ttbb = (
        "TTBB 80128 83612 00951 16805 11900 14420 22/// ///// 33700 02041 44500 10560 "
        "21212 00951 09017 11940 08543 22850 10020 33/// ///// 44600 27030 55500 27040="
    )
    df_main, df_special = decode(None, ttbb)
    assert specials(df_special) == [("TTBB", "nn///", "900-700hPa"), ("TTBB", "nn///", "850-600hPa")]
    assert list(df_special["Description"]) == ["Temperature", "Wind"]
    assert np.isnan(df_main.set_index("Pressure").loc[850.0, "Temp"])
    assert df_main["Height"].isna().all()


def test_whole_bulletin_in_any_argument():
    """A bulletin passed in one argument, or in every one, decodes like the parts passed apart."""
    bulletin = " ".join([SBGL_TTAA, SBGL_TTBB, SBGL_TTCC])
    expected = decode(SBGL_TTAA, SBGL_TTBB, SBGL_TTCC)
    for args in [(bulletin,), (None, bulletin), (bulletin, bulletin, bulletin, bulletin)]:
        df_main, df_special = decode(*args)
        pd.testing.assert_frame_equal(df_main, expected[0])
        pd.testing.assert_frame_equal(df_special, expected[1])


def test_surface_only_report_decodes():
    df_main, _ = decode("TTAA 5900/ 83899 99017 20240 27003 88999 77999=")
    assert list(df_main["Pressure"]) == [1017.0]
    assert df_main.loc[0, "Source"] == "Surface" and df_main.loc[0, "WindDir"] == 270.0


def test_nothing_to_decode_gives_empty_frames():
    for args in [(None,), ("",), ("TTAA 61001 83746 NIL=",), ("no report here",), ("TTAA 61001 8374",)]:
        df_main, df_special = decode(*args)
        assert df_main.empty and df_special.empty
        assert "Pressure" in df_main.columns and "Symbol" in df_special.columns


def test_arguments_must_be_text():
    with pytest.raises(TypeError, match="must be a string or None"):
        decode(12345)


def test_against_the_university_of_wyoming_listing():
    """Station 83779, 12 UTC 23 February 2023: reported values agree with the Wyoming decoding."""
    df_main, _ = decode(*demo_parts(), interpolate=False)
    rows = df_main.set_index("Pressure")
    with open(os.path.join(HERE, "demo.mt.txt")) as handle:
        listing = [line.split() for line in handle if re.match(r"^\s*\d+\.\d\s+\d+\s+-?\d+\.\d\s", line)]
    compared = 0
    for fields in listing:
        if len(fields) != 11:
            continue  # a level without dew point or wind
        pressure, height, temp, dew = (float(x) for x in fields[:4])
        if pressure not in rows.index:
            continue
        row = rows.loc[pressure]
        if row["Source"] == "Standard" and pressure < 938.0:
            assert row["Height"] == height
        if "Temp" not in row["Derived"] and not np.isnan(row["Temp"]):
            assert row["Temp"] == temp
            if not np.isnan(row["DewPoint"]):
                assert row["DewPoint"] == pytest.approx(dew, abs=0.11)
            if not np.isnan(row["Height"]):
                assert row["Height"] == pytest.approx(height, abs=12.0)
            compared += 1
    assert compared > 40


def test_csv_tables_match_the_built_in_ones():
    load_wmo_tables.cache_clear()
    csv_tables = load_wmo_tables(os.path.join(os.path.dirname(fm35_decoder.__file__), "table_codes"))
    load_wmo_tables.cache_clear()
    for key in ("Nh", "CL", "h", "CM", "CH", "Sr", "rara", "sasa"):
        assert csv_tables[key] == WMO_TABLES[key], key
    assert load_wmo_tables() is WMO_TABLES

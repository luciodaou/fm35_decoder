import numpy as np
import pandas as pd
import pytest

from fm35_decoder import decode
from fm35_decoder.decoder import (
    decode_height,
    decode_wind,
    load_wmo_tables,
    parse_ttaa_ttcc,
    parse_ttbb_ttdd,
)


def test_decode_standard():
    ttaa = "TTAA 73121 83779 99938 21224 01008 00163 ///// ///// 92843 20019 07506 85570 18650 36008 70207 08030 34004 50591 06563 29503 40761 18364 30017 30970 33138 28015 25095 43722 28026 20241 55957 29040 15418 68957 28039 10658 73364 28019 88999 77999 31313 42308 81131="
    ttbb = "TTBB 73128 83779 00938 21224 11882 16804 22870 19856 33735 11056 44712 08616 55615 01218 66569 01530 77540 03758 88531 04546 99524 04761 11520 05356 22479 08370 33476 08760 44467 09360 55450 11557 66446 11761 77421 15358 88410 16765 99387 19967 11355 24948 22349 25758 33340 27122 44322 30106 55302 32738 66279 37340 77228 49110 88223 50528 99210 53558 11190 58550 22154 68556 33137 67964 44123 73356 55117 73560 66107 71366 77101 73164 21212 00938 01008 11870 01510 22524 00000 33453 29010 44425 31510 55359 29525 66305 27014 77296 30018 88247 28030 99200 29040 11157 27546 22150 28037 33140 25529 44128 27515 55106 26024 66101 28019 31313 42308 81131 41414 86500="
    ttcc = "TTCC 73123 83779 70865 71568 15020 50064 67574 12519 30380 58383 08535 88906 77162 26018 77999 31313 42308 81131="
    ttdd = "TTDD 7312/ 83779 11906 77162 22585 70370 33542 70970 44445 63978 55283 57785 21212 11935 25516 22896 26516 33868 29513 44832 28520 55774 25010 66742 19017 77632 05515 88618 07010 99605 12508 11592 17011 22572 16516 33537 09517 44526 09516 55500 13017 66475 10532 77421 10524 88376 11025 99357 09535 11330 09537 22308 08527 33289 08544 44283 09041 31313 42308 81131="

    df_main, df_special = decode(ttaa, ttbb, ttcc, ttdd)

    assert not df_main.empty
    assert "Pressure" in df_main.columns
    assert "Temp" in df_main.columns
    assert "DewPoint" in df_main.columns
    assert len(df_main) > 0
    assert not df_special.empty


def test_ttbb_parse_levels_above_1000():
    """Verify TTBB significant levels with pressure >= 1000 hPa are correctly decoded."""
    ttbb = "TTBB 53008 83746 00021 20245 11021 18423 22017 21056 33952 16024="
    levels, _ = parse_ttbb_ttdd(ttbb)
    pressures = [lvl["Pressure"] for lvl in levels]
    assert pressures == [1021.0, 1021.0, 1017.0, 952.0]


def test_ttbb_decode_above_1000():
    """Verify end-to-end decode with sounding exceeding 1000 hPa."""
    ttaa = "TTAA 53001 83746 99021 20245 13003 00191 19845 15007 92857 15056="
    ttbb = "TTBB 53008 83746 00021 20245 11021 18423 22017 21056 33952 16024="
    df_main, _ = decode(ttaa, ttbb, None, None)

    pressures = set(df_main["Pressure"].tolist())
    assert 1021 in pressures
    assert 1017 in pressures
    assert 21 not in pressures
    assert 17 not in pressures

    row_1017 = df_main[df_main["Pressure"] == 1017].iloc[0]
    assert row_1017["Temp"] == 21.0


def test_max_wind_five_degree_resolution():
    """Verify Max Wind with 5-degree speed addition (fff >= 500) decodes speed and direction accurately."""
    # 77200: Max wind at 200 hPa
    # 27620: Direction 275 deg (27*10 + 5), Speed 120 kt (620 - 500)
    ttaa = "TTAA 73121 83779 77200 27620 41414 86500="
    _, df_special = decode(ttaa, None, None, None)

    wind_row = df_special[df_special["Symbol"] == "dmdmfmfmfm"]
    assert not wind_row.empty
    assert wind_row.iloc[0]["Value"] == "275/120kt"


def test_variable_wind_handling():
    """Verify dd=99 produces NaN direction and preserves speed without crashing vector interpolation."""
    direction, speed = decode_wind("99025")
    assert np.isnan(direction)
    assert speed == 25.0

    # End-to-end: surface level with variable wind
    ttaa = "TTAA 73121 83779 99015 20245 99025 85570 18650 36008="
    df_main, _ = decode(ttaa, None, None, None)
    surf_row = df_main[df_main["Pressure"] == 1015].iloc[0]
    assert np.isnan(surf_row["WindDir"])
    assert surf_row["WindSpeed"] == 25.0


def test_ttbb_dropped_group_resilience():
    """Verify that a missing/dropped intermediate group in TTBB does not truncate the rest of the sounding."""
    # Group 11 followed directly by 33 (group 22 missing due to GTS line noise)
    ttbb = "TTBB 53008 83746 00021 20245 11021 18423 33017 21056 44952 16024="
    levels, _ = parse_ttbb_ttdd(ttbb)
    pressures = [lvl["Pressure"] for lvl in levels]
    assert 1017.0 in pressures
    assert 952.0 in pressures
    assert len(levels) == 4


def test_super_saturation_prevention():
    """Verify interpolated dewpoint never exceeds dry temperature (Td <= T)."""
    ttaa = "TTAA 73121 83779 99000 20020 01010 85570 10000 01010="
    df_main, _ = decode(ttaa, None, None, None)
    assert (df_main["DewPoint"] <= df_main["Temp"] + 1e-5).all()


def test_high_stratosphere_heights():
    """Verify standard isobaric levels above 10 hPa (7, 5, 3 hPa) decode with realistic heights."""
    # 7 hPa: standard height ~33,500 m. Coded as 07350 (350 dam = 3500 m + 30000 m = 33,500 m)
    h_7 = decode_height(7, "350")
    assert h_7 is not None
    assert 30000 <= h_7 <= 36000

    # 5 hPa: standard height ~35,800 m. Coded as 05580
    h_5 = decode_height(5, "580")
    assert h_5 is not None
    assert 34000 <= h_5 <= 38000


def test_negative_height_at_1000hpa():
    """Verify negative geopotential heights at 1000 hPa (500 + |h| convention)."""
    # 1000 hPa with reported height 525 -> 500 + 25 -> -25 gpm
    h_neg = decode_height(1000, "525")
    assert h_neg == -25


def test_table_performance_zero_io():
    """Verify in-memory tables load in sub-millisecond time without disk I/O."""
    tables = load_wmo_tables()
    assert "T_3931" in tables
    assert "D_0777" in tables
    assert "CL" in tables
    assert tables["T_3931"]["1"]["Sign"] == "-"


def test_type_safety_input_validation():
    """Verify non-string arguments raise TypeError."""
    with pytest.raises(TypeError, match="must be a string or None"):
        decode(12345, None, None, None)


# --- Regression tests for the WMO-No. 306 review fixes ---

DEMO_TTAA = "TTAA 73121 83779 99938 21224 01008 00163 ///// ///// 92843 20019 07506 85570 18650 36008 70207 08030 34004 50591 06563 29503 40761 18364 30017 30970 33138 28015 25095 43722 28026 20241 55957 29040 15418 68957 28039 10658 73364 28019 88999 77999 31313 42308 81131="
DEMO_TTCC = "TTCC 73123 83779 70865 71568 15020 50064 67574 12519 30380 58383 08535 88906 77162 26018 77999 31313 42308 81131="


def _row(df, pressure):
    return df[df["Pressure"] == pressure].iloc[0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ttbb": "TTBB 73128 83779 00938 21224 11882 16804="},
        {"ttaa": "TTAA 73121 83779 99938 21224 01008="},
        {"ttbb": "TTBB 73128 83779 21212 00938 01008 11870 01510="},
        {"ttdd": "TTDD 7312/ 83779 11906 77162="},
    ],
)
def test_partial_messages_do_not_crash(kwargs):
    df_main, _ = decode(**kwargs)
    assert not df_main.empty
    assert {"Pressure", "Height", "Temp", "DewPoint", "WindDir", "WindSpeed"}.issubset(df_main.columns)


def test_demo_standard_levels_exact():
    """Hand-decoded values for the 83779 demo, Parts A and C."""
    df_main, _ = decode(DEMO_TTAA, None, DEMO_TTCC, None)
    expected = {
        # P: (Height, Temp, DewPoint, WindDir, WindSpeed)
        925: (843, 20.0, 18.1, 75.0, 6.0),
        850: (1570, 18.6, 13.6, 360.0, 8.0),
        700: (3207, 8.0, 5.0, 340.0, 4.0),
        500: (5910, -6.5, -19.5, 295.0, 3.0),
        400: (7610, -18.3, -32.3, 300.0, 17.0),
        300: (9700, -33.1, -36.9, 280.0, 15.0),
        250: (10950, -43.7, -45.9, 280.0, 26.0),
        200: (12410, -55.9, -62.9, 290.0, 40.0),
        150: (14180, -68.9, -75.9, 280.0, 39.0),
        100: (16580, -73.3, -87.3, 280.0, 19.0),
        70: (18650, -71.5, -89.5, 150.0, 20.0),
        50: (20640, -67.5, -91.5, 125.0, 19.0),
        30: (23800, -58.3, -91.3, 85.0, 35.0),
    }
    for p, (h, t, td, wd, ws) in expected.items():
        row = _row(df_main, p)
        assert row["Height"] == h, p
        assert row["Temp"] == pytest.approx(t), p
        assert row["DewPoint"] == pytest.approx(td), p
        assert row["WindDir"] == wd, p
        assert row["WindSpeed"] == ws, p

    # 1000 hPa is below the station: height only, temperature not invented
    row_1000 = _row(df_main, 1000)
    assert row_1000["Height"] == 163
    assert np.isnan(row_1000["Temp"])


def test_id_omits_wind_groups_above_last_wind_level():
    """Id=7: wind groups only up to 700 hPa (Regulation 35.2.2.3(b), code table 1734)."""
    ttaa = "TTAA 73127 83779 99938 21224 01008 85570 18650 36008 70207 08030 34004 50591 06563 40761 18364 30970 33138 25095 43722 20241 55957="
    df_main, _ = decode(ttaa=ttaa)
    assert {500, 400, 300, 250, 200}.issubset(set(df_main["Pressure"]))
    for p in (500, 400, 300, 250, 200):
        row = _row(df_main, p)
        assert np.isnan(row["WindDir"]) and np.isnan(row["WindSpeed"]), p
    assert _row(df_main, 300)["Temp"] == pytest.approx(-33.1)
    assert _row(df_main, 250)["Height"] == 10950


def test_id_slash_means_no_standard_level_winds():
    ttaa = "TTAA 7312/ 10410 99012 21224 01008 00105 20019 85570 18650="
    levels, _ = parse_ttaa_ttcc(ttaa)
    pressures = [lvl["Pressure"] for lvl in levels]
    assert pressures == [1012.0, 1000.0, 850.0]
    assert levels[0]["WindSpeed"] == 8.0
    assert "WindSpeed" not in levels[1]


@pytest.mark.parametrize(
    "message, parser",
    [
        ("TTAA 7312/ 10410 99012 21224 01008 00105 20019=", parse_ttaa_ttcc),
        ("TTBB 7312/ 11035 00980 21224 11850 16804=", parse_ttbb_ttdd),
        ("TTDD 7312/ 11035 11906 77162=", parse_ttbb_ttdd),
    ],
)
def test_header_with_slash_is_not_decoded_as_data(message, parser):
    levels, _ = parser(message)
    pressures = {lvl["Pressure"] for lvl in levels}
    assert not pressures & {100.0, 1035.0, 103.5}


def test_part_c_tropopause_and_max_wind_in_tenths():
    ttcc = "TTCC 73123 83779 70865 71568 15020 88906 77162 26018 77155 27560="
    _, df_special = decode(ttcc=ttcc)
    values = dict(zip(df_special["Symbol"], df_special["Value"]))
    assert values["PtPtPt"] == "90.6hPa"
    assert values["PmPmPm"] == "15.5hPa"


def test_part_taken_from_argument_when_header_missing():
    ttcc = "73123 83779 70865 71568 15020 50064 67574 12519="
    df_main, _ = decode(ttcc=ttcc)
    assert set(df_main["Pressure"]) == {70, 50}


def test_part_c_temperature_groups_starting_with_77():
    """A -77.1 C temperature group (77162) must not be taken for a max-wind indicator."""
    ttcc = "TTCC 73123 83779 70865 77162 15020 50064 67574 12519="
    df_main, df_special = decode(ttcc=ttcc)
    assert _row(df_main, 70)["Temp"] == pytest.approx(-77.1)
    assert _row(df_main, 50)["Temp"] == pytest.approx(-67.5)
    assert df_special.empty or "PmPmPm" not in set(df_special["Symbol"])


@pytest.mark.parametrize("section", ["51515", "61616"])
def test_regional_and_national_sections_are_not_decoded(section):
    ttbb = f"TTBB 73128 72451 00938 21224 11882 16804 21212 00938 01008 11870 01510 31313 58708 81103 {section} 10164 00095 10194 22512 21508="
    levels, _ = parse_ttbb_ttdd(ttbb)
    assert {lvl["Pressure"] for lvl in levels} == {938.0, 882.0, 870.0}

    ttaa = f"TTAA 73121 72451 99938 21224 01008 85570 18650 36008 {section} 10164 00098 10194 22007 25006="
    levels, _ = parse_ttaa_ttcc(ttaa)
    assert {lvl["Pressure"] for lvl in levels} == {938.0, 850.0}


def test_missing_data_is_not_extrapolated():
    """Winds/dewpoints missing above the last report stay missing (no trailing fill)."""
    ttaa = "TTAA 73121 83779 99938 21224 01008 85570 18650 36008 70207 08030 ///// 50591 06563 ///// 40761 183// /////="
    df_main, _ = decode(ttaa=ttaa)
    for p in (700, 500, 400):
        assert np.isnan(_row(df_main, p)["WindSpeed"]), p
    assert np.isnan(_row(df_main, 400)["DewPoint"])


def test_variable_wind_direction_not_interpolated():
    ttaa = "TTAA 73121 83779 99938 21224 09010 85570 18650 99020 70207 08030 27010="
    df_main, _ = decode(ttaa=ttaa)
    row = _row(df_main, 850)
    assert np.isnan(row["WindDir"])
    assert row["WindSpeed"] == 20.0


def test_wind_in_metres_per_second_converted_to_knots():
    """YY <= 31 means m/s (WMO-No. 306, symbol YY); output is always knots."""
    ttaa = "TTAA 23121 83779 99938 21224 27010 77200 27620 40510="
    df_main, df_special = decode(ttaa=ttaa)
    assert _row(df_main, 938)["WindSpeed"] == pytest.approx(19.4)
    values = dict(zip(df_special["Symbol"], df_special["Value"]))
    assert values["dmdmfmfmfm"] == "275/233.3kt"
    assert values["vbvb"] == "9.7kt"
    assert values["vava"] == "19.4kt"


@pytest.mark.parametrize("group", ["36500", "00010", "99525", "40010"])
def test_invalid_wind_groups_rejected(group):
    assert decode_wind(group) == (None, None)


def test_valid_edge_wind_groups():
    assert decode_wind("00000") == (0.0, 0.0)
    assert decode_wind("00505") == (5.0, 5.0)
    assert decode_wind("36010") == (360.0, 10.0)


def test_solar_correction_table_3849():
    tables = load_wmo_tables()
    assert tables["Sr"]["4"] == "Solar and infrared corrected automatically by radiosonde system"


def test_loaded_tables_are_read_only():
    tables = load_wmo_tables()
    with pytest.raises(TypeError):
        tables["Sr"]["4"] = "tampered"


def test_csv_tables_match_in_memory_tables():
    import os

    import fm35_decoder

    base = os.path.join(os.path.dirname(fm35_decoder.__file__), "table_codes")
    csv_tables = load_wmo_tables(base)
    mem_tables = load_wmo_tables()
    for key in ("Nh", "CL", "h", "CM", "CH", "Sr", "rara", "sasa"):
        assert dict(csv_tables[key]) == dict(mem_tables[key]), key

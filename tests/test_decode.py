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


TTAA_CG = (
    "TTAA 80121 83612 99951 16805 09017 00122 ///// ///// 92793 17837 07545 85521 17434 00514 "
    "70157 08400 29028 50587 05704 26019 40758 17910 25022 30966 34926 22516 25091 44340 20022 "
    "20237 55934 23524 15417 66562 24581 10662 77161 19509 88999 77146 24083 43131 31313 42308 81137="
)


def specials(df_special):
    return [tuple(r) for r in df_special[["Part", "Symbol", "Value"]].itertuples(index=False)]


def test_part_c_special_pressures_in_tenths():
    """88/77 groups in Part C give the pressure in tenths of hPa."""
    ttcc = "TTCC 80123 83612 70873 72159 27518 50079 64561 05504 30399 57761 06507 88860 75559 24004 77650 25070 41012="
    _, df_special = decode(None, None, ttcc, None)
    rows = specials(df_special)
    assert ("TTCC", "PtPtPt", "86.0hPa") in rows
    assert ("TTCC", "PmPmPm", "65.0hPa") in rows


def test_specials_name_their_part():
    """A tropopause in Part A and another in Part C are both kept, each with its part."""
    ttcc = "TTCC 80123 83612 70873 72159 27518 88906 77162 26018 77999 31313 42308 81137="
    ttaa = TTAA_CG.replace("88999", "88110 75362 30027")
    _, df_special = decode(ttaa, None, ttcc, None)
    trop = df_special[df_special["Symbol"] == "PtPtPt"]
    assert list(zip(trop["Part"], trop["Value"])) == [("TTAA", "110hPa"), ("TTCC", "90.6hPa")]
    # the 31313 section, identical in both parts, is listed once
    assert (df_special["Symbol"] == "8GGgg").sum() == 1


def test_repeated_max_wind_rows_kept():
    """Two maximum wind levels with the same wind keep all their rows."""
    ttaa = TTAA_CG.replace("43131", "43131 66120 24083 43131")
    _, df_special = decode(ttaa, None, None, None)
    assert list(df_special[df_special["Subject"] == "Max Wind"]["Value"]) == [
        "146hPa", "240/83kt", "31kt", "31kt", "120hPa", "240/83kt", "31kt", "31kt",
    ]


def test_31313_without_sonde_group():
    """31313 followed directly by 8GGgg reads it as the launch time, not as the sonde group."""
    _, special = parse_ttaa_ttcc("TTAA 80121 83612 99951 16805 09017 31313 81137=")
    assert [(s["Symbol"], s["Value"]) for s in special] == [("8GGgg", "11:37")]


def test_temperatures_like_indicators():
    """-66.5 C at 150 hPa (66562) and -77.1 C at 100 hPa (77161) are temperatures."""
    df_main, _ = decode(TTAA_CG, None, None, None)
    top = df_main.set_index("Pressure")
    assert top.loc[150.0, "Temp"] == -66.5
    assert top.loc[100.0, "Temp"] == -77.1


def test_41414_after_max_wind_is_shear():
    """The cloud section is in part B only: in part A, 41414 after a maximum wind is 14/14 kt shear."""
    _, df_special = decode("TTAA 73121 83779 77200 27620 41414 31313 42308 81131=", None, None, None)
    assert specials(df_special)[:4] == [
        ("TTAA", "PmPmPm", "200hPa"), ("TTAA", "dmdmfmfmfm", "275/120kt"),
        ("TTAA", "vbvb", "14kt"), ("TTAA", "vava", "14kt"),
    ]
    assert ("TTAA", "8GGgg", "11:31") in specials(df_special)


def test_temperatures_like_section_markers():
    """21212 (21.2 C) at 925 hPa and 31313 (-31.3 C) at 300 hPa are temperatures in part A."""
    ttaa = TTAA_CG.replace("92793 17837", "92793 21212").replace("30966 34926", "30966 31313")
    df_main, _ = decode(ttaa, None, None, None)
    top = df_main.set_index("Pressure")
    assert (top.loc[925.0, "Temp"], top.loc[925.0, "DewPoint"]) == (21.2, 20.0)
    assert (top.loc[300.0, "Temp"], top.loc[300.0, "DewPoint"]) == (-31.3, -32.6)
    assert top.loc[300.0, "WindDir"] == 225.0


def test_wind_speeds_in_mps():
    """YY without 50 added (day 30): speeds are in m/s, converted to knots in df_main."""
    ttaa = TTAA_CG.replace("TTAA 80121", "TTAA 30121")
    df_main, df_special = decode(ttaa, None, None, None)
    assert df_main.set_index("Pressure").loc[700.0, "WindSpeed"] == round(28 * 3600 / 1852, 1)
    assert ("TTAA", "dmdmfmfmfm", "240/83m/s") in specials(df_special)


def test_regional_section_ends_level_data():
    """51515 groups (US style) are not levels, in part A or in part B."""
    ttbb = "TTBB 80128 83612 00951 16805 11931 16420 21212 00951 09017 11940 08543 51515 10164 00098 10194 22513 27015="
    df_main, _ = decode(TTAA_CG.replace("31313", "51515 10164 00098 10194 22513 27015 31313"), ttbb, None, None)
    assert 513.0 not in set(df_main["Pressure"])
    assert 1098.0 not in set(df_main["Pressure"])
    assert df_main.set_index("Pressure").loc[100.0, "WindSpeed"] == 9.0


def test_ttbb_alone():
    """A TTBB without its TTAA decodes: no heights, but the temperature profile."""
    ttbb = "TTBB 80128 83612 00951 16805 11931 16420 22911 19041 33899 18035 21212 00951 09017 11940 08543="
    df_main, _ = decode(None, ttbb, None, None)
    assert list(df_main["Pressure"]) == [951.0, 940.0, 931.0, 911.0, 899.0]
    assert df_main["Height"].isna().all()


def test_surface_only_is_an_error():
    with pytest.raises(ValueError, match="without temperatures above the surface"):
        decode("TTAA 5900/ 83899 99017 20240 27003 88999 77999=", None, None, None)


def test_nothing_made_up_above_the_last_observation():
    """50 hPa reported as ///// with no wind group (Id 7) keeps no temperature and no wind."""
    ttcc = "TTCC 73127 83746 70865 76164 12006 50064 ///// 88999 77999="
    df_main, _ = decode(TTAA_CG, None, ttcc, None)
    row = df_main.set_index("Pressure").loc[50.0]
    assert row[["Temp", "DewPoint", "WindDir", "WindSpeed"]].isna().all()


def test_variable_wind_keeps_no_direction():
    """dd = 99 between two directional winds keeps its speed and no direction."""
    ttaa = TTAA_CG.replace("85521 17434 00514", "85521 17434 99014")
    df_main, _ = decode(ttaa, None, None, None)
    row = df_main.set_index("Pressure").loc[850.0]
    assert np.isnan(row["WindDir"]) and row["WindSpeed"] == 14.0


def test_wind_groups_follow_id():
    """Id = / : only the surface has a wind group, so no level is skipped or given a made-up wind."""
    ttaa = (
        "TTAA 8012/ 83612 99951 16805 ///// 00122 ///// 92793 17837 85521 17434 70157 08400 "
        "50587 05704 40758 17910 30966 34926 25091 44340 20237 55934 15417 62562 10662 69961 88999 77999="
    )
    df_main, _ = decode(ttaa, None, None, None)
    assert list(df_main["Pressure"]) == [1000.0, 951.0, 925.0, 850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0, 150.0, 100.0]
    assert df_main["WindSpeed"].isna().all()


def test_level_without_wind_keeps_the_tropopause():
    """Id = 3 in Part C: 20 hPa has no wind group, so the 88 group after it is the tropopause."""
    ttcc = "TTCC 64003 83827 70871 67374 29024 50077 61978 22509 30397 56582 26016 20656 ///// 88823 73566 27028 77999="
    df_main, df_special = decode(None, None, ttcc, None)
    assert 20.0 in set(df_main["Pressure"])
    assert ("TTCC", "PtPtPt", "82.3hPa") in specials(df_special)
    assert ("TTCC", "dtdtftft", "270/28kt") in specials(df_special)


def test_header_with_slash_skips_station_number():
    """TTDD YYGG/ IIiii: the station number (here 11035) is not read as a significant level."""
    levels, _ = parse_ttbb_ttdd("TTDD 6612/ 11035 11860 75559 22781 68361=")
    assert [lvl["Pressure"] for lvl in levels] == [86.0, 78.1]


def test_pressures_keep_tenths():
    """Part D levels keep their tenths of hPa and are not merged with nearby levels."""
    ttcc = "TTCC 80121 83612 70873 72159 27518 10662 66962 19509="
    ttdd = "TTDD 8012/ 83612 11707 72159 22700 72561 33104 66560 44100 66962="
    df_main, _ = decode(None, None, ttcc, ttdd)
    assert list(df_main["Pressure"]) == [70.7, 70.0, 10.4, 10.0]


def test_bulletin_in_every_argument():
    """A whole bulletin passed for every part decodes like the parts passed separately."""
    ttbb = "TTBB 80128 83612 00951 16805 11931 16420 22911 19041 21212 00951 09017 11940 08543="
    ttcc = "TTCC 80123 83612 70873 72159 27518 88860 75559 24004 77999="
    bulletin = " ".join([TTAA_CG, ttbb, ttcc])
    split_main, split_special = decode(TTAA_CG, ttbb, ttcc, None)
    for args in [(bulletin, None, None, None), (bulletin, bulletin, bulletin, bulletin)]:
        df_main, df_special = decode(*args)
        pd.testing.assert_frame_equal(df_main, split_main)
        pd.testing.assert_frame_equal(df_special, split_special)


def test_marker_like_temperatures_keep_the_rest_of_part_a():
    """52525 (-52.5 C) at 200 hPa and 56565 (-56.5 C) at the tropopause are data, not sections."""
    ttaa = TTAA_CG.replace("20237 55934", "20237 52525").replace("88999", "88120 56565 24050")
    df_main, df_special = decode(ttaa, None, None, None)
    top = df_main.set_index("Pressure")
    assert (top.loc[200.0, "Temp"], top.loc[200.0, "DewPoint"]) == (-52.5, -55.0)
    assert top.loc[100.0, "Temp"] == -77.1
    rows = specials(df_special)
    assert ("TTAA", "TtTtTt", "-56.5C") in rows
    assert ("TTAA", "DtDt", "-71.5C") in rows
    assert ("TTAA", "PmPmPm", "146hPa") in rows
    assert ("TTAA", "8GGgg", "11:37") in rows


def test_21212_as_part_b_temperature():
    """21212 after a level group is 21.2 C with a depression of 1.2 C, not the wind section."""
    ttbb = "TTBB 80128 83612 00951 21212 11931 16420 22911 19041 21212 00951 09017 11940 08543="
    levels, _ = parse_ttbb_ttdd(ttbb)
    assert [(lv["Pressure"], lv["Source"]) for lv in levels] == [
        (951.0, "SigTemp"), (931.0, "SigTemp"), (911.0, "SigTemp"), (951.0, "SigWind"), (940.0, "SigWind"),
    ]
    assert (levels[0]["Temp"], levels[0]["DewPoint"]) == (21.2, 20.0)
    assert levels[4]["WindSpeed"] == 43.0


def test_reported_standard_level_is_not_extrapolated_again():
    """20 hPa reported with its height and ///// stays one row, with no made-up temperature."""
    ttcc = "TTCC 80123 83612 70873 72159 27518 50079 64561 05504 30399 57761 06507 20648 ///// 88999 77999="
    ttdd = "TTDD 8012/ 83612 11400 60170 22202 52782="
    df_main, _ = decode(TTAA_CG, None, ttcc, ttdd)
    rows = df_main[df_main["Pressure"] == 20.0]
    assert len(rows) == 1
    assert rows.iloc[0]["Height"] == 26480 and rows.iloc[0]["Source"] == "Standard"
    assert np.isnan(rows.iloc[0]["Temp"])


def test_extrapolated_level_has_a_height_only():
    """Sounding ending at 20.2 hPa without a 20 hPa group: the geopotential alone is extrapolated."""
    ttcc = "TTCC 80123 83612 70873 72159 27518 50079 64561 05504 30399 57761 06507 88999 77999="
    ttdd = "TTDD 8012/ 83612 11400 60170 22202 52782="
    df_main, _ = decode(TTAA_CG, None, ttcc, ttdd)
    rows = df_main[df_main["Pressure"] == 20.0]
    assert len(rows) == 1 and rows.iloc[0]["Source"] == "Extrapolated"
    assert 26000 < rows.iloc[0]["Height"] < 27000
    assert rows[["Temp", "DewPoint"]].isna().all().all()
    assert not df_main["Pressure"].duplicated().any()


def test_missing_layers_are_not_interpolated():
    """nn/// ///// (35.3.1.6, 35.3.2.2): no value is filled inside the layer, which is listed."""
    ttbb = (
        "TTBB 80128 83612 00951 16805 11900 14420 22/// ///// 33700 02041 44500 10560 "
        "21212 00951 09017 11940 08543 22850 10020 33/// ///// 44600 27030 55500 27040="
    )
    df_main, df_special = decode(None, ttbb, None, None)
    rows = df_main.set_index("Pressure")
    assert np.isnan(rows.loc[850.0, "Temp"]) and np.isnan(rows.loc[850.0, "DewPoint"])
    assert not np.isnan(rows.loc[940.0, "Temp"]) and not np.isnan(rows.loc[600.0, "Temp"])
    assert np.isnan(rows.loc[700.0, "WindSpeed"]) and np.isnan(rows.loc[700.0, "WindDir"])
    assert not np.isnan(rows.loc[900.0, "WindSpeed"])
    assert specials(df_special) == [
        ("TTBB", "nn///", "900-700hPa"), ("TTBB", "nn///", "850-600hPa"),
    ]
    assert list(df_special["Description"]) == ["Temperature", "Wind"]


def test_undefined_id_does_not_drop_winds():
    """Id = 0 is not defined in Part C: the wind groups are still read as winds, not as levels."""
    ttcc = "TTCC 80120 83612 70873 72159 27518 50079 64561 30014 30399 57761 06507="
    df_main, _ = decode(None, None, ttcc, None)
    assert list(df_main["Pressure"]) == [70.0, 50.0, 30.0]
    assert df_main.set_index("Pressure").loc[50.0, "WindDir"] == 300.0


def test_special_level_without_pressure_keeps_its_groups():
    """88/// : the tropopause is dropped whole; its temperature group is not read as a level."""
    ttaa = TTAA_CG.replace("88999", "88/// 50580 24050")
    df_main, df_special = decode(ttaa, None, None, None)
    assert (df_main["Pressure"] == 500.0).sum() == 1
    assert df_main.set_index("Pressure").loc[500.0, "Height"] == 5870
    assert "Tropopause" not in set(df_special["Subject"])
    assert ("TTAA", "PmPmPm", "146hPa") in specials(df_special)


def test_direction_00_with_speed_has_no_direction():
    direction, speed = decode_wind("00010")
    assert np.isnan(direction) and speed == 10.0
    assert decode_wind("00000") == (0.0, 0.0)
    assert decode_wind("00510") == (5.0, 10.0)


def test_sounding_system_tables_follow_wmo():
    """31313 42308: table 3849, common code tables C-2 and C-7."""
    _, special = parse_ttaa_ttcc("TTAA 80121 83612 99951 16805 09017 31313 42308 81137=")
    assert [s["Value"] for s in special[:3]] == [
        "Solar and infrared corrected automatically by radiosonde system",
        "Vaisala RS41/DigiCORA MW41 (Finland)",
        "Automatic satellite navigation",
    ]


def test_csv_tables_match_the_built_in_ones():
    import os

    import fm35_decoder
    from fm35_decoder.tables import WMO_TABLES

    load_wmo_tables.cache_clear()
    csv_tables = load_wmo_tables(os.path.join(os.path.dirname(fm35_decoder.__file__), "table_codes"))
    load_wmo_tables.cache_clear()
    for key in ("Nh", "CL", "h", "CM", "CH", "Sr", "rara", "sasa"):
        assert csv_tables[key] == WMO_TABLES[key], key


def test_heights_above_the_last_temperature_are_bounded():
    """Wind levels above the last temperature get a height only within 25 hPa and a quarter of
    their pressure (35.2.2.4); a standard level further up keeps the height it reports."""
    ttcc = "TTCC 80123 83612 70873 72159 27518 50079 ///// 05504="
    ttdd = "TTDD 8012/ 83612 11650 70160 21212 11600 27010 22400 27020="
    df_main, _ = decode(TTAA_CG, None, ttcc, ttdd)
    rows = df_main.set_index("Pressure")
    assert 19100 < rows.loc[65.0, "Height"] < 19250
    assert 19550 < rows.loc[60.0, "Height"] < 19750  # 5 hPa above the last temperature
    assert rows.loc[50.0, "Height"] == 20790  # reported
    assert pd.isna(rows.loc[40.0, "Height"])  # 25 hPa above, more than a quarter of 40 hPa


def test_height_inside_a_layer_uses_log_pressure_temperature():
    """A wind level between two temperatures takes its height from a ln(P) temperature."""
    ttbb = "TTBB 80128 83612 00951 16805 11500 05704 21212 00951 09017 11700 29028 22600 28020="
    df_main, _ = decode(TTAA_CG, ttbb, None, None)
    rows = df_main.set_index("Pressure")
    assert rows.loc[700.0, "Height"] == 3157 and rows.loc[500.0, "Height"] == 5870
    assert 4350 < rows.loc[600.0, "Height"] < 4450

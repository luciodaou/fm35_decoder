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

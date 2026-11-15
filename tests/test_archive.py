"""
Reports from a sounding archive (archive_samples.py), decoded group by group: the extreme
values of the archive and the forms that are rare or malformed. The values asserted are those
coded in each report, right or wrong; MALFORMED_REPORTS.md tells the cases apart.
"""

import pytest

from fm35_decoder import LevelType, decode, parse_report

import archive_samples as A
from samples import KT


def rows(report, *types):
    """(pressure, height, temperature, dew point, direction, speed in knots) of the levels."""
    return [
        (
            lv.pressure_hpa, lv.height_m, lv.temp_c, lv.dewpoint_c, lv.wind_dir_deg,
            None if lv.wind_speed_ms is None else round(lv.wind_speed_ms / KT),
        )
        for lv in (report.of_type(*types) if types else report.levels)
    ]


def heights(report):
    return {lv.pressure_hpa: lv.height_m for lv in report.of_type(LevelType.MANDATORY)}


def shears(report):
    return [
        tuple(None if v is None else round(v / KT) for v in (lv.shear_below_ms, lv.shear_above_ms))
        for lv in report.of_type(LevelType.MAX_WIND)
    ]


# --- Extreme values -------------------------------------------------------------------------


def test_winds_above_100_knots_with_a_direction_ending_in_5():
    """23658 is 235 degrees at 158 kt: 500 is added to fff and fff itself is above 100."""
    report = parse_report(A.SBSM_JET_TTAA)
    assert rows(report, LevelType.MANDATORY)[6:9] == [
        (300.0, 9420.0, -37.7, -61.7, 235.0, 124),
        (250.0, 10670.0, -41.3, -66.3, 245.0, 154),
        (200.0, 12150.0, -52.3, -72.3, 235.0, 158),
    ]
    assert rows(report, LevelType.TROPOPAUSE) == [(124.0, None, -63.1, -85.1, 260.0, 92)]
    assert rows(report, LevelType.MAX_WIND) == [(203.0, None, None, None, 235.0, 158)]
    assert shears(report) == [(22, 46)]


def test_lowest_heights_of_the_archive():
    """00764 is 264 m below sea level; 92420, 85154 and 70801 take no thousand more."""
    report = parse_report(A.SBCR_LOW_HEIGHTS_TTAA)
    assert rows(report)[:2] == [(955.0, None, 27.0, 21.0, 30.0, 3), (1000.0, -264.0, None, None, None, None)]
    assert heights(report) == {
        1000.0: -264.0, 925.0: 420.0, 850.0: 1154.0, 700.0: 2801.0, 500.0: 5500.0, 400.0: 7210.0,
        300.0: 9320.0, 250.0: 10580.0, 200.0: 12060.0, 150.0: 13850.0, 100.0: 16260.0,
    }


def test_highest_heights_of_the_archive():
    """30087 is 10870 m and 25214 is 12140 m; in Part C 70983 is 19830 m and 50187 is 21870 m."""
    below = parse_report(A.SBBR_HIGH_HEIGHTS_TTAA)
    assert heights(below) == {
        1000.0: 234.0, 925.0: 919.0, 850.0: 1666.0, 700.0: 3331.0, 500.0: 7050.0, 400.0: 8760.0,
        300.0: 10870.0, 250.0: 12140.0, 200.0: 13620.0, 150.0: 15420.0, 100.0: 17780.0,
    }
    assert rows(below, LevelType.TROPOPAUSE) == [(112.0, None, -78.9, -84.9, 255.0, 64)]
    assert rows(below, LevelType.MAX_WIND) == [(143.0, None, None, None, 230.0, 76)]
    assert shears(below) == [(11, 30)]
    above = parse_report(A.SBBR_HIGH_HEIGHTS_TTCC)
    assert heights(above) == {70.0: 19830.0, 50.0: 21870.0, 30.0: 25050.0, 20.0: 27650.0}
    assert above.of_type(LevelType.TROPOPAUSE) == []


def test_test_pattern_report_decodes_as_coded():
    """99999 is a surface at 999 hPa; 50916 in Part C takes 10000 m, not 20000 m."""
    below = parse_report(A.SBPV_TEST_PATTERN_TTAA)
    assert rows(below)[0] == (999.0, None, 27.0, 23.1, 180.0, 2)
    assert heights(below) == {
        1000.0: 74.0, 925.0: 606.0, 850.0: 1176.0, 700.0: 3485.0, 500.0: 4750.0, 400.0: 6260.0,
        300.0: 8200.0, 250.0: 9430.0, 200.0: 10910.0, 150.0: 12710.0, 100.0: 15090.0,
    }
    above = parse_report(A.SBPV_TEST_PATTERN_TTCC)
    assert heights(above) == {70.0: 17150.0, 50.0: 19160.0, 30.0: 22360.0, 20.0: 24960.0}
    assert rows(above, LevelType.TROPOPAUSE) == [(94.7, None, -78.7, -85.7, 285.0, 17)]


def test_tropopause_temperature_that_starts_with_88():
    """88874 88536 25020: the second group is -88.5 C, not another tropopause."""
    report = parse_report(A.SBMN_COLD_TROPOPAUSE_TTCC)
    assert rows(report, LevelType.TROPOPAUSE) == [(87.4, None, -88.5, -92.1, 250.0, 20)]
    assert rows(report, LevelType.MANDATORY)[-1] == (30.0, 23850.0, None, None, None, None)
    at_999 = parse_report(A.SBMN_COLD_TROPOPAUSE_TTCC.replace("88874", "88999"))
    assert rows(at_999, LevelType.TROPOPAUSE) == [(99.9, None, -88.5, -92.1, 250.0, 20)]


def test_surface_wind_as_coded():
    """03090 is 30 degrees at 90 kt, whatever was meant."""
    report = parse_report(A.SBVT_SURFACE_WIND_TTAA)
    assert rows(report)[0] == (1013.0, None, 26.2, 20.2, 30.0, 90)
    assert rows(report)[1] == (1000.0, 118.0, 24.6, 18.6, 0.0, 20)  # 36020: north is 0


# --- Several tropopauses and maximum winds ---------------------------------------------------


def test_two_tropopauses_and_three_maximum_winds():
    report = parse_report(A.SBSM_THREE_MAX_WINDS_TTAA)
    assert rows(report, LevelType.TROPOPAUSE) == [
        (223.0, None, -56.5, -61.0, 275.0, 87),
        (143.0, None, -59.3, -83.3, 295.0, 62),
    ]
    assert rows(report, LevelType.MAX_WIND) == [
        (220.0, None, None, None, 275.0, 87),
        (143.0, None, None, None, 295.0, 62),
        (119.0, None, None, None, 305.0, 61),
    ]
    assert shears(report) == [(26, 8), (23, 14), (15, 22)]
    assert rows(report)[1] == (1000.0, 16.0, None, None, None, None)


def test_two_tropopauses_and_a_wind_of_119_knots():
    report = parse_report(A.SBFI_TWO_TROPOPAUSES_TTAA)
    assert rows(report, LevelType.TROPOPAUSE) == [
        (182.0, None, -61.3, -64.6, 280.0, 106),
        (112.0, None, -67.7, -85.7, 285.0, 58),
    ]
    assert rows(report, LevelType.MAX_WIND) == [(215.0, None, None, None, 290.0, 119)]
    assert shears(report) == [(7, 18)]
    assert rows(report, LevelType.MANDATORY)[8] == (200.0, 12250.0, -56.5, -61.4, 285.0, 117)


def test_part_c_tropopause_and_two_maximum_winds():
    """426// is a shear below of 26 kt and none above."""
    report = parse_report(A.SBUG_TWO_MAX_WINDS_TTCC)
    assert rows(report, LevelType.TROPOPAUSE) == [(84.9, None, -73.1, -89.1, 300.0, 54)]
    assert rows(report, LevelType.MAX_WIND) == [
        (79.5, None, None, None, 275.0, 62),
        (12.6, None, None, None, 295.0, 60),
    ]
    assert shears(report) == [(33, 38), (26, None)]
    assert heights(report) == {70.0: 18590.0, 50.0: 20630.0, 30.0: 23780.0, 20.0: 26330.0}


# --- Reports that end early ------------------------------------------------------------------


def test_id_7_report_cut_at_500hpa():
    """Winds down to 700 hPa only, so 50585 ///// is the whole level: a height."""
    report = parse_report(A.SBGL_CUT_AT_500_TTAA)
    assert report.top_wind_indicator == 7
    assert rows(report)[-2:] == [
        (700.0, 3144.0, 8.8, 7.0, 260.0, 22),
        (500.0, 5850.0, None, None, None, None),
    ]
    assert len(report.levels) == 6


def test_id_4_report_cut_at_400hpa():
    report = parse_report(A.SBMT_ID_4_TTAA)
    assert report.top_wind_indicator == 4
    assert rows(report)[0] == (937.0, None, 20.0, 19.0, 190.0, 2)
    assert rows(report)[1] == (1000.0, 152.0, None, None, None, None)
    assert rows(report)[-1] == (400.0, 7620.0, -16.1, -17.5, 320.0, 9)
    assert len(report.levels) == 7


def test_part_c_without_a_level():
    report = parse_report(A.SBCG_EMPTY_C_TTCC)
    assert report.levels == []
    assert report.sounding_system is not None


def test_surface_only_report():
    """99904 22710: 904 hPa and -22.7 C as coded; Part B says 00004, which is 1004 hPa."""
    part_a = parse_report(A.SBTG_SURFACE_ONLY_TTAA)
    assert rows(part_a) == [(904.0, None, -22.7, -23.7, 70.0, 3)]
    part_b = parse_report(A.SBTG_SURFACE_ONLY_TTBB)
    assert rows(part_b) == [(1004.0, None, -22.7, -23.7, None, None)]
    df_main, _ = decode(A.SBTG_SURFACE_ONLY_TTAA, A.SBTG_SURFACE_ONLY_TTBB)
    assert list(df_main["Pressure"]) == [1004.0, 904.0]


# --- Forms that 2.0.2 read wrongly -----------------------------------------------------------


def test_height_only_level_whose_height_ends_in_000_metres():
    """30400 ///// in Part C is 24000 m; only hhh = 000 with nothing else is no height."""
    report = parse_report(A.SBLO_HEIGHT_ONLY_30_TTCC)
    assert rows(report, LevelType.MANDATORY) == [
        (70.0, 18750.0, -63.1, -88.1, 295.0, 24),
        (50.0, 20830.0, -59.3, -88.3, 345.0, 9),
        (30.0, 24000.0, None, None, None, None),
    ]
    padded = parse_report(A.SBLO_HEIGHT_ONLY_30_TTCC.replace("30400", "30000"))
    assert list(heights(padded)) == [70.0, 50.0]


@pytest.mark.parametrize(
    "groups, level, pressure, height",
    [
        ("20215 52370 23658", "20200", 200.0, 12000.0),
        ("15398 59173 24616", "15400", 150.0, 14000.0),
        ("10648 62975 25569", "10600", 100.0, 16000.0),
    ],
)
def test_height_only_levels_in_part_a(groups, level, pressure, height):
    """The same in Part A, where a height in decametres may end in 00."""
    report = parse_report(A.SBSM_JET_TTAA.replace(groups, f"{level} ///// /////"))
    assert heights(report)[pressure] == height
    assert len(report.of_type(LevelType.MANDATORY)) == 11
    padded = parse_report(A.SBSM_JET_TTAA.replace(groups, f"{level[:2]}000 ///// /////"))
    assert pressure not in heights(padded)
    assert len(padded.of_type(LevelType.MANDATORY)) == 10


def test_part_d_that_starts_with_100hpa():
    """11100 80557 is the 100 hPa level that ends Part B (99100 80557), not 10.0 hPa."""
    part_d = parse_report(A.SBCG_PART_D_100_TTDD)
    assert rows(part_d, LevelType.SIG_TEMP)[:3] == [
        (100.0, None, -80.5, -87.5, None, None),
        (92.9, None, -78.1, -87.1, None, None),
        (82.1, None, -63.9, -81.9, None, None),
    ]
    assert len(part_d.of_type(LevelType.SIG_TEMP)) == 7
    assert rows(part_d, LevelType.SIG_WIND)[0] == (94.5, None, None, None, 240.0, 29)
    part_b = parse_report(A.SBCG_PART_D_100_TTBB)
    assert rows(part_b, LevelType.SIG_TEMP)[-1] == (100.0, None, -80.5, -87.5, None, None)
    df_main, _ = decode(None, A.SBCG_PART_D_100_TTBB, None, A.SBCG_PART_D_100_TTDD)
    assert (df_main["Pressure"] == 100.0).sum() == 1
    assert df_main["Pressure"].min() == 31.0


def test_part_c_tropopause_coded_100_is_at_100hpa():
    """88100 80557 25534 is the same level again; a second tropopause coded 100 is 10.0 hPa."""
    report = parse_report(A.SBCG_PART_D_100_TTCC)
    assert rows(report, LevelType.TROPOPAUSE) == [(100.0, None, -80.5, -87.5, 255.0, 34)]
    assert heights(report) == {70.0: 18780.0, 50.0: 20830.0, 30.0: 24020.0}
    df_main, df_special = decode(None, A.SBCG_PART_D_100_TTBB, A.SBCG_PART_D_100_TTCC, A.SBCG_PART_D_100_TTDD)
    assert df_main["Pressure"].min() == 30.0
    assert (df_main["Pressure"] == 100.0).sum() == 1
    assert list(df_special[df_special["Symbol"] == "PtPtPt"]["Value"]) == ["100.0hPa"]
    second = parse_report(A.SBCG_PART_D_100_TTCC.replace("88100 80557 25534", "88850 80557 25534 88100 45782 27010"))
    assert [lv.pressure_hpa for lv in second.of_type(LevelType.TROPOPAUSE)] == [85.0, 10.0]


def test_part_d_level_at_10hpa_is_kept():
    """100 is 10.0 hPa when the level after it is higher, and when it is not the first level."""
    first = parse_report("TTDD 8100/ 83612 11100 45782 22085 44183=")
    assert [lv.pressure_hpa for lv in first.levels] == [10.0, 8.5]
    alone = parse_report("TTDD 8100/ 83612 11100 45782=")
    assert [lv.pressure_hpa for lv in alone.levels] == [10.0]
    later = parse_report("TTDD 8100/ 83612 11150 50581 22100 45782 33085 44183=")
    assert [lv.pressure_hpa for lv in later.levels] == [15.0, 10.0, 8.5]


def test_surface_coded_00_in_part_a():
    """Id = / gives 1000 hPa no wind group, so 00986 29256 33005 is the surface of Part B."""
    part_a = parse_report(A.SBCY_SURFACE_00_TTAA)
    assert rows(part_a) == [(986.0, None, 29.2, 23.2, 330.0, 5)]
    assert part_a.levels[0].level_type is LevelType.SURFACE
    df_main, _ = decode(A.SBCY_SURFACE_00_TTAA, A.SBCY_SURFACE_00_TTBB)
    assert list(df_main["Pressure"]) == [986.0]
    assert list(df_main["Source"]) == ["Surface"]


@pytest.mark.parametrize(
    "text, expected",
    [
        # Id = 1: a 1000 hPa level with its wind group
        ("TTAA 55001 83362 00986 29256 33005 88999 77999=", [(1000.0, -486.0)]),
        # Id = /, but the levels go on: a 1000 hPa level
        ("TTAA 5500/ 83362 00123 27244 92808 21223 85539 19667 88999 77999=", [(1000.0, 123.0), (925.0, 808.0), (850.0, 1539.0)]),
    ],
)
def test_00_group_that_is_a_1000hpa_level(text, expected):
    report = parse_report(text)
    assert report.of_type(LevelType.SURFACE) == []
    assert [(lv.pressure_hpa, lv.height_m) for lv in report.levels] == expected


def test_missing_layer_marker_at_the_end_of_the_temperature_levels():
    """88/// 599//: the layer has no level to close it, and the winds after 21212 are read."""
    report = parse_report(A.SBUL_LAYER_AT_TOP_TTDD)
    temps = rows(report, LevelType.SIG_TEMP)
    assert temps[0] == (98.5, None, -78.1, -86.1, None, None)
    assert temps[-1] == (50.4, None, -65.1, -89.1, None, None)
    assert len(temps) == 7
    winds = rows(report, LevelType.SIG_WIND)
    assert winds[0] == (96.8, None, None, None, 310.0, 22)
    assert winds[-1] == (35.9, None, None, None, 85.0, 7)
    assert len(winds) == 18
    assert report.missing_layers == []


# --- Size ------------------------------------------------------------------------------------


def test_part_d_with_more_than_a_thousand_wind_levels():
    """
    SBBE (82244), 2026-10-27 12 UTC sent 1264 winds in Part D, most of them the same pressure
    repeated (... 88200 23034 99200 23034 11200 23034 ...). Every one is a level of the report;
    the merged profile has each pressure once.
    """
    winds = " ".join(f"{n}{n}{200 - k // 6:03d} 23034" for k, n in ((k, k % 9 + 1) for k in range(1200)))
    text = f"TTDD 7712/ 82244 11923 81556 22889 76559 21212 {winds} 31313 42308 81149="
    report = parse_report(text)
    assert len(report.of_type(LevelType.SIG_WIND)) == 1200
    assert report.sounding_system is not None
    df_main, _ = decode(None, None, None, text)
    assert df_main["Pressure"].is_unique
    assert len(df_main) == 202

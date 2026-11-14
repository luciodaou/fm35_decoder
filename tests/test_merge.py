"""Merging the parts of a sounding, heights, interpolation and station tables."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from fm35_decoder import (
    LevelType,
    ReportPart,
    WmoHeader,
    decode_soundings,
    load_station_table,
    merge_parts,
    merge_reports,
    parse_report,
)
from fm35_decoder.groups import FT_TO_M
from fm35_decoder.stations import parse_station_line

from samples import KT, SBGL_TTAA, SBGL_TTBB, SBGL_TTCC, SBGL_TTDD, TTAA_CG

REFERENCE = datetime(2026, 11, 13, 15, tzinfo=timezone.utc)
STATION_LINES = [
    "ENJA      01001 JAN_MAYEN                        -- NO  7094   -867     9  0                    ",
    "SBGL      83746 GALEAO                           -- BZ -2282  -4325     6  0                    ",
    "! a comment",
    "DBBH          0 METEOR                              DL     0      0     0  1661                 ",
]


def by_pressure(sounding):
    return {lv.pressure_hpa: lv for lv in sounding.profile}


def sbgl(**kwargs):
    reports = [parse_report(text, reference_time=REFERENCE) for text in (SBGL_TTAA, SBGL_TTBB, SBGL_TTCC, SBGL_TTDD)]
    return merge_parts(reports, **kwargs)


def test_four_parts_make_one_profile():
    sounding = sbgl()
    assert sounding.station_id == "83746"
    assert sounding.timestamp_utc == datetime(2026, 11, 11, 0, tzinfo=timezone.utc)
    assert sounding.parts == (ReportPart.TTAA, ReportPart.TTBB, ReportPart.TTCC, ReportPart.TTDD)
    pressures = [lv.pressure_hpa for lv in sounding.profile]
    assert pressures == sorted(set(pressures), reverse=True)
    assert pressures[0] == 1026.0 and pressures[-1] == 20.0 and len(pressures) == 99

    rows = by_pressure(sounding)
    # a standard level keeps what Part A reports; nothing is derived there
    assert rows[850.0].level_type is LevelType.MANDATORY and rows[850.0].derived == ()
    assert (rows[850.0].height_m, rows[850.0].temp_c, rows[850.0].wind_dir_deg) == (1607.0, 11.0, 45.0)
    # the surface of Part A and level 00 of Part B are one level
    assert rows[1026.0].level_type is LevelType.SURFACE
    # a significant temperature level has no wind, a significant wind level no temperature
    assert rows[915.0].level_type is LevelType.SIG_TEMP and rows[915.0].wind_speed_ms is None
    assert rows[949.0].level_type is LevelType.SIG_WIND and rows[949.0].temp_c is None
    # the tropopause joins the significant level at the same pressure and gives it its wind
    assert rows[102.0].level_type is LevelType.SIG_TEMP
    assert rows[102.0].wind_speed_ms == pytest.approx(35 * KT)
    assert [lv.pressure_hpa for lv in sounding.tropopauses] == [102.0, 42.6]
    assert [lv.pressure_hpa for lv in sounding.max_winds] == [213.0]


def test_heights_are_computed_between_the_reported_ones():
    rows = by_pressure(sbgl())
    assert rows[915.0].derived == ("height_m",)
    assert 894.0 < rows[919.0].height_m < rows[915.0].height_m < rows[850.0].height_m
    assert 970 < rows[915.0].height_m < 1000
    # the surface, below the 1000 hPa level, is computed downwards: Galeao is at 6 m
    assert rows[1026.0].height_m == pytest.approx(6.0, abs=5.0)
    assert rows[20.0].height_m == 26480.0 and rows[20.0].derived == ()
    assert rows[20.2].height_m == pytest.approx(26420.0, abs=15.0)


def test_surface_height_from_the_station_table():
    table = load_station_table(STATION_LINES)
    sounding = sbgl(station_meta=table["83746"])
    assert sounding.station_meta.name == "GALEAO"
    assert by_pressure(sounding)[1026.0].height_m == 6.0


def test_station_table():
    table = load_station_table(STATION_LINES)
    assert sorted(table) == ["01001", "83746", "DBBH"]
    station = table["83746"]
    assert (station.stid, station.stnm, station.country) == ("SBGL", 83746, "BZ")
    assert (station.latitude, station.longitude, station.elevation_m) == (-22.82, -43.25, 6.0)
    assert parse_station_line("garbage") is None


def test_interpolation_is_optional_and_named():
    plain, filled = by_pressure(sbgl()), by_pressure(sbgl(interpolate=True))
    assert plain[949.0].temp_c is None
    level = filled[949.0]
    assert level.derived == ("height_m", "temp_c", "dewpoint_c")
    assert 14.2 < level.temp_c < 19.8 and level.dewpoint_c <= level.temp_c
    wind = filled[915.0]
    assert set(wind.derived) == {"height_m", "wind_dir_deg", "wind_speed_ms"}
    assert 45.0 < wind.wind_dir_deg < 80.0  # between 080 at 919 hPa and 045 at 849 hPa
    # nothing is made up above the last observation: 20 hPa reports ///// and has no wind group
    top = filled[20.0]
    assert (top.temp_c, top.wind_speed_ms, top.derived) == (None, None, ())
    # reported values are never changed
    for pressure, level in plain.items():
        for name in ("temp_c", "dewpoint_c", "wind_dir_deg", "wind_speed_ms"):
            if getattr(level, name) is not None:
                assert getattr(filled[pressure], name) == getattr(level, name)


def test_missing_layers_are_not_interpolated():
    report = parse_report(
        "TTBB 80128 83612 00951 16805 11900 14420 22/// ///// 33700 02041 44500 10560 "
        "21212 00951 09017 11940 08543 22850 10020 33/// ///// 44600 27030 55500 27040="
    )
    sounding = merge_parts([report], interpolate=True)
    rows = by_pressure(sounding)
    assert rows[850.0].temp_c is None and rows[850.0].dewpoint_c is None
    assert rows[940.0].temp_c is not None and rows[600.0].temp_c is not None
    assert rows[700.0].wind_speed_ms is None and rows[900.0].wind_speed_ms is not None
    assert len(sounding.missing_layers) == 2
    # a lone Part B has no heights: only Parts A and C report any
    assert all(lv.height_m is None for lv in sounding.profile)


def test_dew_point_is_not_interpolated_above_the_temperature():
    """An inversion between two levels: the interpolated dew point stays at or below the temperature."""
    report = parse_report(
        "TTBB 80128 83612 00951 10000 11800 20060 21212 00951 09017 11900 08543 22800 08040="
    )
    level = by_pressure(merge_parts([report], interpolate=True))[900.0]
    assert level.dewpoint_c <= level.temp_c


def test_heights_above_the_last_temperature_are_bounded():
    """Regulation 35.2.2.4: within 25 hPa and a quarter of the pressure of the level."""
    ttcc = parse_report("TTCC 80123 83612 70873 72159 27518 50079 ///// 05504=")
    ttdd = parse_report("TTDD 8012/ 83612 11650 70160 21212 11600 27010 22400 27020=")
    rows = by_pressure(merge_parts([parse_report(TTAA_CG), ttcc, ttdd]))
    assert 19100 < rows[65.0].height_m < 19250
    assert 19550 < rows[60.0].height_m < 19750  # 5 hPa above the last temperature
    assert rows[50.0].height_m == 20790.0  # reported
    assert rows[40.0].height_m is None  # 25 hPa above, more than a quarter of 40 hPa


def test_first_report_of_a_part_is_kept_unless_corrected():
    first = parse_report(TTAA_CG)
    again = parse_report(TTAA_CG.replace("85521 17434", "85521 19434"))
    assert by_pressure(merge_parts([first, again]))[850.0].temp_c == 17.4
    again.header = WmoHeader("USBZ01", "SBCG", "301200", "CCA")
    assert by_pressure(merge_parts([first, again]))[850.0].temp_c == 19.4
    again.header = replace(again.header, bbb="")
    assert by_pressure(merge_parts([first, again]))[850.0].temp_c == 17.4


def test_soundings_are_grouped_by_station_and_time():
    other_station = SBGL_TTAA.replace("83746", "83779")
    later = SBGL_TTBB.replace("TTBB 61008", "TTBB 61128")
    text = "\n".join([SBGL_TTAA, other_station, SBGL_TTBB, later, "TTCC 61003 83746 NIL=", "TTAA 61001 83999 NIL="])
    soundings = decode_soundings(text, reference_time=REFERENCE)
    assert [(s.station_id, s.timestamp_utc.hour, [p.value for p in s.parts]) for s in soundings] == [
        ("83746", 0, ["TTAA", "TTBB"]),
        ("83779", 0, ["TTAA"]),
        ("83746", 12, ["TTBB"]),
    ]
    # an observation an hour off the synoptic time belongs to it
    eleven = parse_report(SBGL_TTBB.replace("TTBB 61008", "TTBB 61238"), reference_time=REFERENCE)
    midnight = parse_report(SBGL_TTAA.replace("TTAA 61001", "TTAA 62001"), reference_time=REFERENCE)
    assert len(merge_reports([eleven, midnight])) == 1


def test_undecodable_reports_are_left_out(caplog):
    text = "TTAA 61001 8374 99026 21450 09004=\n" + SBGL_TTAA
    with caplog.at_level("WARNING", logger="fm35_decoder"):
        (sounding,) = decode_soundings(text, reference_time=REFERENCE)
    assert sounding.station_id == "83746"
    assert "report left out" in caplog.text


def test_pilot_winds_join_the_profile():
    ppaa = parse_report("PPAA 61001 83746 55385 09011 29514 24537=")
    ppbb = parse_report("PPBB 61000 83746 9012/ 09011 08020 949// 25083 999// 25068 21212 00026 09004 11949 09011=")
    sounding = merge_parts([parse_report(SBGL_TTAA), ppaa, ppbb])
    rows = by_pressure(sounding)
    assert rows[949.0].level_type is LevelType.SIG_WIND
    # Part A already has the winds of the standard levels
    assert rows[850.0].wind_dir_deg == 45.0
    # winds on heights within the heights of the profile get a pressure from them
    placed = [lv for lv in sounding.profile if lv.derived == ("pressure_hpa",)]
    assert [lv.height_m for lv in placed] == [round(h * 1000 * FT_TO_M, 1) for h in (49, 2, 1)][::-1]
    assert 1000.0 > placed[0].pressure_hpa > placed[1].pressure_hpa > 925.0
    assert 150.0 > placed[2].pressure_hpa > 100.0
    # 99000 ft is above the top of Part A (100 hPa at 16650 m)
    assert [lv.height_m for lv in sounding.height_winds] == [round(99000 * FT_TO_M, 1)]


def test_empty_input():
    assert decode_soundings("") == []
    sounding = merge_parts([])
    assert sounding.profile == [] and sounding.station_id == ""

"""Decoding of the parts, following the GEMPAK routines RU_TTAA to RU_PPDD."""

import pytest

from fm35_decoder import LevelType, MissingLayer, ReportPart, SoundingSystem, parse_report
from fm35_decoder.groups import FT_TO_M

from samples import KT, SBGL_TTAA, SBGL_TTBB, SBGL_TTCC, SBGL_TTDD, TTAA_CG


def pressures(report, *types):
    return [lv.pressure_hpa for lv in (report.of_type(*types) if types else report.levels)]


def level(report, pressure, level_type=None):
    found = [
        lv for lv in report.levels
        if lv.pressure_hpa == pressure and (level_type is None or lv.level_type is level_type)
    ]
    assert len(found) == 1, found
    return found[0]


# --- Part A ---------------------------------------------------------------------------------


def test_part_a_of_a_real_report():
    report = parse_report(SBGL_TTAA)
    assert pressures(report, LevelType.SURFACE, LevelType.MANDATORY) == [
        1026.0, 1000.0, 925.0, 850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0, 150.0, 100.0,
    ]
    surface = report.levels[0]
    assert surface.level_type is LevelType.SURFACE and surface.height_m is None
    assert (surface.temp_c, surface.dewpoint_c, surface.wind_dir_deg) == (21.4, 16.4, 90.0)
    assert surface.wind_speed_ms == pytest.approx(4 * KT)

    assert [lv.height_m for lv in report.of_type(LevelType.MANDATORY)] == [
        228.0, 894.0, 1607.0, 3212.0, 5900.0, 7600.0, 9690.0, 10940.0, 12400.0, 14220.0, 16650.0,
    ]
    top = level(report, 100.0)
    assert (top.temp_c, top.dewpoint_c, top.wind_dir_deg) == (-73.9, -85.9, 245.0)
    assert top.wind_speed_ms == pytest.approx(29 * KT)

    (tropopause,) = report.of_type(LevelType.TROPOPAUSE)
    assert (tropopause.pressure_hpa, tropopause.temp_c, tropopause.dewpoint_c) == (102.0, -73.7, -85.7)
    assert (tropopause.wind_dir_deg, tropopause.wind_speed_ms) == (240.0, pytest.approx(35 * KT))

    (max_wind,) = report.of_type(LevelType.MAX_WIND)
    assert (max_wind.pressure_hpa, max_wind.wind_dir_deg) == (213.0, 250.0)
    assert max_wind.wind_speed_ms == pytest.approx(83 * KT)
    assert (max_wind.shear_below_ms, max_wind.shear_above_ms) == (pytest.approx(18 * KT), pytest.approx(12 * KT))

    assert report.sounding_system == SoundingSystem("4", "23", "08", "23:31")
    assert report.raw_remarks == ["31313 42308 82331"]


def test_wind_speeds_in_metres_per_second():
    """YY without 50 added: speeds are in m/s and are not converted."""
    report = parse_report(TTAA_CG.replace("TTAA 80121", "TTAA 30121"))
    assert level(report, 700.0).wind_speed_ms == 28.0
    assert report.of_type(LevelType.MAX_WIND)[0].shear_below_ms == 31.0


def test_temperatures_that_look_like_indicators():
    """-66.5 C at 150 hPa (66562) and -77.1 C at 100 hPa (77161) are read by their position."""
    report = parse_report(TTAA_CG)
    assert level(report, 150.0).temp_c == -66.5
    assert level(report, 100.0).temp_c == -77.1
    assert pressures(report, LevelType.MAX_WIND) == [146.0]


def test_underground_level_keeps_its_height_only():
    lvl = level(parse_report(TTAA_CG), 1000.0)
    assert (lvl.height_m, lvl.temp_c, lvl.wind_speed_ms) == (122.0, None, None)


def test_wind_groups_follow_id():
    """Id = / : no standard level has a wind group, so none is taken for a wind."""
    report = parse_report(
        "TTAA 8012/ 83612 99951 16805 ///// 00122 ///// 92793 17837 85521 17434 70157 08400 "
        "50587 05704 40758 17910 30966 34926 25091 44340 20237 55934 15417 62562 10662 69961 88999 77999="
    )
    assert pressures(report) == [951.0, 1000.0, 925.0, 850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0, 150.0, 100.0]
    assert all(lv.wind_speed_ms is None for lv in report.levels)
    assert level(report, 100.0).temp_c == -69.9


def test_id_5_gives_winds_up_to_500hpa():
    text = TTAA_CG.replace("TTAA 80121", "TTAA 80125")
    for group in (" 25022", " 22516", " 20022", " 23524", " 24581", " 19509"):
        text = text.replace(group, "", 1)
    report = parse_report(text)
    assert level(report, 500.0).wind_dir_deg == 260.0
    assert level(report, 400.0).wind_speed_ms is None
    assert level(report, 100.0).temp_c == -77.1


def test_925hpa_may_be_absent():
    report = parse_report(TTAA_CG.replace(" 92793 17837 07545", ""))
    assert pressures(report, LevelType.MANDATORY)[:3] == [1000.0, 850.0, 700.0]


def test_search_for_the_next_level_after_a_bad_group():
    """A stray group between two levels is skipped: 700 hPa is followed by 500 hPa where it should."""
    report = parse_report(TTAA_CG.replace(" 70157", " 12A45 70157"))
    assert pressures(report, LevelType.MANDATORY) == [
        1000.0, 925.0, 850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0, 150.0, 100.0,
    ]


def test_levels_are_taken_in_the_order_of_the_code_form():
    """A level out of place is not a level: a second 500 hPa before 700 hPa is skipped."""
    report = parse_report(TTAA_CG.replace(" 70157", " 50999 01234 27010 70157"))
    assert pressures(report, LevelType.MANDATORY) == [
        1000.0, 925.0, 850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0, 150.0, 100.0,
    ]
    assert level(report, 500.0).height_m == 5870.0


def test_level_not_followed_by_the_next_one_is_not_found_again():
    """After a bad group the search takes 700 hPa only if 500 hPa follows it; here 400 hPa does."""
    report = parse_report(TTAA_CG.replace(" 50587 05704 26019", "").replace(" 70157", " 12A45 70157"))
    assert pressures(report, LevelType.MANDATORY)[2:5] == [850.0, 400.0, 300.0]


def test_level_without_height_is_dropped():
    report = parse_report(TTAA_CG.replace("85521", "85///"))
    assert 850.0 not in pressures(report)
    assert level(report, 700.0).height_m == 3157.0


def test_51515_as_a_temperature():
    """Deviation from GEMPAK: 51515 after PPhhh is -51.5 C with a depression of 1.5 C."""
    report = parse_report(TTAA_CG.replace("20237 55934", "20237 51515"))
    lvl = level(report, 200.0)
    assert (lvl.temp_c, lvl.dewpoint_c, lvl.wind_dir_deg) == (-51.5, -53.0, 235.0)
    assert level(report, 100.0).temp_c == -77.1
    assert report.sounding_system is not None


def test_51515_ends_the_level_data():
    report = parse_report(TTAA_CG.replace(" 31313", " 51515 10164 00098 10194 22513 27015 31313"))
    assert pressures(report, LevelType.MANDATORY)[-1] == 100.0
    assert pressures(report, LevelType.MAX_WIND) == [146.0]
    assert report.raw_remarks[-1].startswith("51515 10164 00098")
    # before the tropopause: nothing after it is decoded
    cut = parse_report(TTAA_CG.replace(" 88999", " 51515 10164 88999"))
    assert cut.of_type(LevelType.MAX_WIND) == []


def test_tropopauses():
    two = parse_report(TTAA_CG.replace("88999", "88120 56565 24050 88105 75162 00000"))
    first, second = two.of_type(LevelType.TROPOPAUSE)
    assert (first.pressure_hpa, first.temp_c, first.dewpoint_c, first.wind_dir_deg) == (120.0, -56.5, -71.5, 240.0)
    # a wind of 0 degrees and 0 speed at the tropopause is taken as missing
    assert (second.pressure_hpa, second.temp_c, second.wind_dir_deg, second.wind_speed_ms) == (105.0, -75.1, None, None)
    assert pressures(two, LevelType.MAX_WIND) == [146.0]


def test_tropopause_without_pressure_keeps_its_groups():
    """88/// is dropped with its temperature and wind groups, which are not read as levels."""
    report = parse_report(TTAA_CG.replace("88999", "88/// 50580 24050"))
    assert report.of_type(LevelType.TROPOPAUSE) == []
    assert pressures(report).count(500.0) == 1
    assert pressures(report, LevelType.MAX_WIND) == [146.0]


def test_maximum_winds():
    report = parse_report(TTAA_CG.replace("77146 24083 43131", "66120 24583 77146 24083 43131 77/// 24083 77300 /////"))
    first, second = report.of_type(LevelType.MAX_WIND)
    assert (first.pressure_hpa, first.wind_dir_deg, first.shear_below_ms) == (120.0, 245.0, None)
    assert (second.pressure_hpa, second.shear_above_ms) == (146.0, pytest.approx(31 * KT))
    assert parse_report(TTAA_CG.replace("77146", "77999 77146")).of_type(LevelType.MAX_WIND) == []
    assert pressures(parse_report(TTAA_CG.replace("77146", "66999 77146")), LevelType.MAX_WIND) == [146.0]


def test_41414_after_a_maximum_wind_is_shear():
    """The cloud section belongs to Part B: in Part A, 41414 is 14 and 14 knots of shear."""
    report = parse_report(TTAA_CG.replace("43131", "41414"))
    (max_wind,) = report.of_type(LevelType.MAX_WIND)
    assert max_wind.shear_below_ms == pytest.approx(14 * KT)
    assert report.cloud_group is None


def test_31313_as_a_temperature_is_not_the_section():
    report = parse_report(TTAA_CG.replace("30966 34926", "30966 31313").replace(" 31313 42308 81137", ""))
    assert level(report, 300.0).temp_c == -31.3 and level(report, 300.0).wind_dir_deg == 225.0
    assert report.sounding_system is None and report.raw_remarks == []


def test_31313_without_the_sounding_system_group():
    report = parse_report(TTAA_CG.replace("31313 42308 81137", "31313 81137"))
    assert report.sounding_system == SoundingSystem(None, None, None, "11:37")


# --- Part C ---------------------------------------------------------------------------------


def test_part_c_of_a_real_report():
    report = parse_report(SBGL_TTCC)
    assert report.part is ReportPart.TTCC
    assert pressures(report, LevelType.MANDATORY) == [70.0, 50.0, 30.0, 20.0]
    assert [lv.height_m for lv in report.of_type(LevelType.MANDATORY)] == [18740.0, 20770.0, 23910.0, 26480.0]
    # Id = 3: 20 hPa has no wind group, and ///// is its temperature
    top = level(report, 20.0)
    assert (top.temp_c, top.wind_speed_ms) == (None, None)
    (tropopause,) = report.of_type(LevelType.TROPOPAUSE)
    assert (tropopause.pressure_hpa, tropopause.temp_c, tropopause.wind_dir_deg) == (42.6, -64.9, 65.0)
    assert report.of_type(LevelType.MAX_WIND) == []


def test_part_c_special_pressures_in_tenths():
    report = parse_report(
        "TTCC 80123 83612 70873 72159 27518 50079 64561 05504 30399 57761 06507 88860 75559 24004 77650 25070 41012="
    )
    assert pressures(report, LevelType.TROPOPAUSE) == [86.0]
    assert pressures(report, LevelType.MAX_WIND) == [65.0]


def test_part_c_id_1_and_0_give_every_level_a_wind():
    for indicator in "10":
        report = parse_report(f"TTCC 8012{indicator} 83612 70873 72159 27518 50079 64561 30014 30399 57761 06507=")
        assert pressures(report) == [70.0, 50.0, 30.0]
        assert level(report, 50.0).wind_dir_deg == 300.0


# --- Parts B and D ----------------------------------------------------------------------------


def test_part_b_of_a_real_report():
    report = parse_report(SBGL_TTBB)
    temps, winds = report.of_type(LevelType.SIG_TEMP), report.of_type(LevelType.SIG_WIND)
    assert len(temps) == 27 and len(winds) == 24
    assert (temps[0].pressure_hpa, temps[0].temp_c, temps[0].dewpoint_c) == (1026.0, 21.4, 16.4)
    assert (temps[-1].pressure_hpa, temps[-1].temp_c) == (100.0, -73.9)
    assert (winds[0].pressure_hpa, winds[0].wind_dir_deg) == (1026.0, 90.0)
    assert (winds[-1].pressure_hpa, winds[-1].wind_dir_deg) == (100.0, 245.0)
    assert winds[-1].wind_speed_ms == pytest.approx(30 * KT)
    assert report.cloud_group == "856//"
    assert report.raw_remarks == ["31313 42308 82331", "41414 856//"]


def test_part_d_pressures_in_tenths():
    report = parse_report(SBGL_TTDD)
    temps, winds = report.of_type(LevelType.SIG_TEMP), report.of_type(LevelType.SIG_WIND)
    assert [lv.pressure_hpa for lv in temps] == [89.5, 80.1, 75.3, 67.8, 49.9, 42.6, 20.2]
    assert len(winds) == 31 and winds[0].pressure_hpa == 94.6 and winds[-1].pressure_hpa == 20.2


def test_21212_as_a_temperature():
    """Deviation from GEMPAK: 21212 after a level group is 21.2 C with a depression of 1.2 C."""
    report = parse_report("TTBB 80128 83612 00951 21212 11931 16420 22911 19041 21212 00951 09017 11940 08543=")
    assert pressures(report, LevelType.SIG_TEMP) == [951.0, 931.0, 911.0]
    assert pressures(report, LevelType.SIG_WIND) == [951.0, 940.0]
    assert (report.levels[0].temp_c, report.levels[0].dewpoint_c) == (21.2, 20.0)
    assert report.levels[-1].wind_speed_ms == pytest.approx(43 * KT)


def test_pressures_of_1000hpa_and_more():
    report = parse_report("TTBB 53008 83746 00021 20245 11021 18423 22017 21056 33952 16024=")
    assert pressures(report) == [1021.0, 1021.0, 1017.0, 952.0]


def test_level_out_of_sequence_is_taken_if_the_pressure_decreases():
    """nn jumps from 11 to 33 (a group lost in transmission): the level is kept, and so are the next."""
    report = parse_report("TTBB 53008 83746 00021 20245 11990 18423 33917 21056 44852 16024=")
    assert pressures(report) == [1021.0, 990.0, 917.0, 852.0]


def test_level_out_of_sequence_is_dropped_if_the_next_does_not_follow_it():
    report = parse_report("TTBB 53008 83746 00021 20245 11990 18423 33917 21056 55852 16024 66800 14024=")
    assert pressures(report) == [1021.0, 990.0, 852.0, 800.0]


def test_level_with_a_rising_pressure_is_not_a_level():
    report = parse_report("TTBB 53008 83746 00021 20245 11915 13407 33950 10800 44757 08009=")
    assert pressures(report) == [1021.0, 915.0, 757.0]


def test_levels_without_data_are_not_kept():
    report = parse_report(
        "TTBB 53008 83746 00021 20245 11990 ///// 22917 21056 21212 00021 ///// 11990 27010 22917 27///="
    )
    assert pressures(report, LevelType.SIG_TEMP) == [1021.0, 917.0]
    assert pressures(report, LevelType.SIG_WIND) == [990.0]


def test_part_b_without_a_surface_level():
    report = parse_report("TTBB 53008 83746 11915 13407 22842 10800=")
    assert pressures(report) == [915.0, 842.0]


def test_layers_of_missing_data():
    """nn/// ///// (35.3.1.6, 35.3.2.2) is recorded and keeps its place in the sequence of nn."""
    report = parse_report(
        "TTBB 80128 83612 00951 16805 11900 14420 22/// ///// 33700 02041 44/// ///// 55500 10560 "
        "21212 00951 09017 11940 08543 22850 10020 33/// ///// 44600 27030 55500 27040="
    )
    assert pressures(report, LevelType.SIG_TEMP) == [951.0, 900.0, 700.0, 500.0]
    assert pressures(report, LevelType.SIG_WIND) == [951.0, 940.0, 850.0, 600.0, 500.0]
    assert report.missing_layers == [
        MissingLayer(LevelType.SIG_TEMP, 900.0, 700.0),
        MissingLayer(LevelType.SIG_TEMP, 700.0, 500.0),
        MissingLayer(LevelType.SIG_WIND, 850.0, 600.0),
    ]


def test_regional_section_ends_part_b():
    report = parse_report(
        "TTBB 80128 83612 00951 16805 11931 16420 21212 00951 09017 11940 08543 51515 10164 00098 10194 22513 27015="
    )
    assert pressures(report) == [951.0, 931.0, 951.0, 940.0]
    assert report.raw_remarks == ["51515 10164 00098 10194 22513 27015"]


# --- PILOT ------------------------------------------------------------------------------------


def test_pilot_part_a():
    report = parse_report("PPAA 61001 83746 55385 09011 29514 24537 55340 24546 25568 26574 55120 25078 77213 25083=")
    assert report.part is ReportPart.PPAA
    assert pressures(report) == [850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0]
    assert all(lv.level_type is LevelType.MANDATORY and lv.temp_c is None for lv in report.levels)
    assert (report.levels[1].wind_dir_deg, report.levels[1].wind_speed_ms) == (295.0, pytest.approx(14 * KT))


def test_pilot_part_c():
    report = parse_report("PPCC 61001 83746 55370 30014 09012 12014 55120 06513=")
    assert pressures(report) == [70.0, 50.0, 30.0, 20.0]


def test_pilot_part_b_on_heights_and_on_pressures():
    report = parse_report(
        "PPBB 61000 83746 90023 09004 09011 08020 9056/ 29015 30013 "
        "21212 00026 09004 11949 09011 22919 08020="
    )
    on_heights = [lv for lv in report.levels if lv.pressure_hpa is None]
    assert [lv.height_m for lv in on_heights] == [
        0.0, round(2000 * FT_TO_M, 1), round(3000 * FT_TO_M, 1), round(5000 * FT_TO_M, 1), round(6000 * FT_TO_M, 1),
    ]
    assert on_heights[3].wind_dir_deg == 290.0
    assert [lv.pressure_hpa for lv in report.levels if lv.pressure_hpa is not None] == [1026.0, 949.0, 919.0]
    assert all(lv.level_type is LevelType.SIG_WIND for lv in report.levels)

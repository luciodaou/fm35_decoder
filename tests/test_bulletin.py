"""Bulletins, reports, report headers and observation times."""

from datetime import datetime, timezone

import pytest

from fm35_decoder import DecodeError, Platform, ReportPart, WindUnit, iter_bulletins, iter_reports, parse_report
from fm35_decoder.bulletin import nominal_time, observation_time

from samples import SBGL_TTAA, SBGL_TTCC

UTC = timezone.utc


def test_bulletins_framed_by_control_characters():
    stream = (
        "\x01\r\r\n123\r\r\nUSBZ01 SBGL 110000\r\r\n" + SBGL_TTAA + "\r\r\n\x03"
        "\x01\r\r\n124\r\r\nULBZ01 SBGL 110000 CCA\r\r\n" + SBGL_TTCC + "\r\r\n\x03"
    )
    first, second = list(iter_bulletins(stream))
    assert (first.header.ttaaii, first.header.cccc, first.header.yygggg, first.header.sequence) == (
        "USBZ01", "SBGL", "110000", "123",
    )
    assert first.header.bbb == "" and not first.header.is_correction
    assert second.header.bbb == "CCA" and second.header.is_correction
    assert first.text == SBGL_TTAA and second.text == SBGL_TTCC


def test_bulletins_split_at_headings_without_control_characters():
    cut = SBGL_TTAA.index(" 70212")
    # the second heading gives its time as MMDDHHMM
    lines = ["USBZ01 SBGL 110000", SBGL_TTAA[:cut], SBGL_TTAA[cut:], "", "ULBZ01 SBGL 11110000 RRA", SBGL_TTCC]
    first, second = list(iter_bulletins(lines))
    assert first.text == SBGL_TTAA
    assert (second.header.yygggg, second.header.bbb) == ("110000", "RRA")


def test_text_without_heading_is_one_bulletin():
    (only,) = list(iter_bulletins(SBGL_TTAA + "\n" + SBGL_TTCC))
    assert only.header is None
    assert len(list(iter_reports(only.text))) == 2


def test_reports_end_at_equals_or_at_the_next_report():
    text = "ZCZC TTAA 61001 83746 99026 21450 09004 TTBB 61008 83746 00026 21450= junk PPBB 61000 83746 90123 09005="
    assert list(iter_reports(text)) == [
        "TTAA 61001 83746 99026 21450 09004 ",
        "TTBB 61008 83746 00026 21450",
        "PPBB 61000 83746 90123 09005",
    ]


def test_header_of_a_land_station():
    report = parse_report(SBGL_TTAA, reference_time=datetime(2026, 11, 13, 15, tzinfo=UTC))
    assert report.part is ReportPart.TTAA and report.platform is Platform.LAND
    assert (report.station_id, report.obs_day, report.obs_hour) == ("83746", 11, 0)
    assert report.wind_unit is WindUnit.KNOTS and report.top_wind_indicator == 1
    assert report.obs_time == datetime(2026, 11, 11, 0, tzinfo=UTC) == report.nominal_time
    assert not report.nil


def test_header_without_knots_and_without_id():
    report = parse_report("TTDD 1112/ 01001 11895 74962=")
    assert report.wind_unit is WindUnit.METERS_PER_SECOND
    assert (report.obs_day, report.obs_hour, report.top_wind_indicator) == (11, 12, None)
    assert report.station_id == "01001"


def test_header_of_a_ship():
    report = parse_report("UUAA WXYZ 61121 99235 70463 08219 99015 20245 09010=")
    assert report.part is ReportPart.TTAA and report.platform is Platform.SHIP
    assert (report.latitude, report.longitude) == (23.5, -46.3)
    assert report.station_id == "WXYZ12"
    assert report.levels[0].pressure_hpa == 1015.0
    anonymous = parse_report("UUBB SHIP 61121 99235 70463 08219 00015 20245=")
    assert anonymous.station_id == "S2350463"


def test_header_of_a_dropsonde():
    text = (
        "XXAA 61187 99235 70463 08219 99015 20245 09010 00130 19843 08509 92804 14212 08019 "
        "85530 11000 04511 88999 77999 31313 09608 81750 61616 AF304 0312A MILTON OB 05 "
        "62626 SPL 2350N04630W 1752 LST WND 012="
    )
    report = parse_report(text)
    assert report.part is ReportPart.TTAA and report.platform is Platform.DROPSONDE
    assert report.station_id == str(5 * 100000 + 18 * 1000 + 304)
    assert [lv.pressure_hpa for lv in report.levels] == [1015.0, 1000.0, 925.0, 850.0]
    with pytest.raises(DecodeError, match="61616"):
        parse_report("XXAA 61187 99235 70463 08219 99015 20245 09010=")


def test_nil_report():
    for text in ("TTAA 61001 83746 NIL=", "TTAA 61001 83746 NIL"):
        report = parse_report(text)
        assert report.nil and report.levels == [] and report.station_id == "83746"


@pytest.mark.parametrize(
    "text",
    ["TTAA", "TTAA 6100", "TTAA 6A001 83746 99026", "TTAA 61001 8374", "TTAA 61001 ABCDE 99026", "TTEE 61001 83746"],
)
def test_invalid_headers_raise(text):
    with pytest.raises(DecodeError):
        parse_report(text)


def test_observation_time_follows_the_reference_time():
    reference = datetime(2026, 12, 1, 2, 30, tzinfo=UTC)
    assert observation_time(reference, 1, 0) == datetime(2026, 12, 1, 0, tzinfo=UTC)
    # A day after the 27th received on the 1st belongs to the month before
    assert observation_time(reference, 30, 12) == datetime(2026, 11, 30, 12, tzinfo=UTC)
    assert observation_time(datetime(2027, 1, 1, 1, tzinfo=UTC), 31, 23) == datetime(2026, 12, 31, 23, tzinfo=UTC)
    # Hour 24 is 00 of the next day
    assert observation_time(reference, 30, 24) == datetime(2026, 12, 1, 0, tzinfo=UTC)
    assert observation_time(reference, 12, 25) is None
    assert observation_time(datetime(2026, 2, 10, tzinfo=UTC), 30, 0) is None


def test_nominal_time_is_the_nearest_three_hours():
    day = datetime(2026, 11, 11, tzinfo=UTC)
    assert nominal_time(day.replace(hour=11)) == day.replace(hour=12)
    assert nominal_time(day.replace(hour=13)) == day.replace(hour=12)
    assert nominal_time(day.replace(hour=12)) == day.replace(hour=12)
    assert nominal_time(day.replace(hour=23)) == datetime(2026, 11, 12, tzinfo=UTC)

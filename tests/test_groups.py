"""Group decoders against the rules of the GEMPAK RU library."""

import pytest

from fm35_decoder.groups import (
    FT_TO_M,
    Fields,
    decode_height,
    decode_pilot_pressures,
    decode_position,
    decode_sig_level,
    decode_temp,
    decode_wind,
    decode_wind_heights,
)

from samples import KT


@pytest.mark.parametrize(
    "group, expected",
    [
        ("12345", (-12.3, -16.8)),  # odd tenths: negative
        ("12462", (12.4, 0.4)),  # depression above 55: whole degrees + 50
        ("00100", (-0.1, -0.1)),
        ("00000", (0.0, 0.0)),
        ("21450", (21.4, 16.4)),  # depression 50: 5.0
        ("21456", (21.4, 15.4)),  # depression 56: 6
        ("21453", (21.4, 18.4)),  # 51-55 are not used by WMO; RU_TEMP reads them as 1-5
        ("619//", (-61.9, None)),
        ("/////", (None, None)),
        ("7/162", (None, None)),
    ],
)
def test_temp(group, expected):
    assert decode_temp(group) == expected


def test_wind_knots_and_five_degrees():
    direction, speed = decode_wind("27620", knots=True)
    assert direction == 275.0
    assert speed == pytest.approx(120 * KT)
    assert decode_wind("27025", knots=False) == (270.0, 25.0)


@pytest.mark.parametrize(
    "group, expected",
    [
        ("36010", (0.0, 10.0)),  # 360 is returned as 0
        ("00000", (0.0, 0.0)),
        ("00010", (0.0, 10.0)),
        ("99025", (None, None)),  # variable: above 360
        ("37010", (None, None)),
        ("36510", (None, None)),  # 365
        ("31313", (None, None)),
        ("/////", (None, None)),
        ("27///", (None, None)),
    ],
)
def test_wind_edges(group, expected):
    assert decode_wind(group, knots=False) == expected


@pytest.mark.parametrize(
    "group, expected",
    [
        ("00163", (1000.0, 163.0)),
        ("00515", (1000.0, -15.0)),  # above 500: below sea level
        ("00500", (1000.0, 500.0)),
        ("92843", (925.0, 843.0)),
        ("92150", (925.0, 1150.0)),
        ("85570", (850.0, 1570.0)),
        ("85950", (850.0, 950.0)),
        ("70207", (700.0, 3207.0)),
        ("70980", (700.0, 2980.0)),
        ("50591", (500.0, 5910.0)),
        ("40761", (400.0, 7610.0)),
        ("30970", (300.0, 9700.0)),
        ("30012", (300.0, 10120.0)),
        ("25095", (250.0, 10950.0)),
        ("20241", (200.0, 12410.0)),
        ("15418", (150.0, 14180.0)),
        ("10658", (100.0, 16580.0)),
        ("85///", (850.0, None)),
        ("//570", (None, None)),
    ],
)
def test_height_up_to_100hpa(group, expected):
    assert decode_height(group, above=False) == expected


def test_height_925_of_a_dropsonde_has_no_thousand_added():
    assert decode_height("92150", above=False, drop=True) == (925.0, 150.0)


@pytest.mark.parametrize(
    "group, expected",
    [
        ("70865", (70.0, 18650.0)),
        ("50064", (50.0, 20640.0)),
        ("50990", (50.0, 19900.0)),
        ("30380", (30.0, 23800.0)),
        ("20648", (20.0, 26480.0)),
        ("10102", (10.0, 31020.0)),
        ("10990", (10.0, 29900.0)),
        ("07350", (7.0, 33500.0)),
        ("05580", (5.0, 35800.0)),
        ("03950", (3.0, 39500.0)),
        ("02250", (2.0, 42500.0)),
        ("02990", (2.0, 39900.0)),
        ("01780", (1.0, 47800.0)),
    ],
)
def test_height_above_100hpa(group, expected):
    assert decode_height(group, above=True) == expected


def test_significant_level():
    assert decode_sig_level("00026", above=False) == (0, 1026.0)
    assert decode_sig_level("11915", above=False) == (1, 915.0)
    assert decode_sig_level("22017", above=False) == (2, 1017.0)  # under 100: 1000 hPa and more
    assert decode_sig_level("11895", above=True) == (1, 89.5)
    assert decode_sig_level("12500", above=False) == (-1, None)
    assert decode_sig_level("22///", above=False) == (-1, None)


def test_pilot_wind_heights():
    assert decode_wind_heights("90123") == [pytest.approx(h * 1000 * FT_TO_M) for h in (1, 2, 3)]
    assert decode_wind_heights("9205/") == [pytest.approx(h * 1000 * FT_TO_M) for h in (20, 25)]
    assert decode_wind_heights("11025") == [pytest.approx(h * 1000 * FT_TO_M) for h in (110, 112, 115)]
    assert decode_wind_heights("93/5/") == [None, pytest.approx(35000 * FT_TO_M)]
    assert decode_wind_heights("9////") == []
    assert decode_wind_heights("9/123") == []
    assert decode_wind_heights("70123") == []


def test_pilot_standard_pressures():
    assert decode_pilot_pressures("44385", above=False) == [850.0, 700.0, 500.0]
    assert decode_pilot_pressures("55185", above=False) == [850.0]
    assert decode_pilot_pressures("44210", above=True) == [10.0, 7.0]
    assert decode_pilot_pressures("44210", above=False) is None  # nothing after 100 hPa
    assert decode_pilot_pressures("44485", above=False) is None
    assert decode_pilot_pressures("33185", above=False) is None
    assert decode_pilot_pressures("44186", above=False) is None


def test_fields_split_a_ten_character_field():
    fields = Fields("TTAA 0022819843 08509 =")
    assert [fields.next() for _ in range(6)] == ["TTAA", "00228", "19843", "08509", "=", None]


def test_position_groups():
    assert decode_position(Fields("99235 70463 08219")) == (23.5, -46.3)
    assert decode_position(Fields("99235 50463 08219")) == (-23.5, -46.3)
    assert decode_position(Fields("99235 10463 08219")) == (23.5, 46.3)
    assert decode_position(Fields("99235 30463 08219")) == (-23.5, 46.3)
    assert decode_position(Fields("99235 20463 08219")) is None
    assert decode_position(Fields("98235 70463 08219")) is None

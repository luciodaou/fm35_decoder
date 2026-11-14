"""
Group decoders, ported from the GEMPAK RU library (gempak/source/bridge/ru).

Each function names the Fortran routine it follows. A value that cannot be decoded is None
(RMISSD in GEMPAK).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# rucmn.cmn: a field longer than MAXFLN ends a report; MAXSKP fields may be skipped in a search
MAXFLN = 15
MAXSKP = 10

# PR_KNMS is not in the extracted GEMPAK tree; the knot is 1852 m per hour
KT_TO_MS = 1852.0 / 3600.0
FT_TO_M = 0.3048

_UNPRINTABLE = re.compile(r"[^\x21-\x7e]+")


def clean_text(text: str) -> str:
    """ST_UNPR: every run of blanks and unprintable characters becomes one blank."""
    return _UNPRINTABLE.sub(" ", text).strip()


def to_int(text: str) -> Optional[int]:
    """ST_INTG: an integer, or None when the text holds anything but digits (a "/" for instance)."""
    text = text.strip()
    return int(text) if text.isascii() and text.isdigit() else None


class Fields:
    """
    RU_GFLD: the blank-separated fields of a report, read one at a time. `pos` is the pointer
    of the Fortran code and may be saved and restored; `end` limits the reading.
    """

    def __init__(self, text: str, pos: int = 0) -> None:
        self.text = text
        self.pos = pos
        self.end = len(text)
        # Start of the last field returned, and of the first 51515 that ended a section
        self.last_start = pos
        self.regional_at: Optional[int] = None

    def next(self) -> Optional[str]:
        """The next field, or None at the end. A 10-character field is returned as two of 5."""
        text, end = self.text, self.end
        i = self.pos
        while i < end and text[i] == " ":
            i += 1
        if i >= end:
            self.pos = end
            return None
        j = text.find(" ", i, end)
        if j < 0:
            j = end
        if j - i == 10:
            j = i + 5
        self.last_start = i
        self.pos = j
        return text[i:j]

    def finish(self) -> None:
        """ipoint = lenr + 1: nothing more is read."""
        self.pos = self.end

    def ends_report(self, fld: Optional[str], *prefixes: str, regional: bool = True) -> bool:
        """
        The ENDRPT statement function: no field, a field too long, 51515, or a field starting
        with one of `prefixes` (66, 77, 88, 41414).
        """
        if fld is None or len(fld) > MAXFLN:
            return True
        if regional and fld[:5] == "51515":
            if self.regional_at is None:
                self.regional_at = self.last_start
            return True
        return any(fld.startswith(p) for p in prefixes)


def decode_temp(fld: str) -> Tuple[Optional[float], Optional[float]]:
    """
    RU_TEMP: TTTDD to (temperature, dew point) in Celsius. The temperature is negative when
    its last figure is odd. A depression up to 50 is in tenths, above 50 in whole degrees + 50.
    """
    itemp = to_int(fld[0:3])
    if itemp is None:
        return None, None
    if itemp % 2 == 1:
        itemp = -itemp
    t = itemp / 10.0
    idep = to_int(fld[3:5])
    if idep is None:
        return t, None
    ddep = idep / 10.0 if idep <= 50 else float(idep - 50)
    return t, round(t - ddep, 1)


def decode_wind(fld: str, knots: bool) -> Tuple[Optional[float], Optional[float]]:
    """
    RU_WIND: ddfff to (direction in degrees, speed in m/s). 500 added to fff means a direction
    ending in 5. A direction above 360 (99 for variable) or the group 31313 gives no wind;
    360 is returned as 0.
    """
    idir = to_int(fld[0:2])
    ispd = to_int(fld[2:5])
    if idir is None or ispd is None:
        return None, None
    idir *= 10
    if ispd >= 500:
        ispd -= 500
        idir += 5
    if idir > 360 or fld[:5] == "31313":
        return None, None
    spd = ispd * KT_TO_MS if knots else float(ispd)
    return (0.0 if idir == 360 else float(idir)), spd


def decode_height(fld: str, above: bool, drop: bool = False) -> Tuple[Optional[float], Optional[float]]:
    """
    RU_HGHT: PPhhh to (pressure in hPa, geopotential height in m). Up to 100 hPa PP is in tens
    of hPa and hhh in metres below 500 hPa, decametres from 500 hPa; above 100 hPa PP is in hPa
    and hhh in decametres. The thousands (or ten thousands) are restored level by level.
    """
    ipres = to_int(fld[0:2])
    if ipres is None:
        return None, None
    if not above:
        ipres *= 10
        if ipres == 0:
            ipres = 1000
    if ipres == 920:
        ipres = 925
    iz = to_int(fld[2:5])
    if iz is None:
        return float(ipres), None

    z = float(iz)
    if not above:
        if ipres == 1000 and iz > 500:
            z = 500.0 - z
        elif ipres == 925 and iz < 200 and not drop:
            z += 1000.0
        elif ipres == 850 and iz < 900:
            z += 1000.0
        elif ipres == 700 and iz < 500:
            z += 3000.0
        elif ipres == 700:
            z += 2000.0
        elif ipres <= 500:
            iz *= 10
            z *= 10.0
            if (
                (ipres == 300 and iz < 3000)
                or (ipres == 250 and iz < 5000)
                or (ipres == 200 and iz < 7000)
                or ipres <= 150
            ):
                z += 10000.0
    else:
        iz *= 10
        z = float(iz)
        if ipres == 70:
            z += 10000.0
        elif ipres == 50 and iz >= 8000:
            z += 10000.0
        elif ipres == 50:
            z += 20000.0
        elif ipres >= 20:
            z += 20000.0
        elif ipres == 10 and iz > 8000:
            z += 20000.0
        elif ipres == 10:
            z += 30000.0
        elif ipres >= 3:
            z += 30000.0
        elif ipres == 2 and iz > 8000:
            z += 30000.0
        else:
            z += 40000.0
    return float(ipres), z


def decode_sig_level(fld: str, above: bool) -> Tuple[int, Optional[float]]:
    """
    RU_PLVL: nnPPP to (level number, pressure). nn is a figure repeated (00 the surface, 11 to
    99); the level is -1 for anything else or without a pressure. PPP is in tenths of hPa above
    100 hPa, in hPa below, where a value under 100 is 1000 hPa and more.
    """
    nn = fld[0:2]
    if len(nn) != 2 or nn[0] != nn[1] or not nn.isdigit():
        return -1, None
    ipres = to_int(fld[2:5])
    if ipres is None:
        return -1, None
    if above:
        return int(nn[0]), ipres / 10.0
    return int(nn[0]), float(ipres + 1000 if ipres < 100 else ipres)


def decode_wind_heights(fld: str) -> List[Optional[float]]:
    """
    RU_WHGT: 9tnu1u2u3 (or 8…, or 1… from 100000 ft) to the heights in metres of the winds that
    follow: tn is the tens and each u the units of thousands of feet.
    """
    if fld[:1] in ("9", "8"):
        iadd = 0
    elif fld[:1] == "1":
        iadd = 100000
    else:
        return []
    iten = to_int(fld[1:2])
    if iten is None:
        return []
    heights: List[Optional[float]] = []
    for ch in fld[2:5].ljust(3):
        iunit = to_int(ch)
        heights.append(None if iunit is None else ((iten * 10 + iunit) * 1000 + iadd) * FT_TO_M)
    count = max((k + 1 for k, h in enumerate(heights) if h is not None), default=0)
    return heights[:count]


_PILOT_BELOW = ("00", "92", "85", "70", "50", "40", "30", "25", "20", "15", "10")
_PILOT_BELOW_HPA = (1000.0, 925.0, 850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0, 150.0, 100.0)
_PILOT_ABOVE = ("70", "50", "30", "20", "10", "07", "05", "03", "02", "01")
_PILOT_ABOVE_HPA = (70.0, 50.0, 30.0, 20.0, 10.0, 7.0, 5.0, 3.0, 2.0, 1.0)


def decode_pilot_pressures(fld: str, above: bool) -> Optional[List[float]]:
    """
    RU_PPMW: 44nPP or 55nPP of PILOT Parts A and C to the n (1 to 3) consecutive standard
    levels starting at PP. None for a group that is not one.
    """
    if fld[0:2] not in ("44", "55"):
        return None
    numb = to_int(fld[2:3])
    if numb is None or not 1 <= numb <= 3:
        return None
    codes, values = (_PILOT_ABOVE, _PILOT_ABOVE_HPA) if above else (_PILOT_BELOW, _PILOT_BELOW_HPA)
    if fld[3:5] not in codes:
        return None
    first = codes.index(fld[3:5])
    if first + numb > len(values):
        return None
    return list(values[first : first + numb])


def decode_position(fields: Fields) -> Optional[Tuple[float, float]]:
    """
    RU_DROP: 99LaLaLa QcLoLoLoLo MMMULaULo of a ship or dropsonde to (latitude, longitude);
    the Marsden square group is skipped. None when the groups are not a position.
    """
    fld = fields.next()
    if fld is None or len(fld) < 5 or fld[0:2] != "99":
        return None
    ilat = to_int(fld[2:5])
    if ilat is None:
        return None
    fld = fields.next()
    if fld is None or len(fld) < 5:
        return None
    iquad, ilon = to_int(fld[0:1]), to_int(fld[1:5])
    if iquad is None or ilon is None or iquad not in (1, 3, 5, 7):
        return None
    lat, lon = ilat * 0.1, ilon * 0.1
    if iquad in (5, 7):
        lon = -lon
    if iquad in (3, 5):
        lat = -lat
    if fields.next() is None:
        return None
    return round(lat, 1), round(lon, 1)

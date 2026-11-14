"""
Decoding of the parts of TEMP and PILOT reports, ported from the GEMPAK RU library
(gempak/source/bridge/ru). Each function names the Fortran routine it follows.

Two things differ from GEMPAK on purpose, both about where a marker is recognised:

1. 21212 starts the wind section of Parts B and D only where a level group is expected.
   GEMPAK cuts the report at the first "21212" it finds, so a level at 21.2 C with a
   depression of 1.2 C turned the temperature levels after it into winds.
2. 51515 in the temperature position of a standard level is a temperature (-51.5 C with a
   depression of 1.5 C); GEMPAK ended the report there.

The shear group of a maximum wind (4vbvbvava) and the layers of missing data (nn/// /////) are
recorded in addition; GEMPAK skips both. A layer marker counts in the sequence of nn.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .bulletin import nominal_time, observation_time, parse_header
from .groups import (
    KT_TO_MS,
    MAXSKP,
    Fields,
    clean_text,
    decode_height,
    decode_pilot_pressures,
    decode_sig_level,
    decode_temp,
    decode_wind,
    decode_wind_heights,
    to_int,
)
from .models import (
    DecodeError,
    LevelType,
    MissingLayer,
    Platform,
    ReportPart,
    SoundingLevel,
    SoundingReport,
    WindUnit,
    WmoHeader,
)
from .sections import read_sections

# Standard levels of Parts A and C in the order of the code form (RU_MLVL). The last entry of
# Part C is the "xx" of the Fortran table: nothing follows 1 hPa.
_PVAL = (
    ("00", "92", "85", "70", "50", "40", "30", "25", "20", "15", "10"),
    ("70", "50", "30", "20", "10", "07", "05", "03", "02", "01", "xx"),
)
_PRES = (
    (1000.0, 925.0, 850.0, 700.0, 500.0, 400.0, 300.0, 250.0, 200.0, 150.0, 100.0),
    (70.0, 50.0, 30.0, 20.0, 10.0, 7.0, 5.0, 3.0, 2.0, 1.0, 0.0),
)

_SHEAR = re.compile(r"^4[0-9/]{4}$")
_MISSING_LAYER = re.compile(r"^(\d)\1///$")

_Mand = Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]


def _top_wind_pressure(itopwn: Optional[int], above: bool) -> float:
    """
    RU_MLVL: the lowest pressure whose level still has a wind group, from Id. Without Id no
    level has one. In Part C the figures 1 and 0 give every level a wind group.
    """
    if itopwn is None:
        return 2000.0
    if itopwn > 0:
        if above:
            return 0.0 if itopwn == 1 else itopwn * 10.0
        return itopwn * 100.0
    return 0.0 if above else 1000.0


def _surface(fields: Fields, knots: bool) -> Optional[SoundingLevel]:
    """RU_MSFC: 99PPP TTTDD ddfff, the first groups of Part A."""
    saved = fields.pos
    fld = fields.next()
    if fields.ends_report(fld, "77", "88"):
        fields.finish()
        return None
    assert fld is not None
    pres = to_int(fld[2:5]) if fld[:2] == "99" and len(fld) >= 5 else None
    if pres is None:
        fields.pos = saved
        return None
    level = SoundingLevel(LevelType.SURFACE, pressure_hpa=float(pres + 1000 if pres < 100 else pres))

    fld = fields.next()
    if fields.ends_report(fld, "77", "88"):
        fields.finish()
        return level
    assert fld is not None
    if len(fld) >= 5:
        level.temp_c, level.dewpoint_c = decode_temp(fld)

    fld = fields.next()
    if fields.ends_report(fld, "77", "88"):
        fields.finish()
        return level
    assert fld is not None
    if len(fld) >= 5:
        level.wind_dir_deg, level.wind_speed_ms = decode_wind(fld, knots)
    return level


def _mandatory(
    fld: str, fields: Fields, knots: bool, topwnd: float, above: bool, drop: bool
) -> Tuple[_Mand, int]:
    """
    RU_MAND: one standard level, PPhhh TTTDD (ddfff), as (pressure, temperature, dew point,
    direction, speed, height) and a return code: 0, -3 for an invalid group, -5 at the end of
    the report.
    """
    p, z = decode_height(fld, above, drop)
    t = td = wdir = wspd = None

    nxt = fields.next()
    # Deviation 2: 51515 is not looked for here
    if fields.ends_report(nxt, regional=False):
        return (p, t, td, wdir, wspd, z), -5
    assert nxt is not None
    if not 5 <= len(nxt) <= 7:
        return (p, t, td, wdir, wspd, z), -3
    t, td = decode_temp(nxt)

    if p is not None and p >= topwnd:
        nxt = fields.next()
        if fields.ends_report(nxt):
            return (p, t, td, wdir, wspd, z), -5
        assert nxt is not None
        if not 5 <= len(nxt) <= 7:
            return (p, t, td, wdir, wspd, z), -3
        wdir, wspd = decode_wind(nxt, knots)

    # A height of zero with everything else missing is no height
    if t is None and td is None and wdir is None and wspd is None and z is not None and round(z) % 1000 == 0:
        z = None
    return (p, t, td, wdir, wspd, z), 0


def _mandatory_levels(
    fields: Fields, knots: bool, itopwn: Optional[int], above: bool, drop: bool
) -> List[SoundingLevel]:
    """
    RU_MLVL: the standard levels of Part A or C, expected in the order of the code form. A
    group that is not the expected level starts a search for the next level that is followed,
    where its own groups end, by the level after it; the search gives up after MAXSKP fields.
    """
    pval, pres = _PVAL[above], _PRES[above]
    topwnd = _top_wind_pressure(itopwn, above)
    levels: List[SoundingLevel] = []
    skipped = 0
    level = 0

    while level <= 10:
        good = False
        saved = fields.pos
        fld = fields.next()
        if fields.ends_report(fld, "66", "77", "88"):
            # A tropopause or maximum wind group is left for the routines that read them
            if fld is not None and fld[:2] in ("66", "77", "88"):
                fields.pos = saved
            else:
                fields.finish()
            return levels
        assert fld is not None
        pp = fld[:2]

        # 925 hPa may be absent
        if pp != pval[level] and pp == "85" and level == 1:
            level += 1

        if pp == pval[level]:
            (p, t, td, wdir, wspd, z), ier = _mandatory(fld, fields, knots, topwnd, above, drop)
            good = ier == 0
            if p is not None and z is not None:
                levels.append(SoundingLevel(LevelType.MANDATORY, p, z, t, td, wdir, wspd))
                good = True
            elif p is not None and not good:
                level += 1
            if ier == -5:
                return levels

        if good:
            level += 1
            continue

        scan = True
        while scan:
            ilev = level
            while ilev <= 9 and scan:
                if pp == pval[ilev]:
                    ahead = Fields(fields.text, fields.pos)
                    nxt = None
                    for _ in range(3 if pres[ilev] >= topwnd else 2):
                        nxt = ahead.next()
                    if nxt is not None and nxt[:2] == pval[ilev + 1]:
                        level = ilev
                        scan = False
                        fields.pos = saved
                ilev += 1
            if scan:
                skipped += 1
                if skipped > MAXSKP:
                    return levels
                saved = fields.pos
                fld = fields.next()
                if fields.ends_report(fld, "66", "77", "88"):
                    fields.finish()
                    return levels
                assert fld is not None
                pp = fld[:2]
    return levels


def _tropopauses(fields: Fields, knots: bool, above: bool) -> List[SoundingLevel]:
    """
    RU_MTRP: 88PPP TTTDD ddfff, as many as there are; 88999 means none. PPP is in tenths of
    hPa above 100 hPa. A wind of 0 degrees and 0 speed is taken as missing.
    """
    levels: List[SoundingLevel] = []
    while True:
        saved = fields.pos
        fld = fields.next()
        if fields.ends_report(fld, "66", "77"):
            if fld is not None and fld[:2] in ("66", "77"):
                fields.pos = saved
            else:
                fields.finish()
            return levels
        assert fld is not None
        if fld[:2] != "88":
            continue
        if fld[2:] == "999":
            return levels
        # RU_MAND reads the group as a level below 100 hPa: its "height" is PPP
        (p, t, td, wdir, wspd, z), _ = _mandatory(fld, fields, knots, 0.0, False, False)
        if p is not None and z is not None:
            if wdir == 0.0 and wspd == 0.0:
                wdir = wspd = None
            levels.append(SoundingLevel(LevelType.TROPOPAUSE, z / 10.0 if above else z, None, t, td, wdir, wspd))


def _shear(fld: str, knots: bool) -> Tuple[Optional[float], Optional[float]]:
    below, over = to_int(fld[1:3]), to_int(fld[3:5])
    factor = KT_TO_MS if knots else 1.0
    return (None if below is None else below * factor, None if over is None else over * factor)


def _max_winds(fields: Fields, knots: bool, above: bool) -> List[SoundingLevel]:
    """
    RU_MMXW: 77PPP (or 66PPP) ddfff, as many as there are. 77999 ends the search; a level
    without a wind is dropped. The shear group 4vbvbvava after the wind is read in addition.
    """
    levels: List[SoundingLevel] = []
    while True:
        fld = fields.next()
        if fields.ends_report(fld):
            fields.finish()
            return levels
        assert fld is not None
        pp = fld[:2]
        if pp not in ("77", "66"):
            continue
        if fld[2:] == "999":
            if pp == "77":
                return levels
            continue
        if not fld[2:].replace(".", "", 1).isdigit():
            continue
        pres = float(fld[2:])
        wind = fields.next()
        wdir, wspd = decode_wind(wind, knots) if wind is not None and len(wind) >= 5 else (None, None)
        if wdir is None and wspd is None:
            continue
        level = SoundingLevel(
            LevelType.MAX_WIND, pres / 10.0 if above else pres, wind_dir_deg=wdir, wind_speed_ms=wspd
        )
        saved = fields.pos
        nxt = fields.next()
        if nxt is not None and _SHEAR.match(nxt):
            level.shear_below_ms, level.shear_above_ms = _shear(nxt, knots)
        else:
            fields.pos = saved
        levels.append(level)


def _significant(
    fields: Fields,
    above: bool,
    knots: bool,
    wind: bool,
    layers: List[MissingLayer],
) -> Tuple[List[SoundingLevel], bool]:
    """
    RU_STMP (wind False: nnPPP TTTDD) and RU_PWND (wind True: nnPPP ddfff). nn is expected in
    sequence (00 at the surface up to 100 hPa, then 11 to 99 and again from 11). A level out of
    sequence is taken if its pressure is lower than the last one, and dropped again if the
    level after it does not follow it. A level without a temperature (or wind) is not kept.
    Returns the levels and whether the temperature levels ended at 21212.
    """
    kind = LevelType.SIG_WIND if wind else LevelType.SIG_TEMP
    # rows[0 : nlev] is DATA (3, NLEV) of the Fortran code; below 100 hPa the first row is the
    # surface, missing until it is reported
    rows: List[Optional[Tuple[float, Optional[float], Optional[float]]]] = [] if above else [None]
    nlev = 0
    levexp = 1 if above else 0
    skip = False
    open_layer: Optional[float] = None
    found_wind_section = False

    def last_pressure() -> float:
        row = rows[nlev - 1]
        return row[0] if row is not None else -9999.0

    while True:
        fld = fields.next()
        if fields.ends_report(fld, "41414"):
            break
        assert fld is not None
        if not wind and fld[:5] == "21212":
            found_wind_section = True
            break
        if len(fld) < 5:
            continue

        # Addition: nn/// ///// is a layer of missing data. It takes its place in the sequence
        # of nn, so that the level closing the layer is not taken for one out of sequence.
        marker = _MISSING_LAYER.match(fld)
        if marker:
            if nlev > 0 and rows[nlev - 1] is not None:
                open_layer = last_pressure()
            if int(marker.group(1)) == levexp:
                levexp = 1 if levexp >= 9 else levexp + 1
            saved = fields.pos
            if fields.next() != "/////":
                fields.pos = saved
            continue

        level, pres = decode_sig_level(fld, above)
        if level == levexp:
            get = True
            skip = False
        elif level <= 0:
            get = False
            if skip:
                nlev -= 1
            skip = False
            levexp = -2
        elif nlev == 0 or (pres is not None and pres < last_pressure()):
            get = True
            if skip:
                nlev -= 1
            skip = True
            levexp = level
        else:
            get = False
            if skip:
                nlev -= 1
            skip = False
            levexp = -2

        if get:
            assert pres is not None
            value = fields.next()
            if wind and fields.ends_report(value, "41414"):
                break
            if value is not None and len(value) >= 5:
                a, b = decode_wind(value, knots) if wind else decode_temp(value)
                if a is None or (wind and b is None):
                    skip = False
                else:
                    nlev += 1
                    if nlev == 1 and level != 0 and not above:
                        nlev = 2
                    del rows[nlev - 1 :]
                    rows.append((pres, a, b))
                    if open_layer is not None:
                        if pres < open_layer:
                            layers.append(MissingLayer(kind, open_layer, pres))
                        open_layer = None
            levexp += 1
            if levexp > 9:
                levexp = 1
            if value is None:
                break

        if nlev == 0:
            skip = False

    levels = []
    for row in rows[:nlev]:
        if row is None:
            continue
        pres, a, b = row
        if wind:
            levels.append(SoundingLevel(kind, pres, wind_dir_deg=a, wind_speed_ms=b))
        else:
            levels.append(SoundingLevel(kind, pres, temp_c=a, dewpoint_c=b))
    return levels, found_wind_section


def _height_winds(fields: Fields, knots: bool) -> List[SoundingLevel]:
    """RU_SIGW: 9tnu1u2u3 ddfff ddfff ddfff of PILOT Parts B and D, winds on heights."""
    levels: List[SoundingLevel] = []
    while True:
        fld = fields.next()
        if fields.ends_report(fld, "41414"):
            return levels
        assert fld is not None
        if len(fld) < 5:
            continue
        for height in decode_wind_heights(fld):
            wind = fields.next()
            if fields.ends_report(wind, "41414"):
                return levels
            assert wind is not None
            if len(wind) < 5:
                continue
            wdir, wspd = decode_wind(wind, knots)
            if wdir is not None and wspd is not None and height is not None:
                levels.append(
                    SoundingLevel(LevelType.SIG_WIND, height_m=round(height, 1), wind_dir_deg=wdir, wind_speed_ms=wspd)
                )


def _pilot_mandatory(fields: Fields, knots: bool, above: bool) -> List[SoundingLevel]:
    """RU_PPAA and RU_PPCC: 44nPP (or 55nPP) followed by n winds, at decreasing pressures."""
    levels: List[SoundingLevel] = []
    pold = 100.0 if above else 2000.0
    while True:
        fld = fields.next()
        if fields.ends_report(fld) or fld is None or len(fld) != 5:
            return levels
        pressures = decode_pilot_pressures(fld, above)
        if pressures is None:
            return levels
        for pres in pressures:
            wind = fields.next()
            if fields.ends_report(wind):
                return levels
            assert wind is not None
            if len(wind) < 5:
                continue
            wdir, wspd = decode_wind(wind, knots)
            if wdir is not None and wspd is not None and pres < pold:
                levels.append(SoundingLevel(LevelType.MANDATORY, pres, wind_dir_deg=wdir, wind_speed_ms=wspd))
                pold = pres


def _dropsonde_id(text: str, hour: int) -> Optional[str]:
    """
    RU_DRP1: the identifier of a dropsonde from the aircraft group after 61616 and the
    observation number after "OB" (99 without one). None when the aircraft is not recognised.
    """
    at = text.find("61616")
    if at < 0:
        return None
    fields = Fields(text, at + 5)
    fld = fields.next()
    if fld is None or len(fld) != 5:
        return None
    if fld[:4] in ("NOAA", "NASA"):
        digits = fld[4:5]
    elif fld[:2] in ("AF", "NA"):
        digits = fld[2:5]
    elif fld[0] == "N" and fld[4] == "F":
        digits = fld[1:4]
    else:
        return None
    ident = to_int(digits)
    if ident is None:
        return None
    number = hour * 1000 + ident
    observation = None
    ob = text.find("OB", fields.pos)
    if ob >= 0:
        fields.pos = ob + 2
        fld = fields.next()
        if fld is not None and len(fld) in (1, 2):
            observation = to_int(fld)
    if observation is None or observation <= 0:
        observation = 99
    return str(observation * 100000 + number)


def _split_at_21212(fields: Fields) -> Optional[int]:
    """Limit `fields` to the groups before the first 21212 and return the position after it."""
    probe = Fields(fields.text, fields.pos)
    while True:
        fld = probe.next()
        if fld is None:
            return None
        if fld[:5] == "21212":
            fields.end = probe.last_start
            return probe.last_start + 5


def parse_report(
    text: str,
    header: Optional[WmoHeader] = None,
    reference_time: Optional[datetime] = None,
) -> SoundingReport:
    """
    RU_SHDR and RU_DECD: decodes one report, from its part name up to (not including) "=".
    `reference_time` is the time the report was received, which gives the year and the month
    of the observation (now, when not given). A NIL report comes back with `nil` set and no
    levels. Raises DecodeError when the header cannot be decoded.
    """
    text = clean_text(text).rstrip("= ")
    fields = Fields(text)
    report = parse_header(text, fields)
    report.header = header

    reference = reference_time or datetime.now(timezone.utc)
    report.obs_time = observation_time(reference, report.obs_day, report.obs_hour)
    if report.obs_time is not None:
        report.nominal_time = nominal_time(report.obs_time)
    if report.nil:
        return report

    knots = report.wind_unit is WindUnit.KNOTS
    part = report.part
    above = part.above_100hpa
    drop = report.platform is Platform.DROPSONDE
    levels: List[SoundingLevel] = []

    if part in (ReportPart.TTAA, ReportPart.TTCC):
        if part is ReportPart.TTAA:
            surface = _surface(fields, knots)
            if surface is not None:
                levels.append(surface)
        levels += _mandatory_levels(fields, knots, report.top_wind_indicator, above, drop)
        levels += _tropopauses(fields, knots, above)
        levels += _max_winds(fields, knots, above)
    elif part in (ReportPart.TTBB, ReportPart.TTDD):
        temps, wind_section = _significant(fields, above, knots, False, report.missing_layers)
        levels += temps
        if wind_section:
            winds, _ = _significant(fields, above, knots, True, report.missing_layers)
            levels += winds
    elif part in (ReportPart.PPAA, ReportPart.PPCC):
        levels += _pilot_mandatory(fields, knots, above)
    else:
        after = _split_at_21212(fields)
        levels += _height_winds(fields, knots)
        if after is not None:
            fields.end = len(text)
            fields.pos = after
            winds, _ = _significant(fields, above, knots, True, report.missing_layers)
            levels += winds

    if drop and part in (ReportPart.TTAA, ReportPart.TTBB):
        ident = _dropsonde_id(text, report.obs_hour)
        if ident is None:
            raise DecodeError(f"dropsonde without an identifier in section 61616: {text[:40]!r}")
        report.station_id = ident

    report.levels = levels
    read_sections(report, fields.regional_at)
    return report

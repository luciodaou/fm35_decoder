"""
Bulletins, reports and report headers, ported from GEMPAK: DC_GBUL and DC_GHDR (bridge/dc),
RU_GRPT, RU_SHDR, RU_RTIM and RU_ADJT (bridge/ru).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator, List, Optional, Tuple, Union

from .groups import Fields, clean_text, decode_position, to_int
from .models import DecodeError, Platform, ReportPart, SoundingReport, WindUnit, WmoHeader

SOH, ETX = "\x01", "\x03"

# TTAAii CCCC YYGGgg (BBB); DC_GHDR also takes MMDDHHMM, DDHHMMZ and "UTC" before BBB
_HEADING = re.compile(r"^([A-Z]{4}\d{0,2}) ([A-Z]{4}) (\d{6}Z?|\d{8})(?: UTC)?(?: ([A-Z]{3}))?$")
_PART_NAME = re.compile(r"^(TT|PP|UU|XX)(AA|BB|CC|DD)")
_SEQUENCE = re.compile(r"^\d{3,5}$")


@dataclass(frozen=True)
class Bulletin:
    header: Optional[WmoHeader]
    text: str


def _parse_heading(line: str, sequence: str) -> Optional[WmoHeader]:
    """DC_GHDR: the heading line, with a valid day (01-31) and time (0000-2359)."""
    m = _HEADING.match(line)
    if m is None or _PART_NAME.match(line):
        return None
    time = m.group(3)
    time = time[2:] if len(time) == 8 else time[:6]
    if not (1 <= int(time[:2]) <= 31 and int(time[2:]) <= 2359):
        return None
    return WmoHeader(m.group(1), m.group(2), time, m.group(4) or "", sequence)


def iter_bulletins(source: Union[str, Iterable[str]]) -> Iterator[Bulletin]:
    """
    The bulletins of a text, a file object or any iterable of lines, one at a time. A bulletin
    starts at SOH or at a WMO abbreviated heading and ends at ETX, at the next start or at the
    end of the input. Text without any of those is one bulletin without a header.
    """
    lines = source.splitlines() if isinstance(source, str) else source
    header: Optional[WmoHeader] = None
    sequence = ""
    body: List[str] = []

    def flush() -> Iterator[Bulletin]:
        nonlocal header, sequence, body
        text = clean_text(" ".join(body))
        if text:
            yield Bulletin(header, text)
        header, sequence, body = None, "", []

    for raw in lines:
        for piece in re.split(f"({SOH}|{ETX})", raw):
            if piece in (SOH, ETX):
                yield from flush()
                continue
            line = clean_text(piece)
            if not line:
                continue
            if header is None and not body and _SEQUENCE.match(line):
                sequence = line
                continue
            heading = _parse_heading(line, sequence)
            if heading is not None:
                kept = sequence
                yield from flush()
                header = WmoHeader(heading.ttaaii, heading.cccc, heading.yygggg, heading.bbb, kept)
                continue
            body.append(line)
    yield from flush()


_REPORT_START = re.compile(r"TT|PP|UU|XX")
_REPORT_END = re.compile(r"TT|PP|UU|XX|=")
# A dropsonde report may hold text, so only another dropsonde report or "=" ends it
_REPORT_END_XX = re.compile(r"XXAA|XXBB|XXCC|XXDD|=")


def iter_reports(text: str) -> Iterator[str]:
    """
    RU_GRPT: the reports of a bulletin. A report starts at TT, PP, UU or XX followed by AA, BB,
    CC or DD and runs up to "=", the start of another report or the end of the bulletin.
    """
    text = clean_text(text)
    pos, end = 0, len(text)
    while pos < end:
        search = pos
        while True:
            m = _REPORT_START.search(text, search)
            if m is None:
                return
            start = m.start()
            if text[start + 2 : start + 4] in ("AA", "BB", "CC", "DD"):
                break
            search = start + 1
        pattern = _REPORT_END_XX if m.group() == "XX" else _REPORT_END
        stop = pattern.search(text, start + 2)
        if stop is None:
            yield text[start:]
            return
        yield text[start : stop.start()]
        pos = stop.start() + (1 if stop.group() == "=" else 0)


def parse_header(text: str, fields: Fields) -> SoundingReport:
    """
    RU_SHDR: MiMiMjMj (call sign) YYGGId IIiii, or the position groups of a ship or dropsonde.
    `fields` is left on the first group after the header. XX and UU parts are decoded as TT.
    Raises DecodeError when the header is not one.
    """
    name = text[fields.pos : fields.pos + 4]
    fields.pos += 4
    p1, p2 = name[:2], name[2:]
    if p1 in ("TT", "PP") and p2 in ("AA", "BB", "CC", "DD"):
        platform = Platform.LAND
    elif p1 == "XX" and p2 in ("AA", "BB"):
        platform = Platform.DROPSONDE
    elif p1 == "UU" and p2 in ("AA", "BB", "CC", "DD"):
        platform = Platform.SHIP
    else:
        raise DecodeError(f"not an upper-air part: {name!r}")
    part = ReportPart(name if platform is Platform.LAND else "TT" + p2)

    call_sign = ""
    if platform is Platform.SHIP:
        call_sign = fields.next() or ""
        if not call_sign or len(call_sign) > 8:
            raise DecodeError(f"invalid call sign in {text[:24]!r}")

    fld = fields.next()
    if fld is None or len(fld) < 5:
        raise DecodeError(f"no YYGGId group in {text[:24]!r}")
    day, hour = to_int(fld[0:2]), to_int(fld[2:4])
    if day is None or hour is None:
        raise DecodeError(f"invalid YYGGId group {fld!r}")
    unit = WindUnit.METERS_PER_SECOND
    if day > 50:
        day -= 50
        unit = WindUnit.KNOTS
    report = SoundingReport(
        part=part,
        station_id="",
        obs_day=day,
        obs_hour=hour,
        wind_unit=unit,
        platform=platform,
        top_wind_indicator=to_int(fld[4:5]),
        text=text,
    )

    if platform is Platform.LAND:
        fld = fields.next()
        number = to_int(fld[0:5]) if fld is not None and len(fld) >= 5 else None
        if number is None:
            raise DecodeError(f"invalid station number in {text[:24]!r}")
        report.station_id = f"{number:05d}"
    else:
        position = decode_position(fields)
        if position is None:
            raise DecodeError(f"invalid position groups in {text[:40]!r}")
        report.latitude, report.longitude = position
        if platform is Platform.DROPSONDE:
            # The identifier comes from the 61616 section; until then it is the hour
            report.station_id = str(hour)
        elif call_sign == "SHIP":
            lat, lon = position
            report.station_id = f"S{int(abs(lat * 10)) * 10000 + int(abs(lon * 10)):07d}"
        else:
            report.station_id = f"{call_sign[:6]}{hour:02d}"

    rest = text[fields.pos :].lstrip()
    report.nil = rest[:3] == "NIL" and rest[3:].strip(" =") == ""
    return report


def observation_time(reference: datetime, day: int, hour: int) -> Optional[datetime]:
    """
    RU_RTIM: the observation time from the day and hour of the report, taking the year and the
    month from `reference` (the time the report was received). A day after the 27th received
    on the 1st belongs to the month before; hour 24 is 00 of the next day. None when the hour
    or the date is not valid.
    """
    add_day = hour == 24
    if add_day:
        hour = 0
    elif not 0 <= hour < 24:
        return None
    year, month = reference.year, reference.month
    if day > 27 and reference.day == 1:
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    try:
        obs = datetime(year, month, day, hour, tzinfo=timezone.utc)
    except ValueError:
        return None
    return obs + timedelta(days=1) if add_day else obs


def nominal_time(obs: datetime) -> datetime:
    """RU_ADJT: the time rounded to the nearest 3 hours."""
    diff = obs.hour % 3
    if diff == 1:
        return obs - timedelta(hours=1)
    if diff == 2:
        return obs + timedelta(hours=1)
    return obs


def station_key(report: SoundingReport) -> Tuple[str, Optional[datetime], int, int]:
    """What the parts of one sounding share: station and nominal time (day and hour without one)."""
    if report.nominal_time is not None:
        return report.station_id, report.nominal_time, 0, 0
    hour = report.obs_hour
    hour += {0: 0, 1: -1, 2: 1}[hour % 3]
    return report.station_id, None, report.obs_day, hour

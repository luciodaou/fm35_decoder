"""
Merging the parts of a sounding into one profile.

The GEMPAK decoder stores the parts unmerged; the merge of its MR library is not part of the
extracted sources. This module follows the WMO Manual on Codes and the method of version 1:
levels are combined by pressure, heights are computed with the hypsometric equation, and
values may be interpolated between observed levels on request. Everything computed here is
named in `SoundingLevel.derived`.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .bulletin import station_key
from .models import (
    LevelType,
    MergedSounding,
    MissingLayer,
    ReportPart,
    SoundingLevel,
    SoundingReport,
    StationMetadata,
)

R_DRY = 287.05  # J/(kg K)
G0 = 9.80665  # m/s2

_PART_ORDER = list(ReportPart)


def select_reports(reports: Iterable[SoundingReport]) -> List[SoundingReport]:
    """
    One report per part, as RU_DUPE and DCUDCD do: the first one received is kept, unless a
    later one comes from a correction, retransmission or amendment (BBB starting with C, R, A).
    NIL reports are left out.
    """
    chosen: Dict[ReportPart, SoundingReport] = {}
    for report in reports:
        if report.nil:
            continue
        if report.part not in chosen or (report.header is not None and report.header.is_correction):
            chosen[report.part] = report
    return [chosen[part] for part in _PART_ORDER if part in chosen]


def _fill(row: SoundingLevel, level: SoundingLevel) -> None:
    """Values `row` does not have are taken from `level`; a wind is taken whole."""
    for name in ("height_m", "temp_c", "dewpoint_c"):
        if getattr(row, name) is None:
            setattr(row, name, getattr(level, name))
    if row.wind_dir_deg is None and row.wind_speed_ms is None:
        row.wind_dir_deg, row.wind_speed_ms = level.wind_dir_deg, level.wind_speed_ms


def _interp(x: float, xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Linear interpolation at x between the points (xs, ys), xs increasing; None outside them."""
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    for k in range(1, len(xs)):
        if x <= xs[k]:
            span = xs[k] - xs[k - 1]
            if span == 0:
                return ys[k]
            return ys[k - 1] + (ys[k] - ys[k - 1]) * (x - xs[k - 1]) / span
    return ys[-1]


def _p(level: SoundingLevel) -> float:
    """The pressure of a level of the profile, which always has one."""
    assert level.pressure_hpa is not None
    return level.pressure_hpa


def _mark(level: SoundingLevel, *names: str) -> None:
    level.derived = tuple(dict.fromkeys(level.derived + names))


def _virtual_temperature(temp_c: float, dewpoint_c: Optional[float], pressure: float) -> float:
    """Tv = T (1 + 0.608 w), with the vapour pressure from the dew point (Bolton)."""
    temp_k = temp_c + 273.15
    if dewpoint_c is None:
        return temp_k
    e = 6.112 * math.exp(17.67 * dewpoint_c / (dewpoint_c + 243.5))
    w = 0.622 * e / (pressure - e) if pressure > e else 0.0
    return temp_k * (1.0 + 0.608 * w)


def compute_heights(profile: List[SoundingLevel]) -> None:
    """
    Heights of the levels that report none, from the nearest level that has one, with the
    hypsometric equation and the virtual temperature. A level without a temperature takes one
    for this calculation only (interpolated in ln p, as is a missing dew point; the last
    temperature above the top one).
    Above the last temperature a height is computed only within the limits of Regulation
    35.2.2.4: 25 hPa, and a quarter of the pressure of the level.
    """
    observed = [(-math.log(_p(lv)), lv.temp_c) for lv in profile if lv.temp_c is not None]
    if not observed:
        return
    xs, ts = [x for x, _ in observed], [t for _, t in observed]
    p_top = min(_p(lv) for lv in profile if lv.temp_c is not None)

    moist = [(-math.log(_p(lv)), lv.dewpoint_c) for lv in profile if lv.dewpoint_c is not None]
    dxs, dds = [x for x, _ in moist], [d for _, d in moist]

    tv: List[float] = []
    for lv in profile:
        x = -math.log(_p(lv))
        temp = lv.temp_c
        if temp is None:
            temp = _interp(x, xs, ts)
            if temp is None:
                temp = ts[0] if x < xs[0] else ts[-1]
        dew = lv.dewpoint_c if lv.dewpoint_c is not None else _interp(x, dxs, dds)
        tv.append(_virtual_temperature(temp, None if dew is None else min(dew, temp), _p(lv)))

    def thickness(low: int, high: int) -> float:
        mean_tv = (tv[low] + tv[high]) / 2.0
        return R_DRY * mean_tv / G0 * math.log(_p(profile[low]) / _p(profile[high]))

    for i in range(1, len(profile)):
        below, level = profile[i - 1], profile[i]
        if level.height_m is not None or below.height_m is None:
            continue
        beyond = p_top - _p(level)
        if beyond > 25.0 or beyond > 0.25 * _p(level):
            continue
        level.height_m = float(round(below.height_m + thickness(i - 1, i)))
        _mark(level, "height_m")

    first = next((i for i, lv in enumerate(profile) if lv.height_m is not None), 0)
    for i in range(first - 1, -1, -1):
        above = profile[i + 1].height_m
        assert above is not None
        profile[i].height_m = float(round(above - thickness(i, i + 1)))
        _mark(profile[i], "height_m")


def _inside(pressure: float, layers: Sequence[MissingLayer], kind: LevelType) -> bool:
    return any(lay.kind is kind and lay.bottom_hpa > pressure > lay.top_hpa for lay in layers)


def interpolate_profile(profile: List[SoundingLevel], layers: Sequence[MissingLayer] = ()) -> None:
    """
    Fills temperature, dew point and wind at the levels that report none, linearly in ln p
    between the observed levels around them (the wind by its components). Nothing is filled
    outside the observed levels or inside a layer reported as missing; a dew point is filled
    only where the temperature is, and never above it.
    """
    xs = [-math.log(_p(lv)) for lv in profile]

    def series(value: Callable[[SoundingLevel], Optional[float]]) -> Tuple[List[float], List[float]]:
        points = [(x, value(lv)) for x, lv in zip(xs, profile)]
        return [x for x, v in points if v is not None], [v for _, v in points if v is not None]

    tx, tt = series(lambda lv: lv.temp_c)
    dx, dd = series(lambda lv: lv.dewpoint_c)

    def u_of(lv: SoundingLevel) -> Optional[float]:
        if lv.wind_dir_deg is None or lv.wind_speed_ms is None:
            return None
        return -lv.wind_speed_ms * math.sin(math.radians(lv.wind_dir_deg))

    def v_of(lv: SoundingLevel) -> Optional[float]:
        if lv.wind_dir_deg is None or lv.wind_speed_ms is None:
            return None
        return -lv.wind_speed_ms * math.cos(math.radians(lv.wind_dir_deg))

    ux, uu = series(u_of)
    _, vv = series(v_of)

    for x, lv in zip(xs, profile):
        if lv.temp_c is None and not _inside(_p(lv), layers, LevelType.SIG_TEMP):
            temp = _interp(x, tx, tt)
            if temp is not None:
                lv.temp_c = round(temp, 1)
                _mark(lv, "temp_c")
                dew = _interp(x, dx, dd)
                if dew is not None:
                    lv.dewpoint_c = min(round(dew, 1), lv.temp_c)
                    _mark(lv, "dewpoint_c")
        if lv.wind_speed_ms is None and not _inside(_p(lv), layers, LevelType.SIG_WIND):
            u, v = _interp(x, ux, uu), _interp(x, ux, vv)
            if u is not None and v is not None:
                speed = math.hypot(u, v)
                lv.wind_speed_ms = round(speed, 1)
                lv.wind_dir_deg = round(math.degrees(math.atan2(-u, -v))) % 360 if speed > 0.05 else 0.0
                lv.wind_dir_deg = float(lv.wind_dir_deg)
                _mark(lv, "wind_dir_deg", "wind_speed_ms")


def _place_height_winds(profile: List[SoundingLevel], winds: List[SoundingLevel]) -> List[SoundingLevel]:
    """
    PILOT winds on heights get a pressure from the heights of the profile (ln p linear in
    height) and join it. Those outside the heights of the profile are returned.
    """
    known = [(lv.height_m, math.log(_p(lv))) for lv in profile if lv.height_m is not None]
    known.sort()
    zs, lnps = [z for z, _ in known], [lp for _, lp in known]
    left: List[SoundingLevel] = []
    by_pressure = {_p(lv): lv for lv in profile}
    for wind in winds:
        lnp = _interp(wind.height_m, zs, lnps) if len(zs) > 1 and wind.height_m is not None else None
        if lnp is None:
            left.append(wind)
            continue
        pressure = round(math.exp(lnp), 1)
        row = by_pressure.get(pressure)
        if row is None:
            row = replace(wind, pressure_hpa=pressure, derived=("pressure_hpa",))
            by_pressure[pressure] = row
            profile.append(row)
        else:
            _fill(row, wind)
    profile.sort(key=lambda lv: -_p(lv))
    return left


def merge_parts(
    reports: Iterable[SoundingReport],
    station_meta: Optional[StationMetadata] = None,
    interpolate: bool = False,
) -> MergedSounding:
    """
    Merges the parts of one sounding. Levels are combined by pressure (to the tenth of hPa):
    standard levels first, then significant temperature levels, significant winds, PILOT
    winds, and the tropopause and maximum wind levels; a value already there is never
    replaced. The profile runs from the highest pressure to the lowest, and levels below the
    surface (a 1000 hPa height under a station at 950 hPa) are kept as reported.
    """
    chosen = select_reports(reports)
    first = chosen[0] if chosen else None
    sounding = MergedSounding(
        station_id=first.station_id if first else "",
        timestamp_utc=first.nominal_time if first else None,
        station_meta=station_meta,
        reports=chosen,
    )

    def levels(parts: Tuple[str, ...], *types: LevelType) -> List[SoundingLevel]:
        return [lv for r in chosen if r.part.value in parts for lv in r.of_type(*types)]

    temp_parts = ("TTAA", "TTCC", "TTBB", "TTDD")
    ordered = (
        levels(("TTAA", "TTCC"), LevelType.SURFACE, LevelType.MANDATORY)
        + levels(temp_parts, LevelType.SIG_TEMP)
        + [lv for r in chosen for lv in r.of_type(LevelType.SIG_WIND) if lv.pressure_hpa is not None]
        + levels(("PPAA", "PPCC"), LevelType.MANDATORY)
    )
    sounding.tropopauses = levels(temp_parts, LevelType.TROPOPAUSE)
    sounding.max_winds = levels(temp_parts, LevelType.MAX_WIND)
    sounding.missing_layers = [layer for r in chosen for layer in r.missing_layers]

    rows: Dict[float, SoundingLevel] = {}
    for level in ordered + sounding.tropopauses + sounding.max_winds:
        if level.pressure_hpa is None or level.pressure_hpa <= 0:
            continue
        key = round(level.pressure_hpa, 1)
        if key in rows:
            _fill(rows[key], level)
        else:
            rows[key] = replace(level, pressure_hpa=key, shear_below_ms=None, shear_above_ms=None)
    profile = sorted(rows.values(), key=lambda lv: -_p(lv))

    if station_meta is not None:
        for level in profile:
            if level.level_type is LevelType.SURFACE and level.height_m is None:
                level.height_m = float(station_meta.elevation_m)
                _mark(level, "height_m")

    compute_heights(profile)
    height_winds = [lv for r in chosen for lv in r.of_type(LevelType.SIG_WIND) if lv.pressure_hpa is None]
    sounding.height_winds = _place_height_winds(profile, height_winds)
    if interpolate:
        interpolate_profile(profile, sounding.missing_layers)
    sounding.profile = profile
    return sounding


def merge_reports(
    reports: Iterable[SoundingReport],
    station_table: Optional[Dict[str, StationMetadata]] = None,
    interpolate: bool = False,
) -> List[MergedSounding]:
    """
    Groups reports by station and nominal time (the observation time rounded to 3 hours) and
    merges each group, in the order the soundings first appear.
    """
    groups: Dict[tuple, List[SoundingReport]] = {}
    for report in reports:
        groups.setdefault(station_key(report), []).append(report)
    soundings = []
    for group in groups.values():
        if all(r.nil for r in group):
            continue
        meta = station_table.get(group[0].station_id) if station_table is not None else None
        soundings.append(merge_parts(group, meta, interpolate))
    return soundings

"""Loader for GEMPAK station tables (gempak/tables/stns/snstns.tbl)."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Union

from .models import StationMetadata


def parse_station_line(line: str) -> Optional[StationMetadata]:
    """
    One line of a GEMPAK station table, in the fixed columns of TB_RSTN:
    STID (1-8), STNM (10-15), NAME (17-48), STATE (50-51), COUNTRY (53-54), LAT*100 (56-60),
    LON*100 (62-67), ELEV in metres (69-73). None for a comment, a blank or a malformed line.
    """
    if not line.strip() or line.startswith("!"):
        return None
    try:
        return StationMetadata(
            stid=line[0:8].strip(),
            stnm=int(line[9:15]),
            name=line[16:48].strip(),
            state=line[49:51].strip(),
            country=line[52:54].strip(),
            latitude=int(line[55:60]) / 100.0,
            longitude=int(line[61:67]) / 100.0,
            elevation_m=float(int(line[68:73])),
        )
    except ValueError:
        return None


def load_station_table(source: Union[str, Iterable[str]]) -> Dict[str, StationMetadata]:
    """
    Reads a station table from a path or from its lines, keyed by the five-figure station
    number ("83746"). Stations without a number (ships, keyed 0 in the table) are keyed by
    their identifier.
    """
    if isinstance(source, str):
        with open(source, encoding="latin-1") as handle:
            return load_station_table(handle.readlines())
    table: Dict[str, StationMetadata] = {}
    for line in source:
        station = parse_station_line(line.rstrip("\r\n"))
        if station is not None:
            key = f"{station.stnm:05d}" if station.stnm > 0 else station.stid
            table.setdefault(key, station)
    return table

"""Data model of the decoder: parts, levels, reports and merged soundings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple


class DecodeError(ValueError):
    """A report whose header cannot be decoded (GEMPAK return code -3 or -4)."""


class ReportPart(str, Enum):
    TTAA = "TTAA"
    TTBB = "TTBB"
    TTCC = "TTCC"
    TTDD = "TTDD"
    PPAA = "PPAA"
    PPBB = "PPBB"
    PPCC = "PPCC"
    PPDD = "PPDD"

    @property
    def above_100hpa(self) -> bool:
        """Parts C and D hold the levels above 100 hPa."""
        return self.value[2:] in ("CC", "DD")

    @property
    def is_pilot(self) -> bool:
        return self.value.startswith("PP")


class WindUnit(Enum):
    """Unit of the wind speeds as reported (YY > 50 means knots)."""

    KNOTS = "kt"
    METERS_PER_SECOND = "m/s"


class Platform(Enum):
    """What made the report: MiMi of TT/PP (land), UU (ship) or XX (dropsonde)."""

    LAND = "land"
    SHIP = "ship"
    DROPSONDE = "dropsonde"


class LevelType(Enum):
    SURFACE = "Surface"
    MANDATORY = "Standard"
    SIG_TEMP = "SigTemp"
    SIG_WIND = "SigWind"
    TROPOPAUSE = "Tropopause"
    MAX_WIND = "MaxWind"


@dataclass
class SoundingLevel:
    """
    One level. A value the report does not give is None. Wind speeds are in m/s whatever the
    unit of the report. `derived` names the fields that were computed or interpolated by the
    merge instead of reported.
    """

    level_type: LevelType
    pressure_hpa: Optional[float] = None
    height_m: Optional[float] = None
    temp_c: Optional[float] = None
    dewpoint_c: Optional[float] = None
    wind_dir_deg: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    # Vertical wind shear 1 km below and above a maximum wind (4vbvbvava), in m/s
    shear_below_ms: Optional[float] = None
    shear_above_ms: Optional[float] = None
    derived: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WmoHeader:
    """WMO abbreviated heading: TTAAii CCCC YYGGgg (BBB)."""

    ttaaii: str
    cccc: str
    yygggg: str
    bbb: str = ""
    sequence: str = ""

    @property
    def is_correction(self) -> bool:
        """BBB of a correction, retransmission or amendment: such a report replaces an earlier one."""
        return self.bbb[:1] in ("C", "R", "A")


@dataclass(frozen=True)
class MissingLayer:
    """A layer reported as missing in Part B or D (nn/// /////), between its boundary levels."""

    kind: LevelType
    bottom_hpa: float
    top_hpa: float


@dataclass(frozen=True)
class SoundingSystem:
    """Section 7 (31313): sr rara sasa 8GGgg, as code figures."""

    radiation_correction: Optional[str] = None
    radiosonde: Optional[str] = None
    tracking: Optional[str] = None
    launch_time: Optional[str] = None


@dataclass
class SoundingReport:
    """One part of a sounding from one station."""

    part: ReportPart
    station_id: str
    obs_day: int
    obs_hour: int
    wind_unit: WindUnit
    levels: List[SoundingLevel] = field(default_factory=list)
    header: Optional[WmoHeader] = None
    platform: Platform = Platform.LAND
    # Id of YYGGId as a figure, None for "/"
    top_wind_indicator: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    nil: bool = False
    # Observation time, and the same rounded to 3 hours (the key the parts are merged on)
    obs_time: Optional[datetime] = None
    nominal_time: Optional[datetime] = None
    missing_layers: List[MissingLayer] = field(default_factory=list)
    sounding_system: Optional[SoundingSystem] = None
    cloud_group: Optional[str] = None
    # Sections 31313, 41414 and 51515 onwards, as text
    raw_remarks: List[str] = field(default_factory=list)
    text: str = ""

    def of_type(self, *types: LevelType) -> List[SoundingLevel]:
        return [lv for lv in self.levels if lv.level_type in types]


@dataclass(frozen=True)
class StationMetadata:
    stid: str
    stnm: int
    name: str
    state: str
    country: str
    latitude: float
    longitude: float
    elevation_m: float


@dataclass
class MergedSounding:
    """The parts of one sounding merged into a profile, surface first."""

    station_id: str
    timestamp_utc: Optional[datetime]
    profile: List[SoundingLevel] = field(default_factory=list)
    tropopauses: List[SoundingLevel] = field(default_factory=list)
    max_winds: List[SoundingLevel] = field(default_factory=list)
    # PILOT winds on heights that could not be given a pressure
    height_winds: List[SoundingLevel] = field(default_factory=list)
    missing_layers: List[MissingLayer] = field(default_factory=list)
    station_meta: Optional[StationMetadata] = None
    reports: List[SoundingReport] = field(default_factory=list)

    @property
    def parts(self) -> Tuple[ReportPart, ...]:
        return tuple(r.part for r in self.reports)

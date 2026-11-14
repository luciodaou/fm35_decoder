"""
Sections 7 (31313), 8 (41414) and 9-10 (51515 onwards) of a TEMP report.

GEMPAK does not decode these sections; they are read here from the WMO Manual on Codes, apart
from the level data and without any effect on it.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .models import SoundingReport, SoundingSystem

_SONDE_GROUP = re.compile(r"^[0-7/][0-9/]{4}$")
_LAUNCH_GROUP = re.compile(r"^8([01]\d|2[0-3])[0-5]\d$")
_CLOUD_GROUP = re.compile(r"^[0-9/]{5}$")


def _find_31313(groups: List[str]) -> Optional[int]:
    """
    Index of the 31313 that opens section 7: the last one followed by the launch time 8GGgg,
    directly or after the sounding system group. 31313 is also a temperature (-31.3 C), which
    no such groups follow.
    """
    for i in range(len(groups) - 1, -1, -1):
        if groups[i] != "31313":
            continue
        after = groups[i + 1 : i + 3]
        if after and _LAUNCH_GROUP.match(after[0]):
            return i
        if len(after) == 2 and _SONDE_GROUP.match(after[0]) and _LAUNCH_GROUP.match(after[1]):
            return i
    return None


def read_sections(report: SoundingReport, regional_at: Optional[int]) -> None:
    """
    Fills `sounding_system`, `cloud_group` and `raw_remarks` of a report. `regional_at` is the
    position in the text of the 51515 that ended the level data, when there is one.
    """
    text = report.text
    regional = text[regional_at:] if regional_at is not None else ""
    groups = (text[:regional_at] if regional_at is not None else text).split()

    at = _find_31313(groups)
    if at is not None:
        section = [groups[at]]
        sr = rara = sasa = None
        k = at + 1
        if not _LAUNCH_GROUP.match(groups[k]):
            sr, rara, sasa = groups[k][0], groups[k][1:3], groups[k][3:5]
            section.append(groups[k])
            k += 1
        launch = groups[k]
        section.append(launch)
        # 9SnTwTwTw (sea-surface temperature) may follow
        if k + 1 < len(groups) and re.match(r"^9[0-9/]{4}$", groups[k + 1]):
            section.append(groups[k + 1])
        report.sounding_system = SoundingSystem(sr, rara, sasa, f"{launch[1:3]}:{launch[3:5]}")
        report.raw_remarks.append(" ".join(section))

    # The cloud group belongs to Part B; in Parts A and C 41414 after a maximum wind is shear
    if report.part.value == "TTBB":
        for i in range(len(groups) - 2, -1, -1):
            if groups[i] == "41414" and _CLOUD_GROUP.match(groups[i + 1]):
                report.cloud_group = groups[i + 1]
                report.raw_remarks.append(f"41414 {groups[i + 1]}")
                break

    if regional:
        report.raw_remarks.append(regional)

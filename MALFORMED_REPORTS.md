# Malformed reports: what is recognised and how it is handled

Reports on the GTS do not always follow the code form. This document lists the formatting
errors the decoder recognises, what it does with each, and how to record a new one. It also
records valid reports that the decoder once misread, so that the same report is not
investigated twice.

The decoder follows Unidata GEMPAK (see [README.md](README.md#decoding-rules)). A rule is added
here only when a real report shows that the GEMPAK rule loses or corrupts data, and each such
rule is a numbered deviation in the docstring of `src/fm35_decoder/parts.py`.

## Principles

- **Nothing is invented.** A value that cannot be read is missing (`None`); a level that cannot
  be placed is dropped. The merge may compute or interpolate it later, and marks it in `derived`.
- **A group is reinterpreted only when its normal reading is impossible.** `88186` cannot be a
  wind, so it may be read as something else; `66750` can be a temperature, so it is one.
- **Every case comes with the report that showed it**, kept in `tests/samples.py` and checked
  against an independent listing (the University of Wyoming sounding archive).

## Cases from real reports

### 1. `00500` at 1000 hPa (valid report, misread by 2.0)

| | |
| :--- | :--- |
| Report | Boa Vista (82022, SBBV), 4 November 2026 00 UTC, Part A |
| Groups | `99991 29020 12002 00500 ///// ///// 92698 27659 10017` |
| Problem | The report is correct. At 1000 hPa, `hhh` of 500 and more is a height below sea level, `500 − hhh`, so `00500` is 0 m. GEMPAK (`RU_HGHT`) tests `hhh > 500`, and 2.0 followed it: the level came out at 500 m, under a surface of 991 hPa. |
| Handling | `decode_height` tests `hhh >= 500`: `00500` is 0 m. The rule of `RU_MAND` that a height of zero with temperature and wind both missing is no height does not apply to `00500`, which is a reported value: the level is kept at 0 m. `00000 ///// /////` is still dropped. |
| Check | Wyoming lists no level below the surface (991 hPa), so it has no 1000 hPa to compare. The height of the surface computed from the report (925 hPa at 698 m) is 83 m, which puts 1000 hPa within a few metres of sea level: 0 m is consistent with the report, 500 m is not. (Wyoming gives the surface 140 m, from its station table.) |
| Tests | `test_height_up_to_100hpa`, `test_00500_at_1000hpa_is_zero_metres` |

### 2. Wind group left out before a tropopause or maximum wind group (malformed report)

| | |
| :--- | :--- |
| Report | Curitiba (83840, SBCT), 13 November 2026 00 UTC, Part A |
| Groups | `63001 … 15415 61167 23062 10663 ///// 88186 58750 24577 77183 24578 42728` |
| Problem | `Id` = 1 says every level down to 100 hPa has a wind group. The sounding ended at 101 hPa and the station left the 100 hPa wind out instead of coding `/////`. `88186` was read as that wind (and rejected: no direction is 880°), so the tropopause was lost. |
| Handling | Where the wind of a standard level or of a tropopause is expected, a group starting with `66`, `77` or `88` is not a wind (`dd` is 00 to 36, or 99). The level keeps no wind and the group is read again as the indicator it is. |
| Result | 100 hPa: 16630 m, no temperature, no wind. Tropopause: 186 hPa, −58.7 °C, dew point −63.7 °C, 245° 77 kt. Maximum wind: 183 hPa, 245° 78 kt. |
| Check | Wyoming gives −58.7 / −63.7 °C at 186 hPa, and Part B has the same level (`88186 58750`). |
| Tests | `test_tropopause_after_a_missing_wind_group`, `test_maximum_wind_after_a_missing_wind_group` |

The rule is not applied to the temperature group: `66750` (−66.7 °C) and `77161` (−77.1 °C) are
ordinary temperatures of the upper levels.

## Other errors the decoder tolerates

These were already handled in 2.0; the README and `CHANGES_v2.md` give the rules in full.

| What is found | Handling |
| :--- | :--- |
| `21212` after `nnPPP` in Parts B and D | A temperature of 21.2 °C, depression 1.2 °C; it opens the wind section only where a level group is expected. |
| `51515` after `PPhhh` | A temperature of −51.5 °C, depression 1.5 °C; elsewhere it ends the level data. |
| 925 hPa absent from Part A | The decoder goes on with 850 hPa. |
| A group that is not the expected standard level | Search for the next level that is followed by the level after it; given up after ten groups. |
| Standard level without a height (`85///`) | Dropped. |
| `PP000 ///// /////` | The height is taken as missing and the level dropped (not `00500`, case 1). |
| Significant level out of the sequence of `nn` | Taken only if its pressure is lower than the last, dropped again if the next level does not follow it. |
| Significant level whose temperature or wind is `/////` | Not kept. |
| `nn/// /////` | Recorded as a layer of missing data; nothing is interpolated across it. |
| `88///`, or a maximum wind without a wind | Dropped with its groups, which are not read as levels. |
| Tropopause wind `00000` | Taken as missing. |
| Wind direction above 360°, or `99` | No wind. |
| Two groups run together (ten characters) | Read as two groups. |
| A field longer than 15 characters | Ends the report. |
| Header that cannot be decoded | `DecodeError` from `parse_report`; logged and skipped when reading a stream. |

## Recording a new case

1. Keep the report exactly as received, with its station, date and hour.
2. Decode it with `parse_report` and compare each level with an independent listing, for
   example `https://weather.uwyo.edu/wsgi/sounding?datetime=YYYY-MM-DD%20HH:00:00&id=IIiii&src=FM35&type=TEXT:LIST`.
3. Decide the handling by the principles above. If the normal reading of the group is possible,
   the report is wrong but the decoder is not: note it here without changing a rule.
4. Add the report to `tests/samples.py` and a test of the exact values to `tests/test_parts.py`
   (or `tests/test_groups.py` for a single group).
5. If the handling differs from GEMPAK, number it in the docstring of `parts.py` and in the
   README, then add a section to this document and an entry to `CHANGELOG.md`.

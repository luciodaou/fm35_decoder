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
| Handling | `decode_height` tests `hhh >= 500`: `00500` is 0 m. The level is kept although its temperature and wind are missing (case 4). |
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

### 3. `88999` in Part C followed by its groups (valid report, misread up to 2.0.1)

| | |
| :--- | :--- |
| Report | SBMQ (82099), 6 October 2026 12 UTC, Part C. Also SBBE (82193), 31 August 2026 12 UTC, and SBTS (82026), 22 October 2026 12 UTC. |
| Groups | `20656 ///// 88999 81747 35027 88324 57979 22536 77999` |
| Problem | `88999` means "no tropopause", but in Part C the pressure is in tenths of hPa, so a tropopause at 99.9 hPa is coded `88999` too. GEMPAK (`RU_MTRP`) and the decoder up to 2.0.1 stopped at every `88999`: this tropopause and the one after it were lost. |
| Handling | In Part C, `88999` is a tropopause at 99.9 hPa when a temperature group and a wind group (or the next indicator, case 2) follow it. It means none when `77999`, a maximum wind group, a section marker or the end follows. A temperature that starts with `66` or `77` (`77562`: −77.5 °C, or a maximum wind at 56.2 hPa) is taken as one only when `77999` comes after its wind, since a maximum wind is followed by its shear, another level or the end. A temperature that starts with `88` is one when a wind follows it (`88874 88536 25020` at SBMN, 82332: −88.5 °C). In Part A `88999` always means none. |
| Result | Tropopauses at 99.9 hPa (−81.7 °C, dew point −86.4 °C, 350° 27 kt) and 32.4 hPa (−57.9 °C, 225° 36 kt). |
| Check | Part D of the same sounding starts with the same level (`11999 81747`), and Wyoming lists 99.9 hPa at −81.7 / −86.4 °C. In an archive of 3,286 soundings, 15 Part C reports from 13 stations have `88999` followed by data, and Part D confirms the level in all 15; the 15 reports with `88999` followed by a maximum wind keep no tropopause. |
| Tests | `test_part_c_88999_with_its_groups_is_a_tropopause_at_99_9hpa`, `test_part_c_88999_alone_means_no_tropopause`, `test_part_a_88999_is_never_a_tropopause`, `test_tropopause_temperature_that_starts_with_88` |

### 4. Standard level with a height and nothing else (valid report, dropped up to 2.0.1)

| | |
| :--- | :--- |
| Report | SBLO (83768), 30 August 2026 12 UTC, Part C |
| Groups | `80125 … 50083 59379 34509 30400 ///// 88999 77999` |
| Problem | The sounding ended between 50 and 30 hPa and the report gives 30 hPa a height only, 24000 m. GEMPAK (`RU_MAND`) takes a level with no temperature and no wind for padding when its height, after the thousands are restored, is a multiple of 1000 m. That catches `PP000`, but also every height in decametres that ends in `00`: `30400` (24000 m), `20200` in Part A (12000 m), and `00500` (0 m, case 1). |
| Handling | The level is dropped only when the height is coded `000`. |
| Check | 20 soundings of the archive, all `30400 /////` in Part C. The 2,580 Part C reports that give 30 hPa a temperature have a median height of 23940 m, so 24000 m is an ordinary value. |
| Tests | `test_height_only_level_whose_height_ends_in_000_metres`, `test_height_only_levels_in_part_a`, `test_00500_at_1000hpa_is_zero_metres` |

### 5. 100 hPa coded `100` in Parts C and D (malformed report)

| | |
| :--- | :--- |
| Report | SBCG (83612), 31 August 2026 00 UTC, Parts B, C and D |
| Groups | Part B ends `88102 80157 99100 80557`; Part D starts `11100 80557 22929 78159`; Part C has `88100 80557 25534 77999` |
| Problem | Parts C and D code pressures in tenths of hPa, so `100` is 10.0 hPa. The station repeats the 100 hPa level of Part B as the first level of Part D, and gives the tropopause at 100 hPa in Part C, both in whole hPa. Read by the rule they put a level at −80.5 °C at 10 hPa in the merged profile. |
| Handling | The first level of a section of Part D coded `100` is 100 hPa when the level after it has a pressure above 10.0 hPa. The first tropopause of Part C coded `88100` is 100 hPa: a first tropopause at 10 hPa does not occur. A later tropopause, or a level of Part D that is not the first, is 10.0 hPa as coded. |
| Check | 7 soundings of the archive start Part D with `11100`; in 5 the last level of Part B is the same group, in the other 2 Part B ends at 101 hPa. All 4 with `88100` in Part C start Part D with `11100` and the same temperature. No other tropopause of the archive is below 10.5 hPa. |
| Tests | `test_part_d_that_starts_with_100hpa`, `test_part_d_level_at_10hpa_is_kept`, `test_part_c_tropopause_coded_100_is_at_100hpa` |

### 6. Surface coded `00PPP` in Part A (malformed report)

| | |
| :--- | :--- |
| Report | SBCY (83362), 5 November 2026 00 UTC, Parts A and B |
| Groups | `TTAA 5500/ 83362 00986 29256 33005 88999 77999=` and `TTBB 5500/ 83362 00986 29256 41414 22500 51515 10159=` |
| Problem | A surface observation sent as a TEMP, with the surface group of Part A written `00986`, as in Part B, in place of `99986`. Read by the rule it is a 1000 hPa level at `500 − 986` = −486 m with the surface temperature. |
| Handling | `00PPP` in the place of the surface group is the surface when `Id` is `/` (no standard level has a wind group) and a temperature, a wind and then the end of the levels follow. With any other `Id`, or when more levels follow, it is a 1000 hPa level. |
| Check | 3 soundings of the archive, all from this station, and Part B gives the same pressure and temperature each time. |
| Tests | `test_surface_coded_00_in_part_a`, `test_00_group_that_is_a_1000hpa_level` |

## Reports that are wrong and decoded as coded

Nothing in these can be told from a correct report by its form, so no rule changes: the decoder
returns what the groups say. They are kept as tests (`tests/test_archive.py`) so that a change
of rule that alters them is noticed.

| Report | What it says |
| :--- | :--- |
| SBBR (83378), 22 October 2026 00 UTC | Every height about 1200 m too high (`50705`: 500 hPa at 7050 m). |
| SBCR (83554), 30 September 2026 12 UTC | Every height about 350 m too low (`00764`: 1000 hPa at −264 m, under a surface of 955 hPa). |
| SBPV (82824), 1 October 2026 00 UTC | A test pattern: surface `99999`, the same wind on four levels, 500 hPa at 4750 m. |
| SBVT (83649), 1 September 2026 12 UTC | Surface wind `03090`, 30° at 90 kt. |
| SBTG (82411), 22 October 2026 12 UTC | Surface only: 904 hPa and −22.7 °C in Part A, `00004` (1004 hPa) in Part B. |
| SBUL (83525), 1 November 2026 12 UTC | `88/// 599//` ends the temperature levels of Part D: a layer of missing data that no level closes. Nothing is recorded for it. |
| SBBE (82244), 27 October 2026 12 UTC | 1,264 winds in Part D, most at a pressure already given. All are levels of the report; the merged profile has each pressure once. |

## Other errors the decoder tolerates

These were already handled in 2.0; the README and `CHANGES_v2.md` give the rules in full.

| What is found | Handling |
| :--- | :--- |
| `21212` after `nnPPP` in Parts B and D | A temperature of 21.2 °C, depression 1.2 °C; it opens the wind section only where a level group is expected. |
| `51515` after `PPhhh` | A temperature of −51.5 °C, depression 1.5 °C; elsewhere it ends the level data. |
| 925 hPa absent from Part A | The decoder goes on with 850 hPa. |
| A group that is not the expected standard level | Search for the next level that is followed by the level after it; given up after ten groups. |
| Standard level without a height (`85///`) | Dropped. |
| `PP000 ///// /////` | The height is taken as missing and the level dropped (case 4). |
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
4. Add the report to `tests/archive_samples.py` and a test of the exact values to
   `tests/test_archive.py` (or `tests/test_groups.py` for a single group).
5. If the handling differs from GEMPAK, number it in the docstring of `parts.py` and in the
   README, then add a section to this document and an entry to `CHANGELOG.md`.

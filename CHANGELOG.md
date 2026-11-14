# Changelog

## 2.0 - 2026-11-14

The decoder is rebuilt on the upper-air decoder of Unidata GEMPAK (`dcuair` and the `RU` bridge
library, `gempak/source/bridge/ru`). The level data is decoded by the rules of its Fortran
routines; the result is a typed data model, with the two DataFrames of version 1 still available
from `decode`. Reported temperatures, dew points, heights and winds of the test soundings
(station 83746, 11–13 November 2026, and station 83779 against the University of Wyoming listing)
decode as in 1.2.

### Added

- **Bulletins and report headers.** WMO abbreviated headings (with `BBB`), `SOH`/`ETX` framing,
  any number of reports and stations per bulletin, `NIL` reports. Each report gives its part,
  station, day, hour, wind unit and `Id`.
- **Observation time**, from the day and hour of the report and a reference time for the year and
  the month, and its rounding to 3 hours, on which the parts of a sounding are matched.
- **Data model**: `SoundingReport`, `SoundingLevel`, `MergedSounding`, `WmoHeader`, `MissingLayer`,
  `SoundingSystem`, `StationMetadata`, and the enums `ReportPart`, `LevelType`, `WindUnit`,
  `Platform`. Wind speeds are in m/s in the model.
- **Pipeline**: `iter_bulletins`, `iter_reports`, `parse_report`, `iter_decoded_reports`,
  `merge_reports`, `merge_parts`, `decode_soundings`, `to_dataframes`.
- **PILOT** (FM 32, `PPAA`–`PPDD`): winds on standard levels, on heights and on pressure levels.
- **TEMP SHIP** (`UUAA`–`UUDD`) and **TEMP DROP** (`XXAA`, `XXBB`): call sign, position, and the
  dropsonde identifier from section `61616`.
- **Station tables**: `load_station_table` reads the GEMPAK format (`snstns.tbl`); with one, the
  surface of a merged sounding takes the station elevation.
- **Corrections**: of two reports of the same part, the first is kept unless the later one comes
  from a bulletin whose `BBB` starts with `C`, `R` or `A`.
- `decode(..., wind_unit="m/s")` and `decode(..., interpolate=False)`.
- `df_main` has a `Derived` column naming the values of each row that were computed or
  interpolated, and `Source` distinguishes `Surface`, `Tropopause` and `MaxWind` levels.
- Tropopause and maximum wind levels join the profile at their pressure.

### Changed (decoding now follows GEMPAK)

- **Standard levels are read in the order of the code form.** A group out of place is not a
  level. After a bad group the decoder looks for the next level that is followed by the level
  after it, so a level that comes after a gap at the very end of a cut report is not found.
  Nothing is decoded in a Part A whose first group is a tropopause, maximum wind or `51515` group.
- **Significant levels follow the sequence of `nn`**, and their pressure must decrease. A level
  whose temperature (or wind) is missing is not kept.
- **Heights** are restored by a fixed rule per level instead of the closest standard-atmosphere
  value: `85950` is 950 m (was 1950 m), `00500` is 500 m (was 0 m), `70500` is 2500 m (was
  3500 m). A standard level without a height is dropped.
- **Wind direction**: north (`36`) is 0° (was 360°). Variable wind (`99`) and any direction above
  360° give no wind (the speed was kept). `00` with a speed is 0° with that speed.
- **Dew-point depression** `51`–`55` is read as 1–5 °C (was missing).
- **Part B pressures** under 100 are always 1000 hPa and more.
- **`Id` in Part C**: `1` and `0` give every level a wind group.
- **Tropopause**: a wind of 0° and speed 0 is taken as missing; `88999` ends the search. A
  **maximum wind** without a wind is dropped.
- A ten-character field is read as two groups; a field longer than 15 characters ends the report.
- **Interpolation**: a dew point is filled only where the temperature is filled too.
- An empty result has the usual columns (it had none).

Two rules of 1.2 are kept where GEMPAK differs: `21212` and `51515` are markers only where a
level group is expected (`21212` after `nnPPP` is 21.2 °C; `51515` after `PPhhh` is −51.5 °C).
The `31313` and `41414` sections, the shear group and the layers of missing data, which GEMPAK
does not decode, are kept as well; a layer marker (`nn///`) takes its place in the sequence of
`nn`.

### Removed

- **Extrapolated standard levels** (`Source` = `Extrapolated`): no level is added that the report
  does not hold.
- `route_parts` and `split_bulletin` (use `iter_reports`), and the functions of
  `fm35_decoder.decoder` that decoded single groups or parts (`decode_temperature`,
  `decode_wind`, `decode_height`, `parse_ttaa_ttcc`, `parse_ttbb_ttdd`, `interpolate_data`,
  `calculate_geopotential`, …): see `fm35_decoder.groups`, `parts` and `merge`.
- `ValueError` for a message with fewer than two temperatures: a surface-only report decodes.
- A message without its part name and header is no longer decoded.
- The CSV versions of Code tables 3931 and 0777 are no longer read (the rules are in the code).
- NumPy is no longer a direct dependency (pandas still is, for the DataFrames).

## 1.2 - 2026-11-13

A review of the decoder against the WMO Manual on Codes (WMO-No. 306, Volume I.1, FM 35 and its
code tables) and the WMO Common Code Tables, cross-checked with the University of Wyoming
decoding of 24 messages from station 83746.

### Fixed

- **Temperatures that look like section markers (Parts A and C).** `52525` (-52.5 °C), `54545`
  (-54.5 °C), `56565` (-56.5 °C) and `58585` (-58.5 °C) in a temperature position were taken for
  regional sections, and the rest of the part was dropped: the levels above, the tropopause, the
  maximum wind and the sounding system section.
- **`21212` as a temperature (Parts B and D).** `21212` after a level group (21.2 °C with a
  depression of 1.2 °C) was taken for the wind section, and the temperature levels after it were
  decoded as winds.
- **Standard level decoded twice.** A standard level reported with its height and `/////` just
  above the top of the sounding got a second, "Extrapolated" row with a made-up temperature. A
  level the report holds is now left as reported.
- **Sounding system tables.** `sr` (Code table 3849), `rara` (Code table 3685 / Common Code Table
  C-2) and `sasa` (Code table 3872 / Common Code Table C-7) did not follow the WMO tables:
  `31313 42308` was decoded as "NOAA solar corrected", "Mesural FMO 1950A" and "Radar (5 cm)"
  instead of "Solar and infrared corrected automatically by radiosonde system", "Vaisala
  RS41/DigiCORA MW41" and "Automatic satellite navigation". The three tables are rebuilt from
  the WMO sources and cover every code figure.
- **`Id` figures the table does not define** (6 in Part A; 0, 4, 6, 8, 9 in Part C) no longer
  remove the wind groups, which could then be read as levels.
- **Tropopause or maximum wind without a readable pressure** (`88///`, `77///`): the level is
  dropped with its own groups, which are no longer read as standard levels.
- **Wind direction `00` with a speed** (north is `36`) keeps its speed and has no direction,
  instead of a direction of 0°.

### Changed

- **Layers of missing data** (`nn/// /////`, Regulations 35.3.1.6 and 35.3.2.2) are recognised:
  nothing is interpolated inside them, and each is listed in `df_special` under the new subject
  `Missing Data` (`Temperature` or `Wind`, with the pressures of its boundary levels).
- **Extrapolated standard levels** (Regulation 35.2.2.4) carry their geopotential only. The
  extrapolated temperature serves that calculation and is no longer given.
- **Computed heights.** For a level without a temperature, the temperature used in the
  hypsometric calculation is interpolated in ln(P) (it was interpolated by row). Above the last
  temperature a height is computed only within the limits of Regulation 35.2.2.4 (25 hPa, and a
  quarter of the level's pressure); further up, a level keeps no height unless the report gives
  it.
- **`rara` figures assigned twice.** Common Code Table C-2 gave the figures 01-99 to a second
  generation of systems. A reassigned figure is decoded as the newer system, as in reports of
  today (`23` is Vaisala RS41/DigiCORA MW41); reports from before the reassignment (2008-2022,
  depending on the figure) used the older meaning.
- **Cloud tables.** `Nh` code figures 9 and `/` and `h` code figure `/` use the wording of Code
  tables 2700 and 1600.
- **CSV tables.** The files in `table_codes` hold the same entries as the built-in tables.
- The documentation no longer lists FM 36 TEMP SHIP and FM 38 TEMP MOBIL as decoded: their
  position groups are not read.

### Not changed

Reported temperatures, dew points, heights and winds of the 24 test messages decode as before
and agree with the University of Wyoming decoding.

## 1.1 - 2026-10-16

- Wind groups of standard levels follow `Id`.
- Pressures in tenths of hPa in Parts C and D; tropopause and maximum wind listed per part.
- Wind speeds in m/s or knots according to `YY`.
- Regional and national sections end the level data.
- Nothing is extrapolated above the last observation; a lone TTBB decodes.

## 1.0 - 2026-09-03

- In-memory WMO tables, scientific decoding fixes and WMO documentation.

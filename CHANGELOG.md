# Changelog

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

# FM35 Decoder

[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=flat&logo=ko-fi&logoColor=white)](https://ko-fi.com/luciodaou)
[![PyPI - Version](https://img.shields.io/pypi/v/fm35_decoder.svg)](https://pypi.org/project/fm35_decoder)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fm35_decoder.svg)](https://pypi.org/project/fm35_decoder)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python decoder for **WMO FM 35 TEMP** and **FM 32 PILOT** upper-air reports (and their ship and
dropsonde forms, FM 36 and FM 37), based on the upper-air decoder of
[Unidata GEMPAK](https://github.com/Unidata/gempak) (`dcuair`, the `RU` bridge library).

For a plain-English guide to the code form, see [TEMP_DECODING.md](TEMP_DECODING.md).
Version 2.0 changes the decoding rules and part of the API: see [CHANGELOG.md](CHANGELOG.md).
Reports that do not follow the code form, and what the decoder does with each, are listed in
[MALFORMED_REPORTS.md](MALFORMED_REPORTS.md).

---

## Installation

```bash
pip install fm35_decoder
```

---

## Quickstart

### The parts of one sounding, as DataFrames

```python
from fm35_decoder import decode

ttaa = "TTAA 73121 83779 99938 21224 01008 00163 ///// ///// 92843 20019 07506 85570 18650 36008 ..."
ttbb = "TTBB 73128 83779 00938 21224 11882 16804 22870 19856 33735 11056 44712 08616 55615 01218 ..."
ttcc = "TTCC 73123 83779 70865 71568 15020 50064 67574 12519 30380 58383 08535 88906 77162 26018 ..."
ttdd = "TTDD 7312/ 83779 11906 77162 22585 70370 33542 70970 44445 63978 55283 57785 21212 11935 ..."

df_main, df_special = decode(ttaa, ttbb, ttcc, ttdd)
```

- `df_main` is the profile, surface first: `Pressure` (hPa), `Height` (m), `Temp`, `DewPoint` (°C),
  `WindDir` (degrees), `WindSpeed` (knots), `Source` (`Surface`, `Standard`, `SigTemp`, `SigWind`,
  `Tropopause`, `MaxWind`) and `Derived`, which names the columns of the row that were computed
  rather than reported (`Height,Temp,DewPoint`).
- `df_special` lists the tropopause, maximum wind, layers of missing data, sounding system and
  cloud entries as text, with the part each came from.

Options: `decode(..., wind_unit="m/s")` for speeds in m/s, and `decode(..., interpolate=False)` to
leave temperature, dew point and wind empty where the report gives none. Any argument may hold a
whole bulletin; every report found in it is used.

### A stream of bulletins, as typed objects

```python
from datetime import datetime, timezone
from fm35_decoder import decode_soundings, load_station_table

stations = load_station_table("gempak/tables/stns/snstns.tbl")      # optional
with open("uair.gts", encoding="latin-1") as stream:
    soundings = decode_soundings(stream, reference_time=datetime(2026, 11, 13, tzinfo=timezone.utc),
                                 station_table=stations)

for sounding in soundings:
    print(sounding.station_id, sounding.timestamp_utc, [part.value for part in sounding.parts])
    for level in sounding.profile:
        print(level.pressure_hpa, level.height_m, level.temp_c, level.wind_speed_ms, level.derived)
```

The steps are available one by one, as generators where the input allows it:

| Function | GEMPAK routines | Result |
| :--- | :--- | :--- |
| `iter_bulletins(source)` | `DC_GBUL`, `DC_GHDR` | `Bulletin` (WMO heading and text) |
| `iter_reports(text)` | `RU_GRPT` | the text of each report |
| `parse_report(text, header, reference_time)` | `RU_SHDR`, `RU_DECD` and the part routines | `SoundingReport` |
| `iter_decoded_reports(source, reference_time)` | the three above | `SoundingReport`, one at a time |
| `merge_reports(reports, station_table)` | — | `MergedSounding` per station and time |

A `SoundingReport` holds the part, the station, the day and hour, the wind unit, its levels
(`SoundingLevel`, wind speeds always in m/s), the layers of missing data, the sounding system
group and the regional sections as text. A report whose header cannot be decoded raises
`DecodeError` in `parse_report` and is logged and skipped by the functions that read a stream.
A `NIL` report comes back with `nil` set and no levels.

The observation day and hour come from the report; the year and the month come from
`reference_time` (when the report was received; now, if not given). Parts are merged when they
share the station and the time rounded to 3 hours.

---

## Decoding rules

The level data is decoded as GEMPAK does. The rules that matter most in practice:

- **Order of the code form.** Standard levels are expected in order (1000, 925, … 100 hPa; 70, 50,
  … 1 hPa in Part C). After a group that is not the expected level, the decoder looks for the next
  level that is itself followed by the level after it, and gives up after ten groups. Significant
  levels are expected in the sequence of `nn`; one out of sequence is taken only if its pressure is
  lower than the last, and dropped again if the next level does not follow it.
- **`Id`** gives the last standard level with a wind group (hundreds of hPa in Part A, tens in
  Part C; `/` for none). In Part C, `1` and `0` give every level a wind group.
- **Heights** are restored by a fixed rule per level (`RU_HGHT`): `00515` is −15 m, `00500` is 0 m, `85570` is
  1570 m, `70980` is 2980 m, `30970` is 9700 m, `20241` is 12410 m, `50064` in Part C is 20640 m.
  A standard level without a height is not kept.
- **Temperature**: negative when the last figure is odd. **Depression**: tenths up to 50, whole
  degrees plus 50 above (51–55, which WMO does not use, are read as 1–5 °C).
- **Wind**: `ddfff` with 500 added to `fff` for a direction ending in 5. 360° is given as 0°. A
  direction above 360° (`99`, variable) gives no wind. Speeds follow `YY` (knots when 50 is added).
- **Tropopause and maximum wind** (`88`, `77`, `66`) are numeric levels; their pressure is in
  tenths of hPa in Part C. `88999` and `77999` mean none. A maximum wind without a wind is dropped.
- **Levels without data** (a significant level whose temperature or wind is `/////`) are not kept.

Four rules differ from GEMPAK. The first two are about where a marker is recognised; the last
two come from real reports, described in [MALFORMED_REPORTS.md](MALFORMED_REPORTS.md):

1. `21212` opens the wind section of Parts B and D only where a level group is expected. After
   `nnPPP` it is a temperature of 21.2 °C with a depression of 1.2 °C.
2. `51515` after `PPhhh` is a temperature of −51.5 °C with a depression of 1.5 °C. Where a level
   or a wind is expected it ends the level data.
3. `00500` at 1000 hPa is 0 m (GEMPAK: 500 m), and the level is kept even when its temperature
   and wind are missing. `00000 ///// /////` is still no height.
4. `66`, `77` or `88` where the wind of a standard level or of a tropopause is expected is the
   indicator of the next group: the wind group was left out, and the tropopause or maximum wind
   that follows is still decoded.

Added to what GEMPAK decodes (from the WMO Manual on Codes): the `31313` section (radiation
correction, sounding system, tracking, launch time), the `41414` cloud group of Part B, the
`4vbvbvava` shear group of a maximum wind, and layers of missing data (`nn/// /////`), which are
listed and never interpolated across.

---

## Merged profile

GEMPAK stores the parts unmerged, so the merge is this library's own:

- Levels are combined by pressure, to the tenth of hPa. Standard levels come first, then
  significant temperature levels, significant winds, PILOT winds, tropopause and maximum wind; a
  value already there is never replaced.
- One report per part: the first received, unless a later one comes from a bulletin whose `BBB`
  marks a correction, retransmission or amendment.
- **Heights** of levels that report none are computed with the hypsometric equation and the
  virtual temperature. Above the last temperature a height is computed only within the limits of
  Regulation 35.2.2.4 (25 hPa, and a quarter of the pressure of the level). With a station table,
  the surface takes the station elevation.
- **Interpolation** (on request; on by default in `decode`) fills temperature and dew point
  linearly in ln(p), and the wind by its components, only between observed levels and never inside
  a layer reported as missing. The dew point never exceeds the temperature.
- PILOT winds on heights get a pressure from the heights of the profile when they fall inside it.

Every value computed here is named in `SoundingLevel.derived` (the `Derived` column).

---

## License

This project is licensed under the terms of the **MIT License**.
You are free to use, modify, and distribute this software with attribution to the original author.

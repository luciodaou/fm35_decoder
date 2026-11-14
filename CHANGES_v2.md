# From v1.2 to v2.0: what changed to follow GEMPAK

This document lists every rule that changed between `fm35_decoder` 1.2 and 2.0, with the exact
behaviour of 2.0, so that the decoder can be written again in another language (a Rust crate)
from this text and the Python sources.

- **Reference**: the upper-air decoder of Unidata GEMPAK, `gempak/source/bridge/ru/*.f` (the `RU_`
  library) driven by `source/programs/dc/dcuair/dcudcd.f`. Each rule below names its Fortran
  routine and the Python function that ports it.
- **Python sources**: `src/fm35_decoder/` at version 2.0. Where this text and the code disagree,
  the code is right.
- **Scope of "GEMPAK standard"**: the decoding of bulletins, reports, headers and level groups.
  GEMPAK's merge of the parts (`MR_` library) is not in the extracted sources, so the merge of 2.0
  is not a port (section 8).

Contents: 1 architecture · 2 conventions · 3 bulletins and headers · 4 group decoders ·
5 Parts A and C · 6 Parts B and D · 7 PILOT, ship, dropsonde · 8 merge · 9 where 2.0 is not
GEMPAK · 10 API changes · 11 notes for the Rust crate · 12 test vectors.

## 1. Architecture

v1.2 was one module (`decoder.py`) that took the text of each part and produced two pandas
DataFrames directly. 2.0 is a pipeline with a typed model between the text and the DataFrames:

```
text ─ iter_bulletins ─▶ Bulletin ─ iter_reports ─▶ report text ─ parse_report ─▶ SoundingReport
                                                                                       │
                              (df_main, df_special) ◀─ to_dataframes ◀─ MergedSounding ◀─ merge_reports
```

| Module | Ports | Content |
| :--- | :--- | :--- |
| `models.py` | — | Enums and records |
| `groups.py` | `RU_GFLD`, `RU_TEMP`, `RU_WIND`, `RU_HGHT`, `RU_PLVL`, `RU_WHGT`, `RU_PPMW`, `RU_DROP` | Field reader and single-group decoders |
| `bulletin.py` | `DC_GBUL`, `DC_GHDR`, `RU_GRPT`, `RU_SHDR`, `RU_RTIM`, `RU_ADJT` | Bulletins, reports, header, time |
| `parts.py` | `RU_MSFC`, `RU_MLVL`, `RU_MAND`, `RU_MTRP`, `RU_MMXW`, `RU_STMP`, `RU_PWND`, `RU_SIGW`, `RU_PPAA`/`CC`, `RU_DRP1`, `RU_DECD` | The parts |
| `sections.py` | — (WMO) | `31313`, `41414`, `51515` sections |
| `merge.py` | `RU_DUPE` (selection only) | One profile from the parts |
| `stations.py` | `TB_RSTN` format | `snstns.tbl` loader |
| `decoder.py` | — | Entry points and DataFrames (Python only) |

Only the last module depends on pandas. The crate needs everything up to `MergedSounding`.

## 2. Conventions that changed

| Topic | v1.2 | 2.0 |
| :--- | :--- | :--- |
| Missing value | `NaN` / `None` in a DataFrame | `None` (`Option`) in the model; GEMPAK uses `RMISSD = -9999` |
| Wind speed | knots | **m/s** in the model, whatever the report uses; knots → m/s with `1852 / 3600` (`PR_KNMS` is not in the extract) |
| North | 360° | **0°** |
| Reported or computed | Not told apart | `SoundingLevel.derived` names the fields computed by the merge |
| Level kind | `Source` text | `LevelType`: `Surface`, `Standard`, `SigTemp`, `SigWind`, `Tropopause`, `MaxWind` |
| Error | `ValueError` in several places | `DecodeError` only, and only for a header that cannot be decoded; level data never raises |
| Text | Upper-cased, `=` removed | `ST_UNPR`: every run of characters outside `0x21`–`0x7E` becomes one blank, then trimmed. After this the text is ASCII |

## 3. Bulletins, reports, headers and time (new in 2.0)

v1.2 had none of this: `split_bulletin` cut a text at the part names, one report per part (the
last one won), the station and the hour were skipped, and `YY` only gave the wind unit.

### 3.1 Bulletins: `iter_bulletins` (`DC_GBUL`, `DC_GHDR`)

- A bulletin starts at `SOH` (`0x01`) or at a heading line and ends at `ETX` (`0x03`), at the next
  start, or at the end of the input. Text with neither is one bulletin without a header.
- Heading line: `TTAAii CCCC YYGGgg [BBB]`. Accepted: `ii` of 0 to 2 digits; the time as 6 digits,
  6 digits + `Z`, or 8 digits `MMDDHHMM` (the last 6 are used); `UTC` before `BBB`. The day must be
  01–31 and the time ≤ 2359. A line that starts with a part name (`TTAA` …) is never a heading.
- A line of 3 to 5 digits before the heading is the sequence number.
- `BBB` starting with `C`, `R` or `A` marks a correction, retransmission or amendment
  (`WmoHeader.is_correction`).

### 3.2 Reports: `iter_reports` (`RU_GRPT`)

- A report starts at `TT`, `PP`, `UU` or `XX` followed by `AA`, `BB`, `CC` or `DD`.
- It ends at `=`, at the next `TT`/`PP`/`UU`/`XX` (any occurrence, not only a part name), or at the
  end of the bulletin. A report that starts with `XX` ends only at `=` or at `XXAA`…`XXDD`, because
  a dropsonde report holds free text.
- A bulletin may hold any number of reports from any number of stations.

### 3.3 Fields: `Fields` (`RU_GFLD`)

The reader has a position that is saved and restored (the Fortran `ipoint`) and an end.

- A field is what stands between blanks. A field of exactly **10 characters is returned as two
  fields of 5** (v1.2 dropped it).
- A field longer than `MAXFLN = 15` ends the report (v1.2 ignored it).
- `ENDRPT` (`Fields.ends_report`): true when there is no field, the field is longer than 15, the
  field starts with `51515`, or it starts with one of the prefixes the caller gives (`66`, `77`,
  `88`, `41414`). The position of the first `51515` that ended a section is remembered: the
  regional section starts there.

### 3.4 Header: `parse_header` (`RU_SHDR`)

| Item | v1.2 | 2.0 |
| :--- | :--- | :--- |
| Part | Substring test | First 4 characters. `TT`/`PP` + `AA`–`DD` land; `UU` + `AA`–`DD` ship; `XX` + `AA`/`BB` dropsonde. `UU` and `XX` parts are decoded as the `TT` part of the same letter. Anything else: `DecodeError` |
| `YY` | Unit only | `> 50`: knots and day = `YY − 50`; else m/s |
| `GG` | Ignored | Hour. 24 is 00 of the next day; above 24 the report has no time |
| `Id` | Table per part; unknown → winds assumed present | A digit or missing (`/`). Used in 5.2 |
| Station | Skipped | Land: `IIiii`, kept as 5 digits. Not a number: `DecodeError` |
| Ship | — | Call sign (≤ 8 characters) **before** `YYGGId`, then `99LaLaLa QcLoLoLoLo MMMULaULo`. Station id: call sign (6 characters) + hour, or `S` + 7 digits from the position when the call sign is `SHIP` |
| Dropsonde | — | Position groups after `YYGGId`; identifier from `61616` (7.3) |
| `NIL` | Empty result | After the header, `NIL` with or without `=`: the report has `nil = true` and no levels |

Position (`RU_DROP`, `decode_position`): `99LaLaLa` in tenths of a degree; `Qc` must be 1, 3, 5
or 7; longitude is negative for 5 and 7, latitude for 3 and 5; the Marsden group is read and
ignored.

### 3.5 Time: `observation_time`, `nominal_time` (`RU_RTIM`, `RU_ADJT`)

- The year and month come from a **reference time** (when the report was received; an argument,
  now by default). If the day of the report is above 27 and the reference day is 1, the report
  belongs to the month before.
- Nominal time: the hour rounded to the nearest multiple of 3 (`hour mod 3 = 1` → −1 h,
  `= 2` → +1 h).
- The parts of one sounding share the station id and the nominal time (`station_key`).

## 4. Group decoders

### 4.1 Temperature and dew point `TTTDD` (`RU_TEMP`, `decode_temp`)

- `TTT` in tenths; negative when it is odd. v1.2 used a table (Code table 3931); the result is the
  same.
- `DD ≤ 50`: tenths of a degree. `DD > 50`: `DD − 50` whole degrees. **Changed:** 51–55 are
  1–5 °C (v1.2: missing).
- `TTT` not a number: both missing. `DD` not a number: temperature only.
- Dew point = temperature − depression, rounded to 0.1.

### 4.2 Wind `ddfff` (`RU_WIND`, `decode_wind`)

1. `dd` and `fff` must be numbers, else no wind.
2. Direction = `dd × 10`. If `fff ≥ 500`: `fff −= 500` and direction `+= 5`.
3. Direction above 360, or the group `31313`: **no wind at all**.
4. Direction 360 becomes 0.
5. Speed in m/s (× `1852/3600` when the report is in knots).

| Case | v1.2 | 2.0 |
| :--- | :--- | :--- |
| `dd = 36` | 360° | 0° |
| `dd = 99` (variable) | No direction, speed kept | No wind |
| `dd = 00`, speed > 0 | No direction, speed kept | 0° with that speed |

### 4.3 Height `PPhhh` (`RU_HGHT`, `decode_height`)

**The largest change.** v1.2 chose the thousands that brought the height closest to a
standard-atmosphere value. 2.0 uses the fixed rules of GEMPAK. `PP = 92` is 925 hPa and
`PP = 00` is 1000 hPa. `hhh` not a number: pressure without a height.

Up to 100 hPa (Part A), `hhh` in metres down to 700 hPa and in decametres from 500 hPa:

| Level | Height in metres |
| :--- | :--- |
| 1000 | `hhh`; if `hhh > 500`: `500 − hhh` (below sea level) |
| 925 | `hhh`; if `hhh < 200`: `+1000` (not for a dropsonde) |
| 850 | `hhh`; if `hhh < 900`: `+1000` |
| 700 | `hhh < 500`: `+3000`; else `+2000` |
| 500, 400 | `hhh × 10` |
| 300 | `hhh × 10`; if under 3000: `+10000` |
| 250 | `hhh × 10`; if under 5000: `+10000` |
| 200 | `hhh × 10`; if under 7000: `+10000` |
| 150, 100 | `hhh × 10 + 10000` |

Above 100 hPa (Part C), `PP` in hPa and `hhh` in decametres (`z = hhh × 10`):

| Level | Height in metres |
| :--- | :--- |
| 70 | `z + 10000` |
| 50 | `z ≥ 8000`: `+10000`; else `+20000` |
| 30, 20 | `z + 20000` |
| 10 | `z > 8000`: `+20000`; else `+30000` (8000 exactly gives 38000) |
| 7, 5, 3 | `z + 30000` |
| 2 | `z > 8000`: `+30000`; else `+40000` |
| 1 | `z + 40000` |

Heights that differ from v1.2: `85950` is 950 m (was 1950), `00500` is 500 m (was 0), `70500` is
2500 m (was 3500).

### 4.4 Significant level `nnPPP` (`RU_PLVL`, `decode_sig_level`)

- `nn` must be a digit repeated (`00`, `11` … `99`); the level number is that digit. Anything
  else, or `PPP` not a number, is "not a level" (−1).
- Part B: `PPP` in hPa, and **under 100 always means 1000 hPa and more** (v1.2 did this only near
  the surface). Part D: tenths of hPa.

### 4.5 Surface pressure `99PPP` (`RU_MSFC`)

Whole hPa; under 100 means 1000 hPa and more (`99012` is 1012 hPa). Unchanged from v1.2. (The
porting guide says tenths; it is wrong.)

## 5. Parts A and C

Order in `parse_report`: surface (Part A only) → standard levels → tropopauses → maximum winds.

### 5.1 Surface: `_surface` (`RU_MSFC`)

- The surface must be the **first group** after the header. If the first group is not `99PPP`, the
  reader goes back and the standard levels are read from there.
- If any of the three groups (`99PPP`, `TTTDD`, `ddfff`) is missing, is `51515`, or starts with
  `77` or `88`, nothing more of the report is decoded.
- v1.2 read the surface like any other level, wherever it stood.

### 5.2 Which levels have a wind group: `_top_wind_pressure` (`RU_MLVL`)

A level has a wind group when its pressure is at or above this value:

| `Id` | Part A | Part C |
| :--- | :--- | :--- |
| `/` | none (2000) | none (2000) |
| 1–9 | `Id × 100` hPa | `Id × 10` hPa, but `1` → all levels (0) |
| 0 | 1000 hPa | all levels (0) |

v1.2 used a table per part and assumed winds present for an unknown figure.

### 5.3 Standard levels: `_mandatory_levels`, `_mandatory` (`RU_MLVL`, `RU_MAND`)

v1.2 took any group starting with a level indicator, in any order. 2.0 expects the levels **in
the order of the code form**:

```
Part A: 00 92 85 70 50 40 30 25 20 15 10
Part C: 70 50 30 20 10 07 05 03 02 01
```

For the expected level `level` (0 to 10):

1. Read a field. End of report, `51515`, or a field starting with `66`, `77`, `88`: stop. For
   `66`/`77`/`88` the field is given back to the tropopause reader.
2. If the field is `85…` while `92` is expected, 925 hPa is absent: expect `85`.
3. If the field starts with the expected `PP`, decode the level (below). The level is stored when
   it has a pressure **and a height**. A level whose height is `///` is dropped.
4. If the level was good, expect the next one. Otherwise **search**: for the current field and
   each following one, find a level `i ≥ level` whose `PP` matches *and* whose successor `PP`
   stands where it should (3 fields on when the level has a wind group, 2 otherwise). When found,
   go on from there. The search gives up after `MAXSKP = 10` skipped fields in total.

Consequence: a level after a gap at the very end of a cut report has no successor to confirm it
and is not found. In a Part C, the last level (1 hPa) cannot be found by the search.

One level (`RU_MAND`): `PPhhh`, then `TTTDD`, then `ddfff` if the level has a wind group.

- The temperature and wind fields must be 5 to 7 characters long, else the level is invalid.
- End of the report at the temperature or wind position ends the levels (a level with a height
  already read is still stored).
- `51515` at the **wind** position ends the report. At the **temperature** position it is a
  temperature (section 9, deviation 2).
- A height that is a multiple of 1000 m with temperature and wind all missing is set missing (a
  height of "zero" with nothing else is no data), and the level is then dropped.

### 5.4 Tropopause: `_tropopauses` (`RU_MTRP`)

v1.2 wrote the tropopause as text rows. 2.0 makes numeric levels of type `Tropopause`.

- Fields are skipped until one starts with `88`. `66`, `77`, `51515` or the end stop the search.
- `88999`: no tropopause; the search ends.
- `88PPP TTTDD ddfff`, always with a wind group. `PPP` in hPa in Part A, tenths in Part C.
- A wind of 0° and speed 0 is taken as missing.
- Several tropopauses are allowed.

### 5.5 Maximum wind: `_max_winds` (`RU_MMXW`)

- Fields are skipped until one starts with `77` or `66`. `51515` or the end stop the search.
- `77999` ends the search; `66999` is skipped.
- `77PPP ddfff` (or `66PPP`); `PPP` in hPa in Part A, tenths in Part C. A level **without a wind
  is dropped**.
- Addition to GEMPAK: a following `4vbvbvava` gives the shear below and above, in m/s.

## 6. Parts B and D

### 6.1 Sections

`_significant` reads `nnPPP TTTDD` levels, then, after `21212`, `nnPPP ddfff` levels. The
temperature section ends at `21212`, `41414`, `51515` or the end; the wind section at `41414`,
`51515` or the end. `21212` is tested only on a field read where a level group is expected
(section 9, deviation 1).

### 6.2 The sequence of `nn` (`RU_STMP`, `RU_PWND`)

v1.2 accepted any `00` or repeated digit, in any order, and kept levels with missing values.
2.0 follows the expected number `levexp`: it starts at 0 in Part B (the surface) and at 1 in
Part D, and after 9 comes 1.

```
for each field (shorter than 5: skipped)
    (level, pres) = decode_sig_level(field)
    if level == levexp:                      take it;  skip = false
    else if level <= 0:                      reject;   undo if skip;  skip = false;  levexp = -2
    else if nothing stored or pres < last:   take it;  undo if skip;  skip = true;   levexp = level
    else:                                    reject;   undo if skip;  skip = false;  levexp = -2
    if taken:
        read the value field (TTTDD or ddfff)
        if it decodes (temperature present; wind with direction and speed):
            store (pres, value) after the last stored level
        else:
            skip = false                     # the level is not kept
        levexp = levexp + 1, 1 after 9
    if nothing is stored: skip = false
```

- "undo if skip" removes the last stored level: a level taken out of sequence is dropped again
  when the level after it does not follow it.
- After a rejection `levexp = -2`, so only a level with a lower pressure than the last one can
  restart the sequence.
- **A pressure that does not decrease is rejected** (v1.2 accepted it).
- **A level whose temperature (or wind) is missing is not stored** (v1.2 kept an empty row).
- Part B keeps the first slot for the surface (`nn = 00`): a first level that is not `00` goes to
  the second slot and the surface stays empty. Keep this layout: "nothing stored" and "the last
  pressure" depend on it (an empty surface slot counts as a pressure of −9999).
- In the wind section, `41414`, `51515` or the end at the value position ends the section.

### 6.3 Layers of missing data (addition to GEMPAK)

`nn///` followed by `/////` marks a layer without data. GEMPAK ignores it, and then treats the
level that closes the layer as out of sequence.

- The marker is consumed with its `/////`; if its `nn` is the expected one, `levexp` advances.
- The layer runs from the last stored level to the next stored level, and is recorded as
  `MissingLayer(kind, bottom_hpa, top_hpa)` when the top pressure is lower.
- The merge does not interpolate inside such a layer.

## 7. PILOT, ship and dropsonde (new in 2.0)

### 7.1 PILOT A and C: `_pilot_mandatory` (`RU_PPAA`, `RU_PPCC`, `RU_PPMW`)

`44nPP` or `55nPP` followed by `n` winds (1 to 3) for `n` consecutive standard levels starting at
`PP`, in the order of 5.3. A wind is stored only at a pressure lower than the last stored one.
Any other group ends the section.

### 7.2 PILOT B and D: `_height_winds` (`RU_SIGW`, `RU_WHGT`)

- `9tnu1u2u3` (also `8…`, and `1…` for 100000 ft and more) followed by up to three winds: each
  height is `(tn × 10 + u) × 1000` feet, converted with 0.3048. A `/` among the `u` leaves that
  wind out; trailing `/` shorten the group.
- These levels have a height and no pressure.
- After `21212`, winds on pressure levels as in 6.2. For PILOT the report is cut at the first
  field starting with `21212`.

### 7.3 Dropsonde identifier: `_dropsonde_id` (`RU_DRP1`)

After `61616`, the aircraft group (5 characters): `NOAAn`, `NASAn`, `AFnnn`, `NAnnn` or `NnnnF`.
Identifier = `observation × 100000 + hour × 1000 + aircraft number`, with the observation number
from the 1 or 2 digits after `OB` (99 without one). A dropsonde Part A or B without it raises
`DecodeError`. In `decode_height`, the 925 hPa rule `+1000` is not applied to a dropsonde.

Not ported: `RU_DRP2` and the `iwndht` cut-off (they re-read the sounding file).

## 8. Merge (`merge.py`): not from GEMPAK

`dcuair` stores the parts unmerged; the merge is done later by GEMPAK's `MR_` library, which is
not in the extract (there is no `rumerg.f`). The merge of 2.0 keeps the method of v1.2, rewritten
on the model, with these changes:

| Topic | v1.2 | 2.0 |
| :--- | :--- | :--- |
| Choice of report | Last one per part | `RU_DUPE` rule: the first per part, replaced only by a report from a bulletin whose `BBB` starts with `C`, `R` or `A`. NIL reports left out |
| Key | Pressure | Pressure rounded to 0.1 hPa |
| Precedence | Order of the parts | Standard levels and surface (A, C) → significant temperature → significant wind → PILOT standard levels → tropopauses → maximum winds. A value already there is never replaced; a wind is taken whole (direction and speed together) |
| Tropopause, maximum wind | Text only | Also levels of the profile at their pressure, with their reported wind |
| Extrapolated standard levels (35.2.2.4) | Added | **Removed**: no level is added that no report holds |
| Interpolation of T, Td, wind | Always | Optional (`interpolate`); filled fields are named in `derived` |
| Dew point | Filled alone | Filled only where the temperature is filled, and never above it |
| Station elevation | — | With a station table, a surface without a height takes the elevation |

Method, for the port:

- **Heights** (`compute_heights`): hypsometric equation between neighbouring levels, mean virtual
  temperature, `R = 287.05`, `g = 9.80665`; vapour pressure `6.112·exp(17.67·Td/(Td+243.5))`,
  `w = 0.622·e/(p−e)`, `Tv = T·(1+0.608·w)`. For this calculation only, a missing temperature or
  dew point is interpolated linearly in `ln p` (the nearest temperature outside the observed
  range). Upwards from each level with a height, then downwards from the lowest level that has
  one. Above the last temperature a height is computed only within 25 hPa and a quarter of the
  level's pressure. Heights are rounded to the metre.
- **Interpolation** (`interpolate_profile`): linear in `ln p` between observed levels, never
  outside them, never inside a missing layer of the same kind; the wind by its components `u`,
  `v`; direction rounded to the degree, 0 when the speed is under 0.05 m/s.
- **PILOT winds on heights** (`_place_height_winds`): given a pressure from the heights of the
  profile (`ln p` linear in height), marked as derived; those outside the heights of the profile
  are returned in `height_winds`.

## 9. Where 2.0 is not GEMPAK

Two deliberate deviations, both about *where* a marker is recognised:

1. **`21212`** starts the wind section only where a level group is expected. GEMPAK cuts the
   report at the first `21212` it finds, so a level at 21.2 °C with a depression of 1.2 °C turned
   the temperature levels after it into winds.
2. **`51515`** at the temperature position of a standard level is −51.5 °C with a depression of
   1.5 °C. GEMPAK ended the report there. At the wind position it still ends the report.

Additions that GEMPAK does not decode: the shear group (5.5), layers of missing data (6.3), and
the sections read by `sections.py`:

- **`31313`**: the last `31313` followed by `8GGgg`, directly or after `srrarasasa`. Gives the
  radiation correction, radiosonde type, tracking system and launch time. (`31313` alone is also
  a temperature of −31.3 °C; hence the test on what follows.)
- **`41414`** + `NhCLhCMCH`: the cloud group, in Part B only.
- **`51515`** onwards: kept as text in `raw_remarks`.

These sections are read from the report text after the levels and change no level.

The porting guide (`lib/gempak_fm_35_decoder_porting_guide.md`, kept locally) disagrees with the
Fortran in several places: surface pressure "in tenths", wind as `dddff` with 50 added to `dd`,
depressions 51–55 "invalid", heights at 250–100 hPa and 10 hPa, and files that do not exist
(`rumerg.f`, `rusigp.f`, `rutrop.f`, `rumaxw.f`). 2.0 follows the Fortran, which agrees with the
WMO Manual on Codes. Do not port from the guide.

## 10. API changes (Python)

**Kept:** `decode(ttaa, ttbb, ttcc, ttdd)` → `(df_main, df_special)`, and `decode_full` (now the
same function).

**New:** `iter_bulletins`, `iter_reports`, `parse_report`, `iter_decoded_reports`,
`merge_parts`, `merge_reports`, `decode_soundings`, `to_dataframes`, `load_station_table`; the
model types; `decode(..., wind_unit="m/s", interpolate=False)`.

**DataFrames:** `df_main` gains `Derived` (the columns of the row that were computed) and its
`Source` now tells `Surface`, `Tropopause` and `MaxWind` apart; `Extrapolated` no longer occurs.
An empty result has the usual columns. `df_special` is as before, built from the model.

**Removed:** `route_parts`, `split_bulletin`, `decode_temperature`,
`decode_dewpoint_depression`, `calculate_dewpoint`, `interpolate_data`, `calculate_geopotential`,
`parse_ttaa_ttcc`, `parse_ttbb_ttdd`, `merge_data`, and the old `decode_wind` and `decode_height`
of `decoder.py` (replaced by `groups.decode_wind(fld, knots)` and
`groups.decode_height(fld, above, drop)`, with other signatures and results). Also: the
`ValueError` for a message with fewer than two temperatures; decoding a message without its part
name and header; the CSV versions of Code tables 3931 and 0777; NumPy as a dependency.

## 11. Notes for the Rust crate

- **Port from `groups.py`, `bulletin.py`, `parts.py`, `sections.py`, `merge.py`, `stations.py`
  and `models.py`.** `decoder.py` is the pandas layer; the crate's output is `MergedSounding` (and
  `SoundingReport`).
- **Text is ASCII after cleaning**, so the field reader can work on bytes, and slices such as
  `fld[2..5]` are safe once the length is checked. Check lengths before slicing: Python slices
  never fail, and several rules rely on a short slice simply not matching.
- **`to_int`** accepts only ASCII digits (no sign, no blank); anything else is missing.
- **The reader is a cursor** with `pos`, `end`, `last_start` and `regional_at`. Look-ahead in 5.3
  uses a second cursor on the same text; several routines save `pos` and restore it.
- **Keep the control flow of 5.3 and 6.2 as it is.** These two loops hold the behaviour that is
  hardest to see from examples (the search after a bad level; taking and undoing an
  out-of-sequence level).
- **Types:** enums for `ReportPart`, `WindUnit`, `Platform`, `LevelType`; `Option<f64>` for every
  value of a level; `derived` as a set of field names or bit flags.
- **Errors:** one error type for the header. `iter_decoded_reports` logs such a report and goes
  on with the next.
- **Time:** the reference time is an argument; do not read the clock inside the decoder.
- **Rounding:** dew point and interpolated values to 0.1, heights to the metre, merged pressure
  key to 0.1 hPa, positions to 0.1°. Python's `round` rounds halves to even; the tests do not
  depend on that case, but a crate that must agree digit for digit should do the same.
- **Tests to carry over:** `tests/test_groups.py`, `test_bulletin.py`, `test_parts.py`,
  `test_merge.py` are pure model tests and translate directly. `tests/samples.py` holds a real
  four-part sounding (station 83746); `tests/demo.mt.txt` is the University of Wyoming listing
  used as an outside reference.

## 12. Test vectors

Group decoders, derived from the rules above (speeds as reported, before conversion to m/s):

| Group | Decoder | Result |
| :--- | :--- | :--- |
| `21212` | temperature | 21.2 °C, dew point 20.0 °C |
| `51515` | temperature | −51.5 °C, dew point −53.0 °C |
| `12356` | temperature | −12.3 °C, dew point −18.3 °C |
| `10051` | temperature | 10.0 °C, dew point 9.0 °C |
| `104//` | temperature | 10.4 °C, no dew point |
| `27620` | wind | 275°, 120 |
| `36010` | wind | 0°, 10 |
| `00005` | wind | 0°, 5 |
| `99005` | wind | none |
| `31313` | wind | none |
| `00500` | height, A | 1000 hPa, 500 m |
| `00520` | height, A | 1000 hPa, −20 m |
| `92100` | height, A | 925 hPa, 1100 m (100 m for a dropsonde) |
| `92750` | height, A | 925 hPa, 750 m |
| `85950` | height, A | 850 hPa, 950 m |
| `85450` | height, A | 850 hPa, 1450 m |
| `70500` | height, A | 700 hPa, 2500 m |
| `70050` | height, A | 700 hPa, 3050 m |
| `50570` | height, A | 500 hPa, 5700 m |
| `30940` | height, A | 300 hPa, 9400 m |
| `25060` | height, A | 250 hPa, 10600 m |
| `20200` | height, A | 200 hPa, 12000 m |
| `15390` | height, A | 150 hPa, 13900 m |
| `10640` | height, A | 100 hPa, 16400 m |
| `70860` | height, C | 70 hPa, 18600 m |
| `50060` | height, C | 50 hPa, 20600 m |
| `50990` | height, C | 50 hPa, 19900 m |
| `30380` | height, C | 30 hPa, 23800 m |
| `10110` | height, C | 10 hPa, 31100 m |
| `10990` | height, C | 10 hPa, 29900 m |
| `07340` | height, C | 7 hPa, 33400 m |
| `99012` | surface | 1012 hPa |
| `99985` | surface | 985 hPa |
| `00012` | `nnPPP`, B | level 0, 1012 hPa |
| `22850` | `nnPPP`, B | level 2, 850 hPa |
| `11950` | `nnPPP`, D | level 1, 95.0 hPa |
| `12850` | `nnPPP` | not a level |

Checks made on 2.0 against v1.2: the 24 real messages of station 83746 (11–13 November 2026) and
the demo sounding give the same levels and the same reported values; only tropopause and
maximum-wind levels differ, which now carry their reported wind instead of an interpolated one.

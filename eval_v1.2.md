# Evaluation of fm35_decoder v1.2

Reviewed on 2026-11-14 at commit `464dab3` (tag `v1.2`): `src/fm35_decoder/decoder.py` (1152 lines),
`tables.py` (383 lines), `tests/test_decode.py` (41 tests, all passing), the docs and the CI
workflows. Behaviour claims below were checked by running the code, including the 24 messages of
station 83746 in `lib/mensagens_sinotico_2026-11-13.txt`.

## Verdict

v1.2 is a correct and well-tested decoder for **one clean FM 35 report from one land station**.
Its group decoding follows the WMO Manual on Codes closely and handles several ambiguities that
the GEMPAK decoder gets wrong. Its weaknesses are structural: it has no notion of a bulletin, a
report header, a station or an observation time; it accepts groups wherever it finds them instead
of following the order of the code form; and the observed data, the interpolated data and the
computed data end up in the same DataFrame columns with nothing to tell them apart.

| Area | Rating | Summary |
| :--- | :--- | :--- |
| Group decoding (TTTDD, ddfff, PPhhh, nnPPP) | Good | WMO-faithful, table-driven, handles marker-like temperatures |
| Report structure (order, sections, `Id`) | Fair | `Id` honoured; level order and `nn` sequence are not checked |
| Bulletin and header handling | Poor | Header skipped, not decoded; no `NIL`, no multi-station bulletin |
| Data model and API | Fair | Two DataFrames; special levels are strings; no provenance |
| Derived data (interpolation, heights) | Fair | Sound physics, but mixed silently with observations |
| Code structure | Fair | One module, two 200-line parsing loops, `Dict[str, Any]` rows |
| Tests | Good | 41 focused tests; no real-data regression fixture |
| Scope | Narrow | No PILOT (FM 32), TEMP SHIP (FM 36), TEMP DROP (FM 37) |

## What v1.2 does well

- **Position decides, not the digits.** A group after `PPhhh` or `nnPPP` is the temperature even
  when it looks like a marker (`21212`, `31313`, `52525`, `66562`, `77161`). GEMPAK finds `21212`
  with a substring search and ends a report on a `51515` temperature.
- **`Id` (Code table 1734)** controls which standard levels carry a wind group, with a fallback
  for figures the table does not define.
- **Part C and D pressures in tenths of hPa**, for significant levels and for the 88/77/66 groups.
- **Wind groups**: the `+500` rule for 5° directions, variable wind (`dd` = 99) kept as a speed
  without direction, and the unit taken from `YY` (m/s or knots).
- **Layers of missing data** (`nn/// /////`) are recognised and never interpolated across.
- **Supplementary sections**: `31313` (radiation correction, sounding system, tracking, launch
  time), `41414` (clouds) and the `4vbvbvava` shear group are decoded with complete WMO tables.
- **Heights and interpolation** use ln(p), virtual temperature and the limits of Regulation
  35.2.2.4.
- **Tests** name the regulation or the case they cover and run in about a second.

## Findings

### 1. No bulletin, header, station or time (high)

- `parse_ttaa_ttcc` and `parse_ttbb_ttdd` skip `YYGGId` and `IIiii`. The station number, the day
  and the hour are never returned, so a decoded sounding cannot say what it is.
- A `NIL` report returns two empty DataFrames, the same as an empty string.
- A bulletin with two stations is merged into one profile:
  `decode("TTAA 61001 83746 … = TTAA 61001 83779 … =")` returns the 850 hPa level of one station
  and the surface of the other. `split_bulletin` keeps the last text of each part.
- The WMO abbreviated heading (`TTAAii CCCC YYGGgg BBB`), `SOH`/`ETX` framing and corrections
  (`COR`, `CCx`) are not read. Control characters happen to be harmless because of `str.split()`.
- `"TTCC" in message` (a substring test) decides the part before the header is seen.

### 2. Groups are accepted out of order (medium)

- In Parts A and C any group whose first two figures name a standard level starts a level,
  wherever it is. `… 50590 … 85607 … 00228 …` decodes to 500, 850 and 1000 hPa in that order with
  no warning. GEMPAK walks the levels in the order of the code form and resynchronises after a
  bad group.
- In Parts B and D `nn` only has to be `00`, `11`, …, `99`; its sequence and the decrease of
  pressure are not checked. `11915 … 22950 …` gives a level at 950 hPa above one at 915 hPa.
- A ten-character run of two groups (`0022819843`), which GEMPAK splits, is dropped: the 1000 hPa
  level disappears.

### 3. Height reconstruction is a nearest-neighbour heuristic (medium)

`decode_height` picks the candidate closest to a standard-atmosphere height. It agrees with
GEMPAK for ordinary values and differs at the edges:

| Group | v1.2 | GEMPAK `RU_HGHT` |
| :--- | ---: | ---: |
| `85950` | 1950 m | 950 m |
| `00500` | 0 m | 500 m |
| `70500` | 3500 m | 2500 m |
| `50990` (Part C) | 19900 m | 19900 m |

The table of standard heights also has to exist for every level, and a level missing from it
would silently compare against 0 m.

### 4. Observed, interpolated and computed values share columns (medium)

`df_main` fills temperature, dew point and wind between observed levels and computes every
missing height. `Source` names where the *level* came from (`Standard`, `SigTemp`, `SigWind`,
`Extrapolated`), not which values of the row were reported. The last sounding of the sample file
decodes to 114 rows: the 54 wind-only levels carry interpolated temperatures and the 44
temperature-only levels carry interpolated winds, and a user cannot tell them from reported ones. The surface height is back-computed (3 m for Galeão, station elevation
6 m) rather than taken from a station table.

### 5. Special levels are text (medium)

Tropopause and maximum wind are stored in `df_special` as strings (`"275/120kt"`, `"90.6hPa"`,
`"-77.1C"`). They are not numeric, not in the profile, and their unit follows the message while
`df_main` is always in knots.

### 6. A valid report can raise (low)

`decode` raises `ValueError` for a message with fewer than two temperatures (a surface-only
Part A). That is a legitimate, if short, report; the exception aborts a batch.

### 7. Code structure (low)

- One 1152-line module holds tables loading, group decoding, both parsers, merging, interpolation
  and hypsometry. The two parsers are `while` loops of about 200 lines with index arithmetic.
- Levels are `Dict[str, Any]`; the special entries are dictionaries with free-form keys
  (`Bottom`/`Top` only on some). There are no types for part, unit or level kind.
- pandas and NumPy are required to parse text. Each part becomes a DataFrame before merging:
  about 21 ms per four-part sounding, most of it DataFrame overhead.
- The `tables` argument is threaded through every function under the name `cloud_tables`.
- `load_wmo_tables` swallows every exception when reading a CSV table.

### 8. Tests and tooling (low)

- All fixtures are inline strings, mostly variations of one Campo Grande Part A. The Wyoming
  listing in `tests/demo.mt.txt` and the 24 real messages in `lib/` are not used by any test, and
  `lib/` is git-ignored, so CI cannot see them.
- `tests/demo.mt.py` is not a test and is not collected.
- No linter or type-checker configuration; CI runs pytest only.
- `python-publish.yml` publishes to PyPI on every GitHub release without running the tests first.

### 9. Scope

Only FM 35 TEMP Parts A–D from fixed land stations. PILOT (`PPAA`–`PPDD`), TEMP SHIP (`UUxx`) and
TEMP DROP (`XXxx`) are not decoded.

## Recommendations for 2.0

1. Decode the bulletin and the report header: heading, part, day, hour, wind unit, `Id`, station,
   `NIL`. Return one object per report and merge by station and time.
2. Follow the order of the code form as GEMPAK does (expected level, resynchronisation, expected
   `nn`, decreasing pressure), keeping the position rule of v1.2 for marker-like temperatures.
3. Use explicit height rules per level instead of the nearest standard-atmosphere candidate.
4. Give levels a type and keep reported values apart from interpolated and computed ones.
5. Keep tropopause and maximum wind as numeric levels.
6. Make the parser pure Python with typed data classes; build DataFrames only at the edge.
7. Add a real-data regression fixture to the tracked tests.
8. Add PILOT, SHIP and DROP parts, which the GEMPAK decoder already covers.

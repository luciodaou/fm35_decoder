import re
import os
import pandas as pd

# --- Decoding Helper Functions ---


def decode_temperature(ttt_str):
    """
    Decodes the TTT part (TaTaTa).
    Sign Rule: If the last digit is odd, the temperature is negative.
    Returns temperature in Celsius.
    """
    if not ttt_str or len(ttt_str) != 3:
        return None
    try:
        tt = int(ttt_str[:2])
        ta = int(ttt_str[2])
        temp_abs = tt + (ta / 10.0)
        return -temp_abs if ta % 2 != 0 else temp_abs
    except ValueError:
        return None


def decode_dewpoint_depression(dd_str):
    """
    Decodes the DD part (Dew Point Depression).
    00-50: tenths of degrees. 56-99: DD-50 degrees.
    Returns depression in Celsius.
    """
    if not dd_str or len(dd_str) != 2:
        return None
    try:
        if dd_str == "//":
            return None
        dd = int(dd_str)
        if dd <= 50:
            return dd / 10.0
        elif 56 <= dd <= 99:
            return float(dd - 50)
        return None
    except ValueError:
        return None


def decode_wind(dddff_str):
    """
    Decodes the dddff group (3 digits direction, 2 digits speed).
    Returns (direction, speed).
    """
    if not dddff_str or len(dddff_str) != 5:
        return None, None
    try:
        if "/////" in dddff_str:
            return None, None
        ddd = int(dddff_str[:3])
        ff = int(dddff_str[3:])
        return ddd, ff
    except ValueError:
        return None, None


def calculate_dewpoint(temp, depression):
    if temp is not None and depression is not None:
        return round(temp - depression, 1)
    return None


def load_wmo_tables(base_path):
    codes = {}
    tables = {
        "Nh": "Nh_2700.csv",
        "CL": "CL_0513.csv",
        "h": "h_1600.csv",
        "CM": "CM_0515.csv",
        "CH": "CH_0509.csv",
        "Sr": "Sr_3849.csv",
        "rara": "rara_3685.csv",
        "sasa": "sasa_3872.csv",
    }

    try:
        table_dir = os.path.join(base_path, "Table Codes")
        if not os.path.exists(table_dir):
            table_dir = os.path.join(os.getcwd(), "Table Codes")

        for key, filename in tables.items():
            path = os.path.join(table_dir, filename)
            if os.path.exists(path):
                try:
                    df_code = pd.read_csv(path, dtype=str)
                    codes[key] = df_code.set_index("Code")["Description"].to_dict()
                except Exception:
                    codes[key] = {}
            else:
                codes[key] = {}
    except Exception:
        return None
    return codes


def decode_cloud_group(group, tables):
    """
    Decodes 5-digit cloud group Nh CL h CM CH.
    Returns: list of dicts [{'Symbol':..., 'Subject': 'Cloud', 'Description':..., 'Value':...}]
    """
    if not tables or len(group) != 5:
        return [
            {
                "Symbol": "41414",
                "Subject": "Cloud",
                "Description": "Cloud Group",
                "Value": group,
            }
        ]

    nh, cl, h, cm, ch = group[0], group[1], group[2], group[3], group[4]
    results = []

    val_nh = tables.get("Nh", {}).get(nh, nh)
    results.append(
        {"Symbol": "Nh", "Subject": "Cloud", "Description": "Amount", "Value": val_nh}
    )

    val_cl = tables.get("CL", {}).get(cl, cl)
    results.append(
        {"Symbol": "CL", "Subject": "Cloud", "Description": "Low Type", "Value": val_cl}
    )

    val_h = tables.get("h", {}).get(h, h)
    results.append(
        {
            "Symbol": "h",
            "Subject": "Cloud",
            "Description": "Base Height",
            "Value": val_h,
        }
    )

    val_cm = tables.get("CM", {}).get(cm, cm)
    results.append(
        {"Symbol": "CM", "Subject": "Cloud", "Description": "Mid Type", "Value": val_cm}
    )

    val_ch = tables.get("CH", {}).get(ch, ch)
    results.append(
        {
            "Symbol": "CH",
            "Subject": "Cloud",
            "Description": "High Type",
            "Value": val_ch,
        }
    )

    return results


def decode_31313_group(groups, start_index, tables):
    """
    Decodes 31313 group sequence.
    Returns: (list_of_dicts, new_index)
    """
    i = start_index
    results = []

    # Check next group: sr rara sasa (5 digits)
    if i + 1 < len(groups) and len(groups[i + 1]) == 5:
        grp = groups[i + 1]
        sr = grp[0]
        rara = grp[1:3]
        sasa = grp[3:5]

        results.append(
            {
                "Symbol": "sr",
                "Subject": "Solar/Inst",
                "Description": "Solar Corr",
                "Value": tables.get("Sr", {}).get(sr, sr),
            }
        )
        results.append(
            {
                "Symbol": "rara",
                "Subject": "Solar/Inst",
                "Description": "Sonde Type",
                "Value": tables.get("rara", {}).get(rara, rara),
            }
        )
        results.append(
            {
                "Symbol": "sasa",
                "Subject": "Solar/Inst",
                "Description": "Tracking",
                "Value": tables.get("sasa", {}).get(sasa, sasa),
            }
        )
        i += 1

    # Check next group: 8GGgg (Time)
    if i + 1 < len(groups) and groups[i + 1].startswith("8"):
        grp = groups[i + 1]
        if len(grp) == 5:
            gg_h = grp[1:3]
            gg_m = grp[3:5]
            results.append(
                {
                    "Symbol": "8GGgg",
                    "Subject": "Solar/Inst",
                    "Description": "Time",
                    "Value": f"{gg_h}:{gg_m}",
                }
            )
        i += 1

    # Check optional 9xxxx group
    if (
        i + 1 < len(groups)
        and groups[i + 1].startswith("9")
        and len(groups[i + 1]) == 5
    ):
        i += 1

    return results, i + 1


def decode_height(pressure, h_str):
    """
    Decodes geopotential height based on pressure level (hPa) and reported string.
    Rules:
    - P < 500 hPa: h_str is tens of standard geopotential meters.
    - P >= 500 hPa: h_str is whole standard geopotential meters.
    - Ambiguity/Truncation: Add thousands (for P>=500) or ten-thousands (for P<500)
      to match 'Standard Atmosphere' approximation.
    - Negative heights (P=1000 etc): If h_str > 500 for low levels, might be 500+|h|.
    """
    if not h_str or len(h_str) != 3:
        return None

    try:
        val_raw = int(h_str)
    except ValueError:
        return None

    # Approximate Standard Atmosphere Heights (m)
    std_h = {
        1000: 111,
        925: 762,
        850: 1457,
        700: 3012,
        500: 5574,
        400: 7185,
        300: 9164,
        250: 10363,
        200: 11784,
        150: 13608,
        100: 16180,
        70: 18440,
        50: 20580,
        30: 23850,
        20: 26500,
        10: 31050,
    }

    # 1. Determine Scale
    if pressure < 500:
        val = val_raw * 10
        step = 10000
    else:
        val = val_raw
        step = 1000  # Usually truncated at 3 digits -> mod 1000 or mod 10000?
        # For 850hPa (1500m), reported 5?? (3 digits).
        # If 1560 reported as 560 -> mod 1000.

    target = std_h.get(pressure, 0)

    # Heuristics
    candidates = []

    # Case A: Positive adders
    # Try adding k * step (0 to 5)
    for k in range(6):
        cand = val + k * step
        candidates.append(cand)

    # Case B: Negative (Only for P >= 500, specifically 1000)
    # Rule: 500 + abs(h). E.g. -100m -> abs(100)=100 -> 600 reported.
    # So if reported > 500, could be -ve.
    if pressure >= 500:
        if val_raw >= 500:
            # Interpreted as 500 + |h|
            abs_h = val_raw - 500
            cand = -abs_h
            candidates.append(cand)

    # Find candidate closest to target
    best_h = min(candidates, key=lambda x: abs(x - target))

    return best_h


# --- Parsing Logic ---


def clean_message(message):
    message = message.replace("=", "")
    return re.sub(r"\s+", " ", message).strip()


def parse_ttaa_ttcc(message, cloud_tables=None):
    levels_data = []
    special_data = []

    clean_msg = clean_message(message)
    groups = clean_msg.split(" ")

    standard_levels_ttaa = {
        "99": "Surface",
        "00": 1000,
        "92": 925,
        "85": 850,
        "70": 700,
        "50": 500,
        "40": 400,
        "30": 300,
        "25": 250,
        "20": 200,
        "15": 150,
        "10": 100,
    }
    standard_levels_ttcc = {
        "70": 70,
        "50": 50,
        "30": 30,
        "20": 20,
        "10": 10,
        "07": 7,
        "05": 5,
        "03": 3,
        "02": 2,
        "01": 1,
    }

    is_ttcc = "TTCC" in message
    standard_levels = standard_levels_ttcc if is_ttcc else standard_levels_ttaa

    i = 0
    while i < len(groups):
        g = groups[i]

        if re.match(r"^(TTAA|TTCC|TTBB|TTDD)$", g):
            i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            continue

        # Tropopause
        if g.startswith("88"):
            if g == "88999":
                i += 1
                continue
            try:
                p_code = g[2:]
                pressure = int(p_code) if len(p_code) == 3 else None

                temp_grp = groups[i + 1] if i + 1 < len(groups) else None
                wind_grp = groups[i + 2] if i + 2 < len(groups) else None

                t, d, wd, ws = None, None, None, None
                valid_t = False

                special_data.append(
                    {
                        "Symbol": "PtPtPt",
                        "Subject": "Tropopause",
                        "Description": "Pressure",
                        "Value": f"{pressure}hPa",
                    }
                )

                if temp_grp:
                    t = decode_temperature(temp_grp[:3])
                    d = decode_dewpoint_depression(temp_grp[3:])
                    if t is not None:
                        special_data.append(
                            {
                                "Symbol": "TtTtTt",
                                "Subject": "Tropopause",
                                "Description": "Temperature",
                                "Value": f"{t}C",
                            }
                        )
                        valid_t = True
                    if t is not None and d is not None:
                        dw = calculate_dewpoint(t, d)
                        special_data.append(
                            {
                                "Symbol": "DtDt",
                                "Subject": "Tropopause",
                                "Description": "Dewpoint",
                                "Value": f"{dw}C",
                            }
                        )

                if wind_grp:
                    wd, ws = decode_wind(wind_grp)
                    if wd is not None:
                        special_data.append(
                            {
                                "Symbol": "dtdtftft",
                                "Subject": "Tropopause",
                                "Description": "Wind",
                                "Value": f"{wd}/{ws}kt",
                            }
                        )

                i += 3
                continue
            except Exception:
                i += 1
                continue

        # Max Wind
        if g.startswith("77") or g.startswith("66"):
            if g in ["77999", "66999"]:
                i += 1
                continue
            try:
                p_code = g[2:]
                pressure = int(p_code)
                wind_grp = groups[i + 1] if i + 1 < len(groups) else None
                wd, ws = None, None

                if wind_grp and len(wind_grp) == 5:
                    try:
                        d_deg = int(wind_grp[:2]) * 10
                        s_kt = int(wind_grp[2:])
                        wd, ws = d_deg, s_kt
                    except ValueError:
                        pass

                special_data.append(
                    {
                        "Symbol": "PmPmPm",
                        "Subject": "Max Wind",
                        "Description": "Pressure",
                        "Value": f"{pressure}hPa",
                    }
                )
                if wd is not None:
                    special_data.append(
                        {
                            "Symbol": "dmdmfmfmfm",
                            "Subject": "Max Wind",
                            "Description": "Wind",
                            "Value": f"{wd}/{ws}kt",
                        }
                    )

                i_next = i + 2
                if (
                    i_next < len(groups)
                    and groups[i_next].startswith("4")
                    and len(groups[i_next]) == 5
                ):
                    shear_grp = groups[i_next]
                    vb = shear_grp[1:3]
                    va = shear_grp[3:5]
                    special_data.append(
                        {
                            "Symbol": "vbvb",
                            "Subject": "Max Wind",
                            "Description": "Shear Below",
                            "Value": f"{vb}kt",
                        }
                    )
                    special_data.append(
                        {
                            "Symbol": "vava",
                            "Subject": "Max Wind",
                            "Description": "Shear Above",
                            "Value": f"{va}kt",
                        }
                    )
                    i_next += 1

                i = i_next
                continue
            except Exception:
                i += 1
                continue

        if g == "31313":
            decoded_list, new_i = decode_31313_group(groups, i, cloud_tables)
            special_data.extend(decoded_list)
            i = new_i
            continue

        if g == "41414":
            if i + 1 < len(groups):
                decoded_list = decode_cloud_group(groups[i + 1], cloud_tables)
                special_data.extend(decoded_list)
                i += 2
            else:
                i += 1
            continue

        if g.startswith(
            (
                "51515",
                "52525",
                "53535",
                "54545",
                "55555",
                "56565",
                "57575",
                "58585",
                "59595",
                "21212",
            )
        ):
            i += 1
            continue

        if len(g) == 2 or (len(g) == 5 and g[:2] in standard_levels):
            pp = g[:2]
            pressure, height = None, None
            if pp == "99":
                try:
                    pressure = 1000 + int(g[2:]) if int(g[2:]) < 100 else int(g[2:])
                except:
                    pass
            elif pp in standard_levels and len(g) == 5:
                try:
                    pressure = standard_levels[pp]
                    h_code = g[2:]
                    height = decode_height(pressure, h_code)
                except:
                    pass

            if pressure is not None:
                t_group = groups[i + 1] if i + 1 < len(groups) else None
                w_group = groups[i + 2] if i + 2 < len(groups) else None
                dp = {"Pressure": float(pressure), "Source": "Standard"}
                if height is not None:
                    dp["Height"] = height

                valid = False
                if t_group and len(t_group) == 5:
                    t = decode_temperature(t_group[:3])
                    d = decode_dewpoint_depression(t_group[3:])
                    dp["Temp"] = t
                    dp["DewPoint"] = calculate_dewpoint(t, d)
                    valid = True
                if w_group and len(w_group) == 5:
                    wd, ws = decode_wind(w_group)
                    dp["WindDir"] = wd
                    dp["WindSpeed"] = ws
                    valid = True

                if valid:
                    levels_data.append(dp)
                    i += 3
                    continue
        i += 1
    return levels_data, special_data


def parse_ttbb_ttdd(message, cloud_tables=None):
    levels_data = []
    special_data = []
    clean_msg = clean_message(message)
    groups = clean_msg.split(" ")
    mode = "TEMP"
    i = 0
    while i < len(groups):
        g = groups[i]
        if re.match(r"^(TTBB|TTDD)$", g):
            i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            continue
        if g == "21212":
            mode = "WIND"
            i += 1
            continue

        if g == "31313":
            decoded_list, new_i = decode_31313_group(groups, i, cloud_tables)
            special_data.extend(decoded_list)
            i = new_i
            continue

        if g == "41414":
            if i + 1 < len(groups):
                decoded_list = decode_cloud_group(groups[i + 1], cloud_tables)
                special_data.extend(decoded_list)
                i += 2
            else:
                i += 1
            continue

        if g == "51515":
            i += 1
            continue

        if len(g) == 5 and g[:2].isdigit():
            nn = g[:2]
            try:
                ppp_part = int(g[2:])
                pressure = None
                if nn == "00":
                    pressure = 1000 + ppp_part if ppp_part < 100 else ppp_part
                else:
                    pressure = float(ppp_part)

                if mode == "TEMP":
                    t_group = groups[i + 1] if i + 1 < len(groups) else None
                    if t_group and len(t_group) == 5:
                        t = decode_temperature(t_group[:3])
                        d = decode_dewpoint_depression(t_group[3:])
                        levels_data.append(
                            {
                                "Pressure": float(pressure),
                                "Temp": t,
                                "DewPoint": calculate_dewpoint(t, d),
                                "Source": "SigTemp",
                            }
                        )
                        i += 2
                        continue
                elif mode == "WIND":
                    w_group = groups[i + 1] if i + 1 < len(groups) else None
                    if w_group and len(w_group) == 5:
                        wd, ws = decode_wind(w_group)
                        levels_data.append(
                            {
                                "Pressure": float(pressure),
                                "WindDir": wd,
                                "WindSpeed": ws,
                                "Source": "SigWind",
                            }
                        )
                        i += 2
                        continue
            except:
                pass
        i += 1
    return levels_data, special_data


def merge_data(df_list):
    if not df_list:
        return pd.DataFrame()
    full_df = pd.concat(df_list, ignore_index=True)

    # Round Pressure to integer
    full_df["Pressure"] = full_df["Pressure"].round(0).astype(int)

    grouped = (
        full_df.groupby("Pressure")
        .agg(
            {
                "Height": "first",
                "Temp": "first",
                "DewPoint": "first",
                "WindDir": "first",
                "WindSpeed": "first",
                "Source": "first",
            }
        )
        .reset_index()
    )

    # Convert Height to Int64 (nullable int) to handle NaNs gracefully
    if "Height" in grouped.columns:
        grouped["Height"] = grouped["Height"].astype(float).round(0).astype("Int64")

    return grouped.sort_values(by="Pressure", ascending=False).reset_index(drop=True)


def decode_full(ttaa_msg, ttbb_msg, ttcc_msg, ttdd_msg):
    base_dir = (
        os.path.dirname(os.path.abspath(__file__))
        if "__file__" in globals()
        else os.getcwd()
    )
    cloud_tables = load_wmo_tables(base_dir)

    data_frames = []
    special_frames = []

    for msg, parser in [
        (ttaa_msg, parse_ttaa_ttcc),
        (ttcc_msg, parse_ttaa_ttcc),
        (ttbb_msg, parse_ttbb_ttdd),
        (ttdd_msg, parse_ttbb_ttdd),
    ]:
        if msg:
            lvls, spcls = parser(msg, cloud_tables=cloud_tables)
            if lvls:
                data_frames.append(pd.DataFrame(lvls))
            if spcls:
                special_frames.append(pd.DataFrame(spcls))

    df_main = merge_data(data_frames)
    df_special = (
        pd.concat(special_frames, ignore_index=True)
        if special_frames
        else pd.DataFrame()
    )

    if not df_main.empty:
        df_main = df_main.dropna(subset=["Temp", "DewPoint"])
    if not df_special.empty:
        # Reorder columns as requested
        if set(["Symbol", "Subject", "Description", "Value"]).issubset(
            df_special.columns
        ):
            df_special = df_special[["Symbol", "Subject", "Description", "Value"]]

        # Drop duplicates based on content
        df_special = df_special.drop_duplicates()

    return df_main, df_special


if __name__ == "__main__":
    ttaa_demo = "TTAA 73001 83779 99937 21626 17006 00151 ///// ///// 92834 20823 14509 85560 16203 07511 70196 08642 19506 50590 07157 26501 40761 16965 27015 30970 33368 24518 25095 44360 28026 20241 55558 29522 15419 66963 27538 10657 72366 31021 88110 75362 30027 77999 31313 42308 82336="
    ttbb_demo = "TTBB 73008 83779 00937 21626 11845 15804 22696 08640 33657 05446 44578 01508 55554 01947 66530 03756 77507 06745 88466 09164 99430 13357 11381 19570 22360 22968 33338 27127 44322 29928 55309 31370 66254 43550 77248 44764 88246 45159 99231 48568 11196 56557 22189 58363 33185 59157 44176 61162 55162 65758 66117 74362 77110 75362 88101 72965 21212 00937 17006 11895 11512 22839 07012 33828 09010 44562 18001 55402 27015 66342 25521 77326 26016 88296 24019 99277 26519 11263 25020 22248 28026 33212 30523 44191 28529 55178 30530 66163 29537 77153 27539 88134 29032 99126 27027 11119 30022 22106 29521 33101 31021 31313 42308 82336 41414 45501="
    ttcc_demo = "TTCC 73003 83779 70866 74966 28509 50066 67374 08522 30380 61181 09031 88999 77999 31313 42308 82336="
    ttdd_demo = "TTDD 7300/ 83779 11704 75365 22612 69171 33562 70370 44441 63778 55280 59383 21212 11972 28026 22926 28531 33810 24510 44789 29004 55748 31512 66721 29017 77704 27513 88678 26504 99652 17011 11627 12019 22605 08517 33569 08012 44555 10009 55542 13513 66511 09022 77476 07014 88458 08507 99435 12012 11415 07013 22400 10014 33382 07514 44368 09523 55345 08514 66328 10021 77295 09534 88280 10525 31313 42308 82336="

    df, df2 = decode_full(ttaa_demo, ttbb_demo, ttcc_demo, ttdd_demo)

    # df2 Sorting
    mask = df2["Subject"] == "Cloud"
    df2.loc[mask] = df2.loc[mask].sort_values("Description").values

    print("\n=== Main Level DataFrame (df) ===")
    # Omit Source column
    print(df.drop(columns=["Source"], errors="ignore").to_string(index=False))

    print("\n=== Special Data DataFrame (df2) ===")
    print(df2.to_string(index=False))

    print(f"\nTotal levels found: {len(df)}")

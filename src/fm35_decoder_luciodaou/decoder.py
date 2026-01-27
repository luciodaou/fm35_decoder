import re
import os
import pandas as pd
import numpy as np
from importlib import resources

# --- Decoding Helper Functions ---


def decode_temperature(ttt_str, tables=None):
    """
    Decodes the TTT part (TaTaTa).
    Uses WMO Code Table 3931 for tenths and sign.
    Returns temperature in Celsius.
    """
    if not ttt_str or len(ttt_str) != 3:
        return None
    try:
        tt = int(ttt_str[:2])
        ta_code = ttt_str[2]  # Code for tenths/sign (as string)

        if not tables or "T_3931" not in tables:
            # Fallback to old logic if table not loaded
            ta = int(ta_code)
            temp_abs = tt + (ta / 10.0)
            return -temp_abs if ta % 2 != 0 else temp_abs

        t_table = tables.get("T_3931", {})
        entry = t_table.get(ta_code)

        if entry:
            sign = entry.get("Sign", "+")
            tenths = float(entry.get("TenthsValue", 0.0))

            # TenthsValue in CSV is signed (e.g., -0.2), or use sign column
            # Logic: Temp = Sign * (TT + Tenths)

            val = float(tt) + abs(tenths)
            return -val if sign == "-" else val

        return None
    except ValueError:
        return None


def decode_dewpoint_depression(dd_str, tables=None):
    """
    Decodes the DD part (Dew Point Depression).
    Uses WMO Code Table 0777.
    Returns depression in Celsius.
    """
    if not dd_str or len(dd_str) != 2:
        return None
    try:
        if dd_str == "//":
            return None

        if tables and "D_0777" in tables:
            d_table = tables.get("D_0777", {})
            entry = d_table.get(dd_str)
            if entry:
                val = entry.get("Value")
                if pd.isna(val) or val == "":
                    return None
                return float(val)

        # Fallback
        dd = int(dd_str)
        if dd <= 50:
            return dd / 10.0
        elif 56 <= dd <= 99:
            return float(dd - 50)
        return None
    except ValueError:
        return None


def decode_wind(dff_str):
    """
    Decodes wind group in WMO format (ddfff).
    dd: Direction in tens of degrees.
    fff: Speed + (units digit of direction) * 100.

    Rule:
    1. Extract fff.
    2. If fff >= 500:
       Direction ends in 5.
       Speed = fff - 500.
    3. If fff < 500:
       Direction ends in 0.
       Speed = fff.

    Direction = dd * 10 + (5|0).
    """
    if not dff_str or len(dff_str) != 5:
        return None, None
    try:
        if "/////" in dff_str:
            return None, None

        dd = int(dff_str[:2])
        fff = int(dff_str[2:])

        # Direction Range Validation: 00-36 or 99 (Variable)
        if not (0 <= dd <= 36 or dd == 99):
            return None, None

        direction_unit = 0
        speed = fff

        if fff >= 500:
            direction_unit = 5
            speed = fff - 500

        direction = dd * 10 + direction_unit

        # Determine strict WMO speed unit? Usually knots for upper air.
        return direction, speed
    except ValueError:
        return None, None


def calculate_dewpoint(temp, depression):
    if temp is not None and depression is not None:
        return round(temp - depression, 1)
    return None


def load_wmo_tables(base_path=None):
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
        "T_3931": "T_3931.csv",
        "D_0777": "D_0777.csv",
    }

    try:
        # standard way to access package data
        with resources.path("fm35_decoder.table_codes", "") as table_dir:
            for key, filename in tables.items():
                path = os.path.join(table_dir, filename)
                if os.path.exists(path):
                    try:
                        df_code = pd.read_csv(path, dtype=str)
                        if "Code" in df_code.columns:
                            if key in ["T_3931", "D_0777"]:
                                codes[key] = df_code.set_index("Code").to_dict(
                                    orient="index"
                                )
                            else:
                                codes[key] = df_code.set_index("Code")[
                                    "Description"
                                ].to_dict()
                    except Exception:
                        codes[key] = {}
                else:
                    codes[key] = {}
    except Exception:
        # Fallback for local development if not installed as a package
        current_dir = os.path.dirname(os.path.abspath(__file__))
        table_dir = os.path.join(current_dir, "table_codes")
        if not os.path.exists(table_dir):
            return None

        for key, filename in tables.items():
            path = os.path.join(table_dir, filename)
            if os.path.exists(path):
                try:
                    df_code = pd.read_csv(path, dtype=str)
                    if "Code" in df_code.columns:
                        if key in ["T_3931", "D_0777"]:
                            codes[key] = df_code.set_index("Code").to_dict(
                                orient="index"
                            )
                        else:
                            codes[key] = df_code.set_index("Code")[
                                "Description"
                            ].to_dict()
                except Exception:
                    codes[key] = {}
            else:
                codes[key] = {}
    return codes


def interpolate_data(df):
    """
    Interpolates missing Temperature, DewPoint, and Wind data vertically.
    - Temperature/DewPoint: Linear interpolation in Log-Pressure.
    - Wind: Vector interpolation (U/V components) in Log-Pressure.
    """
    if df.empty or "Pressure" not in df.columns:
        return df

    # Work on a copy to avoid side effects
    df = df.copy()

    # Ensure sorted by Pressure Descending (Surface -> Top)
    # But for interpolation, monotonic increasing or decreasing index is needed.
    # Log(P) is monotonic.
    df = df.sort_values("Pressure", ascending=False).reset_index(drop=True)

    # Calculate Log-Pressure (Natural Log)
    # Avoid log(0)
    df["log_p"] = np.log(df["Pressure"].replace(0, np.nan))

    # set index to log_p for interpolation
    # Note: log_p is descending (Surface=high P, Top=low P).
    # interpolate() works on index.
    df = df.set_index("log_p")

    # --- Temperature Interpolation ---
    # Linear interpolation in Log-P space
    cols_to_interp = ["Temp", "DewPoint"]
    for col in cols_to_interp:
        if col in df.columns:
            # Ensure numeric to avoid TypeError: Series cannot interpolate with object dtype
            df[col] = pd.to_numeric(df[col], errors="coerce")
            # Mask for original NaNs to round only them (optional, but cleaner)
            mask = df[col].isna()
            df[col] = df[col].interpolate(method="index")
            df.loc[mask, col] = df.loc[mask, col].round(1)

    # --- Wind Interpolation (Vector) ---
    if "WindSpeed" in df.columns and "WindDir" in df.columns:
        # Ensure numeric
        df["WindSpeed"] = pd.to_numeric(df["WindSpeed"], errors="coerce")
        df["WindDir"] = pd.to_numeric(df["WindDir"], errors="coerce")

        # Convert to U (Zonal) and V (Meridional)
        # meteo dir: 0/360=North, 90=East.
        # math dir: 0=East, 90=North.
        # u = -speed * sin(dir)
        # v = -speed * cos(dir)
        rads = np.radians(df["WindDir"])
        df["u"] = -df["WindSpeed"] * np.sin(rads)
        df["v"] = -df["WindSpeed"] * np.cos(rads)

        # Interpolate U and V
        df["u"] = df["u"].interpolate(method="index")
        df["v"] = df["v"].interpolate(method="index")

        # Reconstruct Speed and Direction
        # Speed = sqrt(u^2 + v^2)
        speed = np.sqrt(df["u"] ** 2 + df["v"] ** 2)

        # Dir = atan2(u, v)? No.
        # atan2(y, x) -> atan2(v, u)?
        # To convert back to meteo:
        # dir = (270 - degrees(atan2(v, u))) % 360
        degrees = np.degrees(np.arctan2(df["v"], df["u"]))
        direction = (270 - degrees) % 360

        # Fill missing values in original columns
        mask = df["WindSpeed"].isna() | df["WindDir"].isna()

        # Assign interpolated values
        df.loc[mask, "WindSpeed"] = speed[mask].round(1)
        df.loc[mask, "WindDir"] = direction[mask].round(0)

        # Clean up temporary columns
        df = df.drop(columns=["u", "v"])

    # Reset index and restore original sorting
    df = df.reset_index(drop=False)  # log_p becomes column
    df = df.drop(columns=["log_p"])

    return df


def calculate_geopotential(df):
    """
    Calculates missing Geopotential Height values using the Hypsometric Equation.
    Formula: Z2 = Z1 + (R * T_avg / g) * ln(P1 / P2)
    """
    if df.empty or "Pressure" not in df.columns or "Temp" not in df.columns:
        return df

    # Constants
    R = 287.05  # Specific gas constant for dry air (J/(kg·K))
    g = 9.80665  # Gravity (m/s^2)

    # Ensure sorted by pressure descending (Surface -> Top)
    df = df.sort_values("Pressure", ascending=False).reset_index(drop=True)

    # Work with a copy to avoid SettingWithCopy warnings and temporary columns
    # Ensure Temp is numeric
    temp_numeric = pd.to_numeric(df["Temp"], errors="coerce")
    df["Temp_K"] = temp_numeric + 273.15

    # Interpolate missing temperatures for calculation (linear in log-P would be better, but linear is ok)
    if df["Temp_K"].isnull().any():
        df["Temp_K"] = df["Temp_K"].interpolate(method="linear", limit_direction="both")

    # 1. Forward Pass (Surface -> Top): Fill NaNs using valid level below
    # We iterate manually because each step depends on the potentially calculated prev step
    for i in range(1, len(df)):
        if pd.isna(df.at[i, "Height"]) and not pd.isna(df.at[i - 1, "Height"]):
            try:
                p1 = df.at[i - 1, "Pressure"]  # Lower altitude (higher P)
                z1 = df.at[i - 1, "Height"]
                t1 = df.at[i - 1, "Temp_K"]

                p2 = df.at[i, "Pressure"]  # Higher altitude (lower P)
                t2 = df.at[i, "Temp_K"]

                if p2 <= 0:
                    continue  # Avoid log domain error

                avg_t = (t1 + t2) / 2
                # Hypsometric: Z2 - Z1 = (R * T / g) * ln(P1/P2)
                dz = (R * avg_t / g) * np.log(p1 / p2)

                df.at[i, "Height"] = round(z1 + dz)
            except Exception:
                pass

    # 2. Backward Pass (Top -> Surface): Fill NaNs at bottom using valid level above
    # Useful if surface height is missing but 1000hPa or 925hPa is known
    first_valid = df["Height"].first_valid_index()
    if first_valid is not None and first_valid > 0:
        for i in range(first_valid - 1, -1, -1):
            if pd.isna(df.at[i, "Height"]):
                try:
                    # p1 is "Upper" level (Lower Pressure, index i+1)
                    p1 = df.at[i + 1, "Pressure"]
                    z1 = df.at[i + 1, "Height"]
                    t1 = df.at[i + 1, "Temp_K"]

                    # p2 is "Target" level (Higher Pressure, index i)
                    p2 = df.at[i, "Pressure"]
                    t2 = df.at[i, "Temp_K"]

                    if p1 <= 0:
                        continue

                    avg_t = (t1 + t2) / 2
                    # Z_target = Z_upper - DZ
                    # DZ = (R * T / g) * ln(P_target / P_upper)
                    dz = (R * avg_t / g) * np.log(p2 / p1)

                    df.at[i, "Height"] = round(z1 - dz)
                except Exception:
                    pass

    # 3. WMO Extrapolation Rule 35.2.2.4 (Upward to standard levels)
    # Check if we can extrapolate to the next standard level above the top
    standard_levels = [
        1000,
        925,
        850,
        700,
        500,
        400,
        300,
        250,
        200,
        150,
        100,
        70,
        50,
        30,
        20,
        10,
    ]

    # Get current top of sounding (lowest pressure with valid Data)
    # We rely on 'Temp_K' being present (interpolated) and 'Height' being calculated
    # Find the row with the lowest pressure that has valid Temp and Height
    valid_df = df.dropna(subset=["Height", "Temp_K"])
    if not valid_df.empty:
        top_row = valid_df.iloc[-1]  # Sorted descending by pressure, so last is top
        p_min = top_row["Pressure"]
        t_min = top_row["Temp_K"]
        z_min = top_row["Height"]

        # Identify target standard levels that are slightly above p_min
        # Filter standard levels < p_min
        targets = [sl for sl in standard_levels if sl < p_min]

        new_rows = []

        for p_target in targets:
            delta_p = p_min - p_target

            # Criterion a: Delta P <= 25 hPa AND Delta P <= 0.25 * P_target
            if delta_p <= 25 and delta_p <= 0.25 * p_target:
                try:
                    # Criterion b: Use points at P_min and P_base (P_min + Delta_P)
                    p_base = p_min + delta_p

                    # Interpolate Temp at p_base from existing profile
                    # Linear interpolation in log(P) for Temperature
                    # We need the full profile arrays
                    all_p = df["Pressure"].values
                    all_t = df["Temp_K"].values

                    # Sort by P ascending for np.interp (Standard atmosphere decreases P with height,
                    # but interpolation expects increasing x usually, or handled correctly)
                    # Let's use log(P)
                    log_p = np.log(all_p)
                    log_p_base = np.log(p_base)

                    # Ensure x is increasing for interp
                    # all_p is currently Descending (1000 -> 100)
                    # log_p is Descending (6.9 -> 4.6)
                    # Flip for interpolation
                    t_base = np.interp(log_p_base, log_p[::-1], all_t[::-1])

                    # Extrapolate T to P_target
                    # Slope m = (T_min - T_base) / (ln(P_min) - ln(P_base))
                    # T_target = T_min + m * (ln(P_target) - ln(P_min))
                    log_p_min = np.log(p_min)
                    log_p_target = np.log(p_target)

                    # Prevent division by zero if delta_p is tiny (though criteria imply it exists)
                    if abs(log_p_min - log_p_base) < 1e-6:
                        t_target = t_min
                    else:
                        slope = (t_min - t_base) / (log_p_min - log_p_base)
                        t_target = t_min + slope * (log_p_target - log_p_min)

                    avg_t = (t_min + t_target) / 2

                    # Hypsometric: Z_target = Z_min + (R * T_avg / g) * ln(P_min / P_target)
                    dz = (R * avg_t / g) * np.log(p_min / p_target)
                    z_target = z_min + dz

                    new_rows.append(
                        {
                            "Pressure": int(p_target),
                            "Height": round(z_target),
                            "Temp": round(t_target - 273.15, 1),
                            "DewPoint": None,  # Cannot reliably extrapolate moisture
                            "Source": "Extrapolated",
                        }
                    )

                    # Update p_min/z_min for next step?
                    # Rule says "extrapolate a sounding", implies from the *actual* sounding top.
                    # So we don't daisy chain. We stop after one or handle independent targets?
                    # "provided the extrapolation does not extend through a pressure interval exceeding 25 hPa"
                    # This implies valid only for the immediate vicinity of the sounding top.
                    # Usually only one standard level fits this tight window.

                except Exception:
                    pass

        if new_rows:
            # Append new extrapolated rows
            df_ext = pd.DataFrame(new_rows)
            df = pd.concat([df, df_ext], ignore_index=True)
            df = df.sort_values("Pressure", ascending=False).reset_index(drop=True)

    # Drop temp column
    df.drop(columns=["Temp_K"], inplace=True)

    return df


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
    if pressure <= 500:
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

                special_data.append(
                    {
                        "Symbol": "PtPtPt",
                        "Subject": "Tropopause",
                        "Description": "Pressure",
                        "Value": f"{pressure}hPa",
                    }
                )

                if temp_grp:
                    t = decode_temperature(temp_grp[:3], tables=cloud_tables)
                    d = decode_dewpoint_depression(temp_grp[3:], tables=cloud_tables)
                    if t is not None:
                        special_data.append(
                            {
                                "Symbol": "TtTtTt",
                                "Subject": "Tropopause",
                                "Description": "Temperature",
                                "Value": f"{t}C",
                            }
                        )
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
                except (ValueError, TypeError):
                    pass
            elif pp in standard_levels and len(g) == 5:
                try:
                    pressure = standard_levels[pp]
                    h_code = g[2:]
                    height = decode_height(pressure, h_code)
                except (ValueError, TypeError, Exception):
                    pass

            if pressure is not None:
                t_group = groups[i + 1] if i + 1 < len(groups) else None
                w_group = groups[i + 2] if i + 2 < len(groups) else None
                dp = {"Pressure": float(pressure), "Source": "Standard"}
                if height is not None:
                    dp["Height"] = height

                valid = False
                indicators = ("88", "77", "66", "51515", "31313", "41414")
                if (
                    t_group
                    and len(t_group) == 5
                    and not t_group.startswith(indicators)
                ):
                    t = decode_temperature(t_group[:3], tables=cloud_tables)
                    d = decode_dewpoint_depression(t_group[3:], tables=cloud_tables)
                    dp["Temp"] = t
                    dp["DewPoint"] = calculate_dewpoint(t, d)
                    valid = True
                if (
                    w_group
                    and len(w_group) == 5
                    and not w_group.startswith(indicators)
                ):
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
    is_ttdd = "TTDD" in message  # Simple check, or track via group iteration
    last_nn = None  # Sequence tracking for intruder detection

    i = 0
    while i < len(groups):
        g = groups[i]

        if re.match(r"^(TTBB|TTDD)$", g):
            if g == "TTDD":
                is_ttdd = True
            elif g == "TTBB":
                is_ttdd = False

            i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            continue
        if g == "21212":
            mode = "WIND"
            last_nn = None  # Reset sequence counter for new section
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

            # --- Strict Sequence Validation ---
            is_valid_level = False

            if last_nn is None:
                # Restrict start to 00 or 11 to filter out header noise
                try:
                    n_val = int(nn)
                    if n_val == 0 or n_val == 11:
                        is_valid_level = True
                    else:
                        pass
                except (ValueError, IndexError):
                    pass
            else:
                try:
                    ln = int(last_nn)
                    # strict next step
                    if ln == 0:
                        exp = 11
                    elif ln == 99:
                        exp = 11
                    else:
                        exp = ln + 11

                    try:
                        n_val = int(nn)
                        if n_val == exp:
                            is_valid_level = True
                        else:
                            pass
                    except (ValueError, IndexError):
                        pass
                except (ValueError, IndexError):
                    pass

            if not is_valid_level:
                # Treat as intruder/noise.
                i += 1
                continue

            last_nn = nn
            # ----------------------------------

            try:
                ppp_part = int(g[2:])
                pressure = None
                if nn == "00":
                    pressure = 1000 + ppp_part if ppp_part < 100 else ppp_part
                else:
                    pressure = float(ppp_part)

                # If TTDD, pressure is in tenths of hPa
                if is_ttdd:
                    pressure = pressure / 10.0

                if mode == "TEMP":
                    t_group = groups[i + 1] if i + 1 < len(groups) else None
                    if t_group and len(t_group) == 5 and t_group != "21212":
                        t = decode_temperature(t_group[:3], tables=cloud_tables)
                        d = decode_dewpoint_depression(t_group[3:], tables=cloud_tables)
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
            except (ValueError, IndexError):
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
    cloud_tables = load_wmo_tables()

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
    df_main = interpolate_data(df_main)
    df_main = calculate_geopotential(df_main)
    df_special = (
        pd.concat(special_frames, ignore_index=True)
        if special_frames
        else pd.DataFrame()
    )

    # Validating and sorting data
    if not df_special.empty:
        # Reorder columns as requested
        if set(["Symbol", "Subject", "Description", "Value"]).issubset(
            df_special.columns
        ):
            df_special = df_special[["Symbol", "Subject", "Description", "Value"]]

        # Drop duplicates based on content
        df_special = df_special.drop_duplicates()

        # Sort Special Data (Cloud groups specifically)
        mask = df_special["Subject"] == "Cloud"
        if mask.any():
            order = {"h": 0, "Nh": 1, "CL": 2, "CM": 3, "CH": 4}
            # Only sort the Cloud subject rows
            clouds = df_special[mask].sort_values(
                by="Symbol", key=lambda col: col.map(order)
            )
            others = df_special[~mask]
            df_special = pd.concat([clouds, others], ignore_index=True)

    return df_main, df_special


def decode(ttaa, ttbb, ttcc, ttdd):
    """
    Exposed function for external scripts.
    Returns (df_main, df_special)
    """
    return decode_full(ttaa, ttbb, ttcc, ttdd)


# This file is intended to be used as a module.
# Use decode(ttaa, ttbb, ttcc, ttdd) to process meteorological data.

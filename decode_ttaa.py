import sys
import re
import pandas as pd

# ... [keep existing decode functions: decode_temperature, decode_dewpoint_depression, decode_wind, decode_ttaa] ...

def decode_temperature(ttt_str):
    """
    Decodes the TTT part (TaTaTa).
    Sign Rule: If the last digit is odd, the temperature is negative.
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
    """
    if not dd_str or len(dd_str) != 2:
        return None
    try:
        dd = int(dd_str)
        if dd <= 50: return dd / 10.0
        elif 56 <= dd <= 99: return float(dd - 50)
        return None
    except ValueError:
        return None

def decode_wind(dddff_str):
    """
    Decodes the dddff group (3 digits direction, 2 digits speed).
    """
    if not dddff_str or len(dddff_str) != 5:
        return None, None
    try:
        ddd = int(dddff_str[:3])
        ff = int(dddff_str[3:])
        return ddd, ff
    except ValueError:
        return None, None

def decode_ttaa(message):
    clean_msg = re.sub(r'\s+', ' ', message).strip()
    groups = clean_msg.split(' ')
    data = []
    
    # Standard Isobaric Surfaces
    standard_levels = {
        '00': 1000, '92': 925, '85': 850, '70': 700, 
        '50': 500, '40': 400, '30': 300, '25': 250, 
        '20': 200, '15': 150, '10': 100
    }
    
    i = 0
    while i < len(groups):
        g = groups[i]
        
        # Skip header and known auxiliary groups
        if 'TTAA' in g or g.startswith(('88', '77', '66', '31313', '41414', '51515')):
            if 'TTAA' in g:
                 i += 3 # Skip TTAA YYGGi IIiii
            else:
                 i += 1
            continue
            
        if len(g) == 5 and g[:2].isdigit():
            pp = g[:2]
            pressure = None
            
            if pp == '99': # Surface
                try:
                    ppp = int(g[2:])
                    pressure = 1000 + ppp if ppp < 100 else ppp
                except:
                    pass
            elif pp in standard_levels:
                pressure = standard_levels[pp]
            
            if pressure and i + 2 < len(groups):
                tttdd = groups[i+1]
                dddff = groups[i+2]
                
                if len(tttdd) == 5 and len(dddff) == 5:
                    air_temp = decode_temperature(tttdd[:3])
                    dep = decode_dewpoint_depression(tttdd[3:])
                    dew_temp = round(air_temp - dep, 1) if air_temp is not None and dep is not None else None
                    wdir, wspd = decode_wind(dddff)
                    
                    data.append({
                        'Pressure': float(pressure),
                        'Air Temperature (C)': air_temp,
                        'Dew Temperature (C)': dew_temp,
                        'Wind Direction (deg)': wdir,
                        'Wind Speed (kt)': wspd
                    })
                    i += 3
                    continue
        i += 1
        
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values(by='Pressure', ascending=False).set_index('Pressure')
    return df

if __name__ == "__main__":
    import sys
    import os
    
    message = None

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # Check if the argument is a file that exists
        if os.path.exists(arg) and os.path.isfile(arg):
            try:
                with open(arg, 'r') as f:
                    content = f.read()
                    match = re.search(r'(TTAA.*?=)', content, re.DOTALL)
                    if match:
                        message = match.group(1)
                    else:
                        print(f"No standard TTAA message pattern found in {arg}, using full file content.")
                        message = content
            except Exception as e:
                print(f"Error reading file: {e}")
                sys.exit(1)
        else:
            # Treat the argument as the message itself
            message = arg
    else:
        print("Please paste the TTAA message below (end with Ctrl+Z + Enter on Windows, or Ctrl+D on Linux/Mac):")
        try:
            message = sys.stdin.read()
        except KeyboardInterrupt:
            sys.exit(0)

    if not message or not message.strip():
        print("Error: No message provided.")
        sys.exit(1)

    # Clean up message if it contains the standard TTAA pattern
    match = re.search(r'(TTAA.*?=)', message, re.DOTALL)
    if match:
        message = match.group(1)

    try:
        df = decode_ttaa(message)
        print("Decoded TTAA Table:")
        print(df)
    except Exception as e:
        print(f"Error during decoding: {e}")

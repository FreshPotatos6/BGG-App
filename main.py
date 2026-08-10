import json
import os
import re
from flask import Flask, render_template_string, jsonify, redirect, url_for

print("--- MAIN.PY IS STARTING UP ---")

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
    print("gspread is available.")
except ImportError:
    GSPREAD_AVAILABLE = False
    print("gspread is NOT available.")

JSON_FILENAME = "bgg_collection.json"
GAMES_CACHE = []

def clean_int(val, default=0):
    if val is None:
        return default
    val_str = str(val).strip()
    match = re.search(r'\d+', val_str)
    if match:
        try:
            return int(match.group())
        except ValueError:
            pass
    return default

def clean_float(val, default=0.0):
    if val is None:
        return default
    try:
        val_str = str(val).strip()
        val_str = re.sub(r'[^0-9.\-]', '', val_str)
        if val_str:
            return float(val_str)
    except ValueError:
        pass
    return default

def clean_title(raw_title):
    if not raw_title:
        return "Untitled Game"
    return re.sub(r'\s*\(\d{4}\)\s*$', '', str(raw_title)).strip()

def clean_award_name(raw_award):
    if not raw_award:
        return ""
    cleaned = re.sub(r'^\d{4}\s+', '', str(raw_award)).strip()
    cleaned = re.sub(r'\s+\(\d{4}\)$', '', cleaned).strip()
    return cleaned

def get_row_value(row, keys, default="Unknown"):
    for k in keys:
        if k in row and row[k] is not None and str(row[k]).strip() != "":
            return str(row[k]).strip()
    for r_key, r_val in row.items():
        clean_key = str(r_key).strip().lower()
        for k in keys:
            if clean_key == k.lower() and r_val is not None and str(r_val).strip() != "":
                return str(r_val).strip()
    return default

def parse_player_count_string(val, default_min=1, default_max=4):
    if not val:
        return default_min, default_max
    
    val_str = str(val).strip()
    numbers = re.findall(r'\d+', val_str)
    
    if len(numbers) >= 2:
        return int(numbers[0]), int(numbers[1])
    elif len(numbers) == 1:
        num = int(numbers[0])
        return num, num
    
    return default_min, default_max

def get_google_creds():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file"
    ]
    
    env_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if env_creds:
        try:
            cred_dict = json.loads(env_creds)
            return Credentials.from_service_account_info(cred_dict, scopes=scope)
        except Exception as e:
            print(f"Error parsing GOOGLE_CREDENTIALS_JSON env var: {e}")

    cred_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(cred_path):
        return Credentials.from_service_account_file(cred_path, scopes=scope)

    print("No valid credentials found.")
    return None

def generate_json_from_sheet():
    global GAMES_CACHE
    print("generate_json_from_sheet() was called.")
    if not GSPREAD_AVAILABLE:
        print("-> Aborting: Gspread not available.")
        return False

    creds = get_google_creds()
    if not creds:
        print("-> Aborting: Credentials not available.")
        return False
        
    try:
        print("Connecting to Google Sheets...")
        client = gspread.authorize(creds)
        
        spreadsheet = client.open_by_key("1epBOjwD8fSr-1DEy7FKG-t2ggheubK9Fhrul_Ui3Aqo")
        sheet = spreadsheet.worksheet("App")
        
        raw_data = sheet.get_all_records()
        print(f"Successfully fetched {len(raw_data)} rows from Google Sheet.")
        
        games_list = []
        for row in raw_data:
            is_exp_val = str(row.get("Is Expansion", "")).strip().lower()
            is_expansion = is_exp_val in ["yes", "true", "1"]

            parent_ref = str(row.get("Parent Game ID", row.get("Parent Game", ""))).strip()

            is_standalone_raw = str(row.get("Is Standalone", "")).strip().lower() in ["yes", "true", "1"]
            supports_one_off_raw = str(row.get("Supports One-Off", "")).strip().lower() in ["yes", "true", "1"]
            
            is_standalone = is_standalone_raw and supports_one_off_raw
            supports_one_off = supports_one_off_raw

            campaign_struct = str(row.get("Campaign Structure", "")).strip()
            game_mode = str(row.get("Game Mode", row.get("Game mode", "Competitive"))).strip()

            raw_play_time = str(row.get("Play Time", "")).strip()

            designer_val = get_row_value(row, ["Designers", "Designer", "Game Designer"], "Unknown")
            artist_val = get_row_value(row, ["Artists", "Artist"], "Unknown")
            publisher_val = get_row_value(row, ["Publisher", "Publishers"], "Unknown")

            box_players_raw = row.get("Box Player Count", "")
            if box_players_raw is not None and str(box_players_raw).strip() != "":
                min_p, max_p = parse_player_count_string(box_players_raw, 1, 4)
            else:
                min_p = clean_int(row.get("Min Players"), 1)
                max_p = clean_int(row.get("Max Players"), max(min_p, 4))

            major_awards_cleaned = [clean_award_name(a) for a in str(row.get("Major Awards", "")).split(",") if clean_award_name(a)]
            minor_awards_cleaned = [clean_award_name(a) for a in str(row.get("Minor Awards", "")).split(",") if clean_award_name(a)]

            games_list.append({
                "id": str(row.get("Game ID", "")).strip(),
                "title": clean_title(row.get("Title", "Unknown")),
                "year": clean_int(row.get("Year Published"), 0),
                "playing_time_raw": raw_play_time if raw_play_time else "0",
                "playing_time": clean_int(row.get("Play Time"), 0),
                "weight": clean_float(row.get("Weight / Complexity"), 0.0),
                "bgg_rating": clean_float(row.get("BGG Geek Rating"), 0.0),
                "user_rating": clean_float(row.get("User Rating"), 0.0),
                "plays_recorded": clean_int(row.get("Plays Recorded"), 0),
                "popularity_owned": clean_int(row.get("Popularity (Owned)", 0), 0),
                "publisher": publisher_val,
                "designer": designer_val,
                "artist": artist_val,
                "description": row.get("Description", "No description available."),
                "is_expansion": is_expansion,
                "is_standalone": is_standalone,
                "parent_game_id": parent_ref,
                "min_players": min_p,
                "max_players": max_p,
                "image": row.get("Full Image URL", ""),
                "thumbnail": row.get("Thumbnail URL", ""),
                "categories": [c.strip() for c in str(row.get("Categories", "")).split(",") if c.strip()],
                "mechanics": [m.strip() for m in str(row.get("Mechanics", "")).split(",") if m.strip()],
                "themes": [t.strip() for t in str(row.get("Themes", "")).split(",") if t.strip()],
                "major_awards": major_awards_cleaned,
                "minor_awards": minor_awards_cleaned,
                "game_mode": game_mode,
                "conflict_level": str(row.get("Conflict Level", "Medium")).strip(),
                "campaign_structure": campaign_struct,
                "supports_one_off": supports_one_off
            })
            
        GAMES_CACHE = games_list

        try:
            json_path = os.path.join(os.path.dirname(__file__), JSON_FILENAME)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(games_list, f, indent=2)
            print("JSON file successfully generated and saved.")
        except Exception as file_err:
            print(f"Notice: Could not write JSON file to disk ({file_err}). Serving from RAM cache.")

        return True
    except Exception as e:
        print(f"Error generating JSON from sheet: {e}")
        return False

app = Flask(__name__)

generate_json_from_sheet()

@app.route('/api/collection')
def api_collection():
    if GAMES_CACHE:
        return jsonify(GAMES_CACHE)
    try:
        json_path = os.path.join(os.path.dirname(__file__), JSON_FILENAME)
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
    except Exception as e:
        print(f"Error reading JSON cache: {e}")
    return jsonify([])

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/Jens')
def trigger_jens_sync():
    generate_json_from_sheet()
    return redirect(url_for('index'))

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>RENGAW'S MEEPLES // Collection Dash</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='-51.2 -51.2 614.40 614.40' fill='%23fee440'><path d='M256 54.99c-27 0-46.418 14.287-57.633 32.23-10.03 16.047-14.203 34.66-15.017 50.962-30.608 15.135-64.515 30.394-91.815 45.994-14.32 8.183-26.805 16.414-36.203 25.26C45.934 218.28 39 228.24 39 239.99c0 5 2.44 9.075 5.19 12.065 2.754 2.99 6.054 5.312 9.812 7.48 7.515 4.336 16.99 7.95 27.412 11.076 15.483 4.646 32.823 8.1 47.9 9.577-14.996 25.84-34.953 49.574-52.447 72.315C56.65 378.785 39 403.99 39 431.99c0 4-.044 7.123.31 10.26.355 3.137 1.256 7.053 4.41 10.156 3.155 3.104 7.017 3.938 10.163 4.28 3.146.345 6.315.304 10.38.304h111.542c8.097 0 14.026.492 20.125-3.43 6.1-3.92 8.324-9.275 12.67-17.275l.088-.16.08-.166s9.723-19.77 21.324-39.388c5.8-9.808 12.097-19.576 17.574-26.498 2.74-3.46 5.304-6.204 7.15-7.754.564-.472.82-.56 1.184-.76.363.2.62.288 1.184.76 1.846 1.55 4.41 4.294 7.15 7.754 5.477 6.922 11.774 16.69 17.574 26.498 11.6 19.618 21.324 39.387 21.324 39.387l.08.165.088.16c4.346 8 6.55 13.323 12.61 17.254 6.058 3.93 11.974 3.45 19.957 3.45H448c4 0 7.12.043 10.244-.304 3.123-.347 6.998-1.21 10.12-4.332 3.12-3.122 3.984-6.997 4.33-10.12.348-3.122.306-6.244.306-10.244 0-28-17.65-53.205-37.867-79.488-17.493-22.74-37.45-46.474-52.447-72.315 15.077-1.478 32.417-4.93 47.9-9.576 10.422-3.125 19.897-6.74 27.412-11.075 3.758-2.168 7.058-4.49 9.81-7.48 2.753-2.99 5.192-7.065 5.192-12.065 0-11.75-6.934-21.71-16.332-30.554-9.398-8.846-21.883-17.077-36.203-25.26-27.3-15.6-61.207-30.86-91.815-45.994-.814-16.3-4.988-34.915-15.017-50.96C302.418 69.276 283 54.99 256 54.99z'/></svg>">
<style>
    :root {
      --bg: #0d0221;
      --card-bg: #150833;
      --panel-bg: #1f0c48;
      --turquoise: #00f5d4;
      --magenta: #f72585;
      --yellow: #fee440;
      --purple-border: #7209b7;
      --yellow-border: #fee440;
      --text: #ffffff;
      --text-muted: #b8c0ff;
      --sidebar-width: 320px;
      --header-height: 110px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }

    body { 
      background: var(--bg); 
      color: var(--text); 
      padding: 0 20px 20px 20px; 
      min-height: 100vh; 
    }

    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: var(--card-bg); border-radius: 4px; }
    ::-webkit-scrollbar-thumb { background: var(--yellow); border-radius: 4px; border: 1px solid var(--purple-border); }
    ::-webkit-scrollbar-thumb:hover { background: var(--magenta); }

    header {
      position: sticky;
      top: 0;
      z-index: 80;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0px;
      flex-wrap: wrap;
      gap: 12px;
      background: rgba(21, 8, 51, 0.95);
      backdrop-filter: blur(8px);
      padding: 10px 20px;
      border-radius: 0 0 12px 12px;
      border: 2px solid var(--purple-border);
      border-top: none;
      box-shadow: 0 4px 15px rgba(247, 37, 133, 0.2);
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .meeple-logo {
      width: 42px;
      height: 42px;
      filter: drop-shadow(0 0 8px var(--magenta));
    }

    h1 { 
      font-size: 2.2rem; 
      font-weight: 900; 
      color: var(--yellow); 
      text-transform: uppercase; 
      letter-spacing: 2px;
      text-shadow: 2px 2px 0px var(--magenta);
      white-space: nowrap;
    }

    .header-right-column {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 8px;
      flex: 1;
      max-width: 680px;
    }

    .header-actions-top {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
      width: 100%;
      flex-wrap: wrap;
    }

    .header-search-and-sort-mobile {
      display: none;
    }

    .global-search-container {
      position: relative;
      width: 100%;
    }

    .global-search-input {
      width: 100%;
      background: var(--panel-bg);
      color: var(--text);
      border: 2px solid var(--purple-border);
      padding: 6px 12px 6px 36px;
      border-radius: 8px;
      font-size: 0.88rem;
      outline: none;
      transition: all 0.2s ease;
    }
    .global-search-input:focus {
      border-color: var(--turquoise);
      box-shadow: 0 0 10px rgba(0, 245, 212, 0.3);
    }
    .global-search-icon {
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 0.9rem;
      color: var(--text-muted);
      pointer-events: none;
    }

    button, select {
      background: var(--panel-bg);
      color: var(--turquoise);
      border: 2px solid var(--purple-border);
      padding: 6px 10px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 0.85rem;
      font-weight: 700;
      transition: all 0.2s ease;
    }

    button:hover, select:hover { 
      border-color: var(--turquoise); 
      background: var(--purple-border);
      color: #fff;
    }

    .btn-primary { 
      background: var(--magenta); 
      color: #fff; 
      border: 2px solid var(--magenta); 
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .btn-primary:hover { 
      background: var(--turquoise); 
      color: #000; 
      border-color: var(--turquoise);
    }

    .btn-play {
      background: var(--turquoise);
      color: #0d0221;
      border: 2px solid var(--turquoise);
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .btn-play:hover {
      background: var(--magenta);
      color: #ffffff;
      border-color: var(--magenta);
      box-shadow: 0 0 12px var(--magenta);
    }

    .btn-clear-filters {
      background: var(--panel-bg);
      color: #ffffff;
      border: 2px solid var(--magenta);
      text-transform: uppercase;
      letter-spacing: 1px;
      font-size: 0.8rem;
    }
    .btn-clear-filters:hover {
      background: var(--magenta);
      color: #ffffff;
      border-color: var(--magenta);
      box-shadow: 0 0 10px rgba(247, 37, 133, 0.4);
    }

    .btn-luck {
      background: var(--yellow);
      color: #0d0221;
      border: 2px solid var(--yellow);
      font-weight: 900;
      text-transform: uppercase;
    }
    .btn-luck:hover {
      background: #fff;
      color: var(--magenta);
      border-color: var(--magenta);
      box-shadow: 0 0 10px var(--yellow);
    }

    .sort-direction-btn {
      font-weight: bold;
      font-size: 0.95rem;
      padding: 5px 8px;
      text-align: center;
      color: var(--yellow);
    }

    .app-layout {
      display: flex;
      gap: 20px;
      align-items: flex-start;
      position: relative;
      margin-top: 20px;
    }

    .side-toolbar {
      width: var(--sidebar-width);
      flex-shrink: 0;
      background: var(--card-bg);
      border: 2px solid var(--turquoise);
      border-radius: 12px;
      padding: 0 16px 16px 16px;
      box-shadow: 0 0 15px rgba(0, 245, 212, 0.15);
      transition: all 0.3s ease;
      display: flex;
      flex-direction: column;
      gap: 16px;
      max-height: calc(100vh - var(--header-height) - 60px);
      overflow-y: auto;
      scrollbar-gutter: stable;
      z-index: 70;
    }

    .side-toolbar.collapsed {
      width: 0;
      padding: 0;
      margin: 0;
      border: none;
      opacity: 0;
      pointer-events: none;
    }

    .sidebar-toggle-tab {
      position: absolute;
      right: -36px;
      top: 20px;
      width: 36px;
      height: 44px;
      background: var(--card-bg);
      border: 2px solid var(--turquoise);
      border-left: none;
      border-radius: 0 8px 8px 0;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--yellow);
      font-weight: bold;
      z-index: 50;
      box-shadow: 4px 0 10px rgba(0, 245, 212, 0.2);
      transition: background 0.2s ease, color 0.2s ease;
      pointer-events: auto;
    }
    .sidebar-toggle-tab:hover {
      background: var(--turquoise);
      color: #0d0221;
    }

    .sidebar-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid var(--purple-border);
      padding: 16px 0 8px 0;
      margin-bottom: 4px;
      position: sticky;
      top: 0;
      background: var(--card-bg);
      z-index: 10;
    }
    .sidebar-header-title {
      font-size: 0.9rem;
      font-weight: 900;
      color: var(--yellow);
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .sidebar-close-btn {
      background: var(--magenta);
      color: #fff;
      border: none;
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: bold;
      cursor: pointer;
    }
    .sidebar-close-btn:hover {
      background: var(--turquoise);
      color: #0d0221;
    }

    .main-content {
      flex: 1;
      min-width: 0;
      padding-top: 10px;
      padding-right: 10px;
    }

    .filter-section {
      border: 1px solid var(--purple-border);
      border-radius: 8px;
      background: rgba(31, 12, 72, 0.4);
    }

    .filter-section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      background: var(--panel-bg);
      cursor: pointer;
      user-select: none;
      border-bottom: 1px solid var(--purple-border);
    }
    .filter-section-header:hover {
      background: var(--purple-border);
    }

    .filter-section-title {
      color: var(--yellow);
      font-size: 0.8rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .collapse-icon {
      font-weight: bold;
      color: var(--turquoise);
      transition: transform 0.2s ease;
      font-size: 0.8rem;
    }

    .filter-section.collapsed .filter-section-content {
      display: none;
    }
    .filter-section.collapsed .collapse-icon {
      transform: rotate(-90deg);
    }

    .filter-section-content {
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .filter-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .filter-label-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .filter-group label {
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
    }

    .value-display {
      font-size: 0.8rem;
      color: var(--yellow);
      font-weight: 800;
      background: var(--panel-bg);
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--purple-border);
    }

    .range-slider-container {
      position: relative;
      height: 32px;
      display: flex;
      align-items: center;
    }

    .range-slider-track {
      position: absolute;
      width: 100%;
      height: 6px;
      background: var(--panel-bg);
      border: 1px solid var(--purple-border);
      border-radius: 3px;
      pointer-events: none;
    }

    .range-slider-highlight {
      position: absolute;
      height: 6px;
      background: var(--magenta);
      border-radius: 3px;
      pointer-events: none;
    }

    .range-slider-container input[type="range"] {
      position: absolute;
      width: 100%;
      pointer-events: none;
      -webkit-appearance: none;
      background: none;
      z-index: 2;
      margin: 0;
    }

    .range-slider-container input[type="range"]::-webkit-slider-thumb {
      pointer-events: auto;
      -webkit-appearance: none;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: var(--yellow);
      cursor: pointer;
      border: 2px solid var(--bg);
      box-shadow: 0 0 4px rgba(0,0,0,0.6);
    }

    .checkbox-grid {
      display: flex;
      flex-direction: column;
      gap: 6px;
      background: var(--panel-bg);
      padding: 8px 10px;
      border-radius: 6px;
      border: 1px solid var(--purple-border);
    }

    .style-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      color: var(--turquoise);
      font-weight: 600;
      cursor: pointer;
    }
    .style-item input { accent-color: var(--magenta); }

    .dropdown-container { position: relative; }

    .dropdown-toggle {
      width: 100%;
      text-align: left;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--panel-bg);
      color: var(--turquoise);
      font-size: 0.85rem;
      padding: 8px;
    }

    .dropdown-menu {
      display: none;
      position: absolute;
      top: 105%;
      left: 0;
      right: 0;
      background: var(--card-bg);
      border: 2px solid var(--turquoise);
      border-radius: 8px;
      max-height: 240px;
      overflow-y: auto;
      z-index: 99;
      padding: 8px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.9);
      scrollbar-gutter: stable;
    }

    .dropdown-menu.show { display: block; }

    .dropdown-search {
      width: 100%;
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--purple-border);
      border-radius: 6px;
      padding: 6px 8px;
      font-size: 0.8rem;
      margin-bottom: 6px;
      outline: none;
    }

    .dropdown-controls {
      display: flex;
      gap: 6px;
      margin-bottom: 6px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--purple-border);
    }

    .dropdown-controls button {
      padding: 3px 6px;
      font-size: 0.7rem;
      flex: 1;
      border-color: var(--magenta);
      color: #fff;
    }

    .checkbox-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px;
      font-size: 0.8rem;
      cursor: pointer;
      border-radius: 4px;
      color: var(--text);
    }

    .checkbox-item:hover { background: var(--purple-border); }
    .checkbox-item input[type="checkbox"] { accent-color: var(--magenta); }

    .game-grid-row {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 20px;
      align-items: stretch;
      margin-bottom: 25px;
    }

    .game-card {
      background: var(--card-bg);
      border: 2px solid var(--purple-border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      position: relative;
      transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
      cursor: pointer;
    }

    .game-card.top-rated {
      border: 2px solid var(--yellow);
      box-shadow: 0 0 12px rgba(254, 228, 64, 0.25);
    }

    .game-card:hover {
      transform: translateY(-4px);
      border-color: var(--turquoise);
      box-shadow: 0 8px 20px rgba(0, 245, 212, 0.3);
    }

    .card-img-wrapper {
      height: 200px;
      width: 100%;
      background: radial-gradient(circle, #1a083d 0%, #080214 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 8px;
      border-bottom: 2px solid var(--purple-border);
      position: relative;
      flex-shrink: 0;
    }

    .game-card.top-rated .card-img-wrapper {
      border-bottom: 2px solid var(--yellow);
    }

    .card-img-wrapper img {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      filter: drop-shadow(0px 4px 8px rgba(0, 0, 0, 0.7));
    }

    .image-badges-top-left {
      position: absolute;
      top: 8px;
      left: 8px;
      display: flex;
      gap: 6px;
      z-index: 10;
      pointer-events: none;
    }

    .score-badge-circle {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.72rem;
      font-weight: 900;
      box-shadow: 0 2px 6px rgba(0,0,0,0.6);
      border: 2px solid var(--bg);
    }
    .score-badge-bgg {
      background: var(--turquoise);
      color: #0d0221;
    }
    .score-badge-luke {
      background: var(--yellow);
      color: #0d0221;
    }

    .expansion-icon-btn {
      position: absolute;
      top: 8px;
      right: 8px;
      background: transparent;
      border: none;
      cursor: pointer;
      z-index: 10;
      transition: transform 0.2s ease;
      padding: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .expansion-icon-btn svg {
      width: 28px;
      height: 28px;
      fill: var(--turquoise);
      filter: drop-shadow(0 0 4px rgba(0, 245, 212, 0.8));
    }
    .expansion-icon-btn:hover {
      transform: scale(1.2);
    }

    .medal-icon-badge {
      position: absolute;
      bottom: 8px;
      right: 8px;
      background: transparent;
      color: var(--yellow);
      width: 28px;
      height: 28px;
      border-radius: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      border: none;
      box-shadow: none;
      font-size: 1.2rem;
      z-index: 10;
      pointer-events: none;
      filter: drop-shadow(0 2px 4px rgba(0,0,0,0.8));
    }

    .card-content {
      padding: 14px;
      display: flex;
      flex-direction: column;
      flex: 1;
      justify-content: space-between;
      gap: 8px;
    }

    .game-title {
      font-size: 1.05rem;
      font-weight: 800;
      color: var(--yellow);
      line-height: 1.2;
    }

    .game-stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      padding-top: 8px;
      border-top: 1px solid var(--purple-border);
      font-size: 0.8rem;
    }

    .game-card.top-rated .game-stats {
      border-top: 1px solid var(--yellow);
    }

    .stat-badge {
      background: var(--panel-bg);
      color: var(--turquoise);
      padding: 4px 6px;
      border-radius: 4px;
      text-align: center;
      font-weight: 600;
      border: 1px solid var(--purple-border);
    }

    .expansions-overlay {
      display: none;
      position: absolute;
      inset: 0;
      background: rgba(21, 8, 51, 0.98);
      backdrop-filter: blur(4px);
      z-index: 25;
      padding: 12px;
      flex-direction: column;
      overflow-y: auto;
      overflow-x: hidden;
      border-radius: 12px;
    }
    .game-card.show-expansions .expansions-overlay {
      display: flex;
    }

    .expansions-header {
      font-size: 0.8rem;
      font-weight: 900;
      color: var(--yellow);
      text-transform: uppercase;
      border-bottom: 2px dashed var(--magenta);
      padding-bottom: 6px;
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      white-space: nowrap;
      gap: 4px;
    }

    .expansion-close-btn {
      background: var(--magenta);
      color: #fff;
      border: 1px solid var(--turquoise);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.7rem;
      cursor: pointer;
      font-weight: bold;
      flex-shrink: 0;
    }
    .expansion-close-btn:hover {
      background: var(--turquoise);
      color: #0d0221;
    }

    .expansion-item {
      background: var(--panel-bg);
      border: 1px solid var(--purple-border);
      border-radius: 6px;
      padding: 6px 8px;
      margin-bottom: 4px;
      font-size: 0.75rem;
    }

    .expansion-title {
      font-weight: 800;
      color: var(--turquoise);
      margin-bottom: 2px;
    }

    .modal-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(13, 2, 33, 0.88);
      backdrop-filter: blur(8px);
      z-index: 100;
      justify-content: center;
      align-items: center;
      padding: 20px;
    }
    .modal-overlay.open { display: flex; }

    .grid-overlay-container {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(13, 2, 33, 0.88);
      backdrop-filter: blur(8px);
      z-index: 100;
      justify-content: center;
      align-items: center;
      padding: 20px;
    }
    .grid-overlay-container.open { display: flex; }

    .modal-card {
      background: var(--card-bg);
      border: 4px solid var(--yellow);
      border-radius: 16px;
      max-width: 650px;
      width: 100%;
      padding: 20px;
      box-shadow: 0 0 35px rgba(254, 228, 64, 0.4);
      position: relative;
      max-height: 90vh;
      overflow-y: auto;
    }

    .modal-close-x {
      position: absolute;
      top: 12px;
      right: 12px;
      background: var(--magenta);
      color: #fff;
      border: 2px solid var(--yellow);
      border-radius: 50%;
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: 1rem;
      cursor: pointer;
      z-index: 110;
      box-shadow: 0 0 8px rgba(247, 37, 133, 0.5);
    }
    .modal-close-x:hover {
      background: var(--turquoise);
      color: #0d0221;
      border-color: var(--turquoise);
    }

    .modal-title {
      color: var(--magenta);
      font-size: 1.4rem;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 12px;
      padding-right: 30px;
    }

    /* Arcade Launcher Grid */
    .arcade-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
      margin-top: 15px;
    }

    .arcade-card {
      background: var(--panel-bg);
      border: 2px solid var(--purple-border);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: all 0.2s ease;
      cursor: pointer;
    }
    .arcade-card:hover {
      border-color: var(--turquoise);
      transform: translateY(-3px);
      box-shadow: 0 6px 15px rgba(0, 245, 212, 0.25);
    }

    .arcade-card h3 {
      color: var(--yellow);
      font-size: 1.1rem;
      font-weight: 800;
    }

    .arcade-card p {
      color: var(--text-muted);
      font-size: 0.82rem;
      line-height: 1.35;
      flex: 1;
    }

    /* Mini Games Specific UI Components */
    .game-board {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-top: 10px;
    }

    .game-status-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--panel-bg);
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px solid var(--purple-border);
      font-weight: 700;
      color: var(--turquoise);
    }

    .game-btn {
      background: var(--magenta);
      color: #fff;
      border: none;
      padding: 8px 14px;
      border-radius: 6px;
      font-weight: bold;
      cursor: pointer;
    }
    .game-btn:hover { background: var(--turquoise); color: #000; }

    /* Higher / Lower */
    .hl-container { display: flex; gap: 10px; align-items: center; justify-content: space-around; margin: 15px 0; }
    .hl-card { background: var(--panel-bg); border: 2px solid var(--purple-border); border-radius: 10px; padding: 12px; width: 45%; text-align: center; }
    .hl-card img { height: 110px; object-fit: contain; margin-bottom: 8px; }

    /* Connections Grid */
    .conn-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 10px; }
    .conn-card { background: var(--panel-bg); border: 2px solid var(--purple-border); border-radius: 8px; padding: 10px; font-size: 0.78rem; font-weight: bold; text-align: center; cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: center; min-height: 60px; }
    .conn-card.selected { border-color: var(--yellow); background: var(--purple-border); }
    .conn-card.solved { opacity: 0.6; pointer-events: none; }

    /* Blind Ranking Column Grid (1-5 down col 1, 6-10 down col 2) */
    .blind-grid-columns {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 10px;
    }

    /* Auto Suggest Input Dropdown */
    .autocomplete-wrapper { position: relative; width: 100%; }
    .autocomplete-list {
      position: absolute; top: 100%; left: 0; right: 0;
      background: var(--card-bg); border: 2px solid var(--turquoise);
      border-radius: 0 0 8px 8px; max-height: 180px; overflow-y: auto;
      z-index: 120;
    }
    .autocomplete-item {
      padding: 8px 12px; cursor: pointer; color: var(--text); font-size: 0.85rem;
    }
    .autocomplete-item:hover { background: var(--purple-border); color: var(--yellow); }

    /* Crossword Board */
    .crossword-board { display: grid; gap: 2px; background: var(--panel-bg); padding: 10px; border-radius: 8px; overflow-x: auto; justify-content: center; }
    .crossword-cell { width: 32px; height: 32px; background: var(--bg); border: 1px solid var(--purple-border); text-align: center; font-weight: bold; text-transform: uppercase; color: var(--yellow); font-size: 1rem; }
    .crossword-cell.empty { background: transparent; border: none; }

    .btn-text-play-desktop { display: inline; }
    .btn-text-play-mobile { display: none; }
    .btn-text-clear-desktop { display: inline; }
    .btn-text-clear-mobile { display: none; }
    .btn-icon { display: inline; }

@media (max-width: 600px), (max-height: 500px) and (orientation: landscape) {
      body { padding: 0 6px 6px 6px; }
      
      header { 
        padding: 8px 10px; 
        gap: 8px; 
        flex-direction: column;
        align-items: stretch; 
        justify-content: flex-start;
      }

      .header-left { 
        width: 100%; 
        justify-content: center;
      }
      .header-left .meeple-logo { width: 28px; height: 28px; }
      h1 { font-size: 1.2rem; letter-spacing: 0.5px; text-shadow: 1px 1px 0px var(--magenta); }

      .header-right-column { 
        width: 100%;
        max-width: none; 
        gap: 6px; 
        align-items: center; 
        flex-direction: column;
      }

      .header-actions-top {
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        gap: 4px;
        align-items: center;
        width: 100%;
        justify-content: space-between;
      }

      .header-actions-top button {
        flex: 1;
        text-align: center;
        padding: 6px 2px;
        font-size: 0.7rem;
      }

      .header-actions-top select,
      .header-actions-top .sort-direction-btn {
        display: none;
      }

      .header-search-and-sort-mobile {
        display: flex;
        gap: 6px;
        align-items: center;
        width: 100%;
      }

      .header-search-and-sort-mobile .global-search-container {
        flex: 1;
      }

      .header-search-and-sort-mobile select {
        width: auto;
        padding: 5px 6px;
        font-size: 0.75rem;
      }

      .btn-icon { display: none; }
      .btn-text-play-desktop { display: none; }
      .btn-text-play-mobile { display: inline; }
      .btn-text-clear-desktop { display: none; }
      .btn-text-clear-mobile { display: inline; }
      .desktop-search-slot { display: none; }

      .global-search-input { padding: 5px 8px 5px 28px; font-size: 0.8rem; }
      .global-search-icon { font-size: 0.75rem; left: 8px; }

      .side-toolbar {
        position: fixed;
        top: 0;
        left: 0;
        width: 85vw;
        max-width: 320px;
        height: 100vh;
        max-height: 100vh;
        z-index: 200;
        border-radius: 0 12px 12px 0;
        box-shadow: 5px 0 25px rgba(0, 0, 0, 0.8);
      }
      .sidebar-toggle-tab { display: none; }
      
      .game-grid-row { 
        grid-template-columns: repeat(2, minmax(0, 1fr)); 
        gap: 8px; 
      }
    }
  </style>
</head>
<body>

  <header id="main-header">
    <div class="header-left">
      <div style="display: flex; align-items: center; gap: 8px;">
        <svg class="meeple-logo" viewBox="-51.2 -51.2 614.40 614.40" xmlns="http://www.w3.org/2000/svg" fill="#fee440" style="vertical-align: middle;">
          <path fill="#fee440" d="M256 54.99c-27 0-46.418 14.287-57.633 32.23-10.03 16.047-14.203 34.66-15.017 50.962-30.608 15.135-64.515 30.394-91.815 45.994-14.32 8.183-26.805 16.414-36.203 25.26C45.934 218.28 39 228.24 39 239.99c0 5 2.44 9.075 5.19 12.065 2.754 2.99 6.054 5.312 9.812 7.48 7.515 4.336 16.99 7.95 27.412 11.076 15.483 4.646 32.823 8.1 47.9 9.577-14.996 25.84-34.953 49.574-52.447 72.315C56.65 378.785 39 403.99 39 431.99c0 4-.044 7.123.31 10.26.355 3.137 1.256 7.053 4.41 10.156 3.155 3.104 7.017 3.938 10.163 4.28 3.146.345 6.315.304 10.38.304h111.542c8.097 0 14.026.492 20.125-3.43 6.1-3.92 8.324-9.275 12.67-17.275l.088-.16.08-.166s9.723-19.77 21.324-39.388c5.8-9.808 12.097-19.576 17.574-26.498 2.74-3.46 5.304-6.204 7.15-7.754.564-.472.82-.56 1.184-.76.363.2.62.288 1.184.76 1.846 1.55 4.41 4.294 7.15 7.754 5.477 6.922 11.774 16.69 17.574 26.498 11.6 19.618 21.324 39.387 21.324 39.387l.08.165.088.16c4.346 8 6.55 13.323 12.61 17.254 6.058 3.93 11.974 3.45 19.957 3.45H448c4 0 7.12.043 10.244-.304 3.123-.347 6.998-1.21 10.12-4.332 3.12-3.122 3.984-6.997 4.33-10.12.348-3.122.306-6.244.306-10.244 0-28-17.65-53.205-37.867-79.488-17.493-22.74-37.45-46.474-52.447-72.315 15.077-1.478 32.417-4.93 47.9-9.576 10.422-3.125 19.897-6.74 27.412-11.075 3.758-2.168 7.058-4.49 9.81-7.48 2.753-2.99 5.192-7.065 5.192-12.065 0-11.75-6.934-21.71-16.332-30.554-9.398-8.846-21.883-17.077-36.203-25.26-27.3-15.6-61.207-30.86-91.815-45.994-.814-16.3-4.988-34.915-15.017-50.96C302.418 69.276 283 54.99 256 54.99"></path>
        </svg>
        <h1>Rengaw's Meeples</h1>
      </div>
    </div>

    <div class="header-right-column">
      <div class="header-actions-top">
        <button id="play-games-btn" class="btn-play" title="Play Mini Games"><span class="btn-icon">🎮 </span><span>Play Games</span></button>
        <button id="luck-btn" class="btn-luck" title="Pick Game"><span class="btn-icon">🎲 </span><span class="btn-text-play-desktop">Pick Game</span><span class="btn-text-play-mobile">Pick</span></button>
        <button id="toggle-filters-btn" class="btn-primary" title="Filters"><span class="btn-icon">⚙️ </span>Filters</button>
        <button id="header-clear-btn" class="btn-clear-filters" title="Reset to Page Load"><span class="btn-text-clear-desktop">Clear Filters</span><span class="btn-text-clear-mobile">Clear</span></button>
        <select id="sort-select">
          <option value="popularity_owned" selected>Popularity</option>
          <option value="title">Title</option>
          <option value="user_rating">Luke's Rating</option>
          <option value="bgg_rating">BGG Rating</option>
          <option value="weight">Weight</option>
          <option value="playing_time">Playtime</option>
          <option value="year">Year Published</option>
        </select>
        <button id="sort-dir-btn" class="sort-direction-btn" title="Toggle Sort Direction">▼</button>
      </div>

      <div class="header-search-and-sort-mobile">
        <div class="global-search-container">
          <span class="global-search-icon">🔍</span>
          <input type="text" id="global-search-mobile" class="global-search-input" placeholder="Search collection...">
        </div>
        <select id="sort-select-mobile">
          <option value="popularity_owned" selected>Popularity</option>
          <option value="title">Title</option>
          <option value="user_rating">Luke's Rating</option>
          <option value="bgg_rating">BGG Rating</option>
          <option value="weight">Weight</option>
          <option value="playing_time">Playtime</option>
          <option value="year">Year Published</option>
        </select>
        <button id="sort-dir-btn-mobile" class="sort-direction-btn" title="Toggle Sort Direction">▼</button>
      </div>

      <div class="global-search-container desktop-search-slot">
        <span class="global-search-icon">🔍</span>
        <input type="text" id="global-search" class="global-search-input" placeholder="Search collection...">
      </div>
    </div>
  </header>

  <div class="app-layout">

    <aside id="side-toolbar" class="side-toolbar collapsed">
      <button class="sidebar-toggle-tab" onclick="toggleSidebar()" title="Toggle Sidebar">☰</button>
      
      <div class="sidebar-header-row">
        <span class="sidebar-header-title">⚙️ Filters</span>
        <button class="sidebar-close-btn" onclick="toggleSidebar()">✕ Collapse</button>
      </div>

      <div class="filter-section" id="section-sliders">
        <div class="filter-section-header" onclick="toggleFilterSection('section-sliders')">
          <span class="filter-section-title">📊 Range & Numeric Filters</span>
          <span class="collapse-icon">▼</span>
        </div>
        <div class="filter-section-content">
          <div class="filter-group">
            <div class="filter-label-header">
              <label>Player Count</label>
              <span id="player-val" class="value-display">1 - 10+</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="player-track" class="range-slider-highlight"></div>
              <input type="range" id="player-min" min="1" max="10" value="1">
              <input type="range" id="player-max" min="1" max="10" value="10">
            </div>
          </div>

          <div class="filter-group">
            <div class="filter-label-header">
              <label>Weight (Complexity)</label>
              <span id="weight-val" class="value-display">1.0 - 5.0</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="weight-track" class="range-slider-highlight"></div>
              <input type="range" id="weight-min" min="1.0" max="5.0" step="0.1" value="1.0">
              <input type="range" id="weight-max" min="1.0" max="5.0" step="0.1" value="5.0">
            </div>
          </div>

          <div class="filter-group">
            <div class="filter-label-header">
              <label>Playtime (Min)</label>
              <span id="time-val" class="value-display">0 - 300+ min</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="time-track" class="range-slider-highlight"></div>
              <input type="range" id="time-min" min="0" max="300" step="15" value="0">
              <input type="range" id="time-max" min="0" max="300" step="15" value="300">
            </div>
          </div>

          <div class="filter-group">
            <div class="filter-label-header">
              <label>BGG Rating</label>
              <span id="bgg-val" class="value-display">1.0 - 10.0</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="bgg-track" class="range-slider-highlight"></div>
              <input type="range" id="bgg-min" min="1" max="10" step="0.5" value="1">
              <input type="range" id="bgg-max" min="1" max="10" step="0.5" value="10">
            </div>
          </div>

          <div class="filter-group">
            <div class="filter-label-header">
              <label>Luke's Rating</label>
              <span id="luke-val" class="value-display">0 - 10</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="luke-track" class="range-slider-highlight"></div>
              <input type="range" id="luke-min" min="0" max="10" step="1" value="0">
              <input type="range" id="luke-max" min="0" max="10" step="1" value="10">
            </div>
          </div>

          <div class="filter-group">
            <div class="filter-label-header">
              <label>Year Published</label>
              <span id="year-val" class="value-display">&lt;1990 - 2026</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="year-track" class="range-slider-highlight"></div>
              <input type="range" id="year-min" min="0" max="28" value="0">
              <input type="range" id="year-max" min="0" max="28" value="28">
            </div>
          </div>
        </div>
      </div>

      <div class="filter-section" id="section-style">
        <div class="filter-section-header" onclick="toggleFilterSection('section-style')">
          <span class="filter-section-title">🕹️ Style & Play Modes</span>
          <span class="collapse-icon">▼</span>
        </div>
        <div class="filter-section-content">
          <div id="style-list" class="checkbox-grid"></div>

          <div class="checkbox-grid">
            <label class="style-item">
              <input type="checkbox" id="filter-played">
              Played
            </label>
            <label class="style-item">
              <input type="checkbox" id="filter-unplayed">
              Unplayed
            </label>
          </div>

          <div class="checkbox-grid">
            <label class="style-item">
              <input type="checkbox" id="filter-standalone" checked>
              Base Games
            </label>
            <label class="style-item">
              <input type="checkbox" id="filter-expansions">
              Expansions
            </label>
            <label class="style-item">
              <input type="checkbox" id="filter-campaign">
              Campaign / Legacy
            </label>
          </div>
        </div>
      </div>

      <div class="filter-section" id="section-awards">
        <div class="filter-section-header" onclick="toggleFilterSection('section-awards')">
          <span class="filter-section-title">🏆 Awards</span>
          <span class="collapse-icon">▼</span>
        </div>
        <div class="filter-section-content">
          <div class="filter-group">
            <label>Major Awards</label>
            <div class="dropdown-container">
              <button id="major-award-toggle" class="dropdown-toggle">All Major Awards <span>▼</span></button>
              <div id="major-award-menu" class="dropdown-menu">
                <input type="text" id="major-award-search" class="dropdown-search" placeholder="Search major awards...">
                <div class="dropdown-controls">
                  <button id="major-award-select-all">All</button>
                  <button id="major-award-clear-all">Clear</button>
                </div>
                <div id="major-award-list"></div>
              </div>
            </div>
          </div>

          <div class="filter-group">
            <label>Minor Awards</label>
            <div class="dropdown-container">
              <button id="minor-award-toggle" class="dropdown-toggle">All Minor Awards <span>▼</span></button>
              <div id="minor-award-menu" class="dropdown-menu">
                <input type="text" id="minor-award-search" class="dropdown-search" placeholder="Search minor awards...">
                <div class="dropdown-controls">
                  <button id="minor-award-select-all">All</button>
                  <button id="minor-award-clear-all">Clear</button>
                </div>
                <div id="minor-award-list"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="filter-section" id="section-dropdowns">
        <div class="filter-section-header" onclick="toggleFilterSection('section-dropdowns')">
          <span class="filter-section-title">🏷️ Categories, Mechanics & Themes</span>
          <span class="collapse-icon">▼</span>
        </div>
        <div class="filter-section-content">

          <div class="filter-group">
            <label>Themes</label>
            <div class="dropdown-container">
              <button id="theme-toggle" class="dropdown-toggle">All Themes <span>▼</span></button>
              <div id="theme-menu" class="dropdown-menu">
                <input type="text" id="theme-search" class="dropdown-search" placeholder="Search themes...">
                <div class="dropdown-controls">
                  <button id="theme-select-all">All</button>
                  <button id="theme-clear-all">Clear</button>
                </div>
                <div id="theme-list"></div>
              </div>
            </div>
          </div>

          <div class="filter-group">
            <label>Categories</label>
            <div class="dropdown-container">
              <button id="cat-toggle" class="dropdown-toggle">All Categories <span>▼</span></button>
              <div id="cat-menu" class="dropdown-menu">
                <input type="text" id="cat-search" class="dropdown-search" placeholder="Search categories...">
                <div class="dropdown-controls">
                  <button id="cat-select-all">All</button>
                  <button id="cat-clear-all">Clear</button>
                </div>
                <div id="cat-list"></div>
              </div>
            </div>
          </div>

          <div class="filter-group">
            <label>Mechanics</label>
            <div class="dropdown-container">
              <button id="mech-toggle" class="dropdown-toggle">All Mechanics <span>▼</span></button>
              <div id="mech-menu" class="dropdown-menu">
                <input type="text" id="mech-search" class="dropdown-search" placeholder="Search mechanics...">
                <div class="dropdown-controls">
                  <button id="mech-select-all">All</button>
                  <button id="mech-clear-all">Clear</button>
                </div>
                <div id="mech-list"></div>
              </div>
            </div>
          </div>

          <div class="filter-group">
            <label>Publisher</label>
            <div class="dropdown-container">
              <button id="pub-toggle" class="dropdown-toggle">All Publishers <span>▼</span></button>
              <div id="pub-menu" class="dropdown-menu">
                <input type="text" id="pub-search" class="dropdown-search" placeholder="Search publishers...">
                <div class="dropdown-controls">
                  <button id="pub-select-all">All</button>
                  <button id="pub-clear-all">Clear</button>
                </div>
                <div id="pub-list"></div>
              </div>
            </div>
          </div>

          <div class="filter-group">
            <label>Designers</label>
            <div class="dropdown-container">
              <button id="des-toggle" class="dropdown-toggle">All Designers <span>▼</span></button>
              <div id="des-menu" class="dropdown-menu">
                <input type="text" id="des-search" class="dropdown-search" placeholder="Search designers...">
                <div class="dropdown-controls">
                  <button id="des-select-all">All</button>
                  <button id="des-clear-all">Clear</button>
                </div>
                <div id="des-list"></div>
              </div>
            </div>
          </div>

          <div class="filter-group">
            <label>Artists</label>
            <div class="dropdown-container">
              <button id="art-toggle" class="dropdown-toggle">All Artists <span>▼</span></button>
              <div id="art-menu" class="dropdown-menu">
                <input type="text" id="art-search" class="dropdown-search" placeholder="Search artists...">
                <div class="dropdown-controls">
                  <button id="art-select-all">All</button>
                  <button id="art-clear-all">Clear</button>
                </div>
                <div id="art-list"></div>
              </div>
            </div>
          </div>

        </div>
      </div>

      <button id="reset-filters-btn" style="width: 100%;">Reset to Page Load</button>

    </aside>

    <main id="game-grid" class="main-content">
    </main>

  </div>

  <!-- Detail Modal -->
  <div id="detail-modal" class="grid-overlay-container">
    <div class="modal-card" style="position: relative;">
      <div class="modal-close-x" onclick="closeDetailModal()">✕</div>
      <div id="detail-modal-content"></div>
    </div>
  </div>

  <!-- Pick Game Modal -->
  <div id="luck-modal" class="modal-overlay">
    <div class="modal-card" style="position: relative;">
      <div class="modal-close-x" onclick="closeLuckModal()">✕</div>
      <div class="modal-title" style="text-align: center;">✨ Pick Game ✨</div>
      <div id="modal-content"></div>
      <div style="display: flex; gap: 8px; margin-top: 16px;">
        <button id="modal-try-again-btn" class="btn-luck" style="flex: 1; padding: 10px;">🎲 Try Again</button>
        <button id="modal-change-filters-btn" class="btn-primary" style="flex: 1; padding: 10px;">Filters</button>
      </div>
    </div>
  </div>

  <!-- Games Arcade Overlay Modal -->
  <div id="games-arcade-modal" class="modal-overlay">
    <div class="modal-card" style="position: relative; max-width: 750px;">
      <div class="modal-close-x" onclick="closeGamesArcadeModal()">✕</div>
      <div id="arcade-view-launcher">
        <div class="modal-title">👾 Mini-Game Arcade</div>
        <p style="color: var(--text-muted); font-size: 0.9rem;">Test your board game knowledge with interactive games generated from your collection!</p>
        <div class="arcade-grid">
          <div class="arcade-card" onclick="launchGame('blind_ranking')">
            <h3>🎲 Blind Ranking</h3>
            <p>Rank 10 randomly drawn games one by one without seeing what’s next.</p>
          </div>
          <div class="arcade-card" onclick="launchGame('guess_game')">
            <h3>🔎 Guess the Game</h3>
            <p>Progressive clues paired with Pixel/Blur or Zoom image modes.</p>
          </div>
          <div class="arcade-card" onclick="launchGame('higher_lower')">
            <h3>📈 Higher or Lower</h3>
            <p>Compare games directly based on Weight or Ratings metrics.</p>
          </div>
          <div class="arcade-card" onclick="launchGame('connections')">
            <h3>🧩 Connections</h3>
            <p>Group 16 collection cards into 4 distinct metadata buckets (5 strikes allowed).</p>
          </div>
          <div class="arcade-card" onclick="launchGame('glipped')">
            <h3>🌀 4X3</h3>
            <p>A 9-card grid with 4 intersecting sets of 3 games (4 strikes allowed).</p>
          </div>
          <div class="arcade-card" onclick="launchGame('crossword')">
            <h3>✏️ Collection Crossword</h3>
            <p>An interactive crossword puzzle built from your actual titles and metadata clues.</p>
          </div>
        </div>
      </div>
      <div id="arcade-game-container" style="display: none;"></div>
    </div>
  </div>

<script>
    let games = [];
    let rawCollection = [];
    let currentlyFilteredGames = [];
    let isAscending = false;
    let currentDetailGame = null;

    let selectedPlayerCounts = new Set();
    let selectedStyles = new Set();
    let selectedMajorAwards = new Set();
    let selectedMinorAwards = new Set();
    let selectedThemes = new Set();
    let selectedCategories = new Set();
    let selectedMechanics = new Set();
    let selectedPublishers = new Set();
    let selectedDesigners = new Set();
    let selectedArtists = new Set();

    const toolbar = document.getElementById('side-toolbar');
    const toggleBtn = document.getElementById('toggle-filters-btn');
    const resetBtn = document.getElementById('reset-filters-btn');
    const headerClearBtn = document.getElementById('header-clear-btn');
    const grid = document.getElementById('game-grid');
    const sortSelect = document.getElementById('sort-select');
    const sortDirBtn = document.getElementById('sort-dir-btn');
    const sortSelectMobile = document.getElementById('sort-select-mobile');
    const sortDirBtnMobile = document.getElementById('sort-dir-btn-mobile');
    const luckBtn = document.getElementById('luck-btn');
    const luckModal = document.getElementById('luck-modal');
    const modalContent = document.getElementById('modal-content');
    const modalTryAgainBtn = document.getElementById('modal-try-again-btn');
    const modalChangeFiltersBtn = document.getElementById('modal-change-filters-btn');
    const detailModal = document.getElementById('detail-modal');
    const detailModalContent = document.getElementById('detail-modal-content');
    const globalSearch = document.getElementById('global-search');
    const globalSearchMobile = document.getElementById('global-search-mobile');
    const playGamesBtn = document.getElementById('play-games-btn');
    const gamesArcadeModal = document.getElementById('games-arcade-modal');

    playGamesBtn.addEventListener('click', () => {
      returnToArcadeMenu();
      gamesArcadeModal.classList.add('open');
    });

    function returnToArcadeMenu() {
      document.getElementById('arcade-view-launcher').style.display = 'block';
      document.getElementById('arcade-game-container').style.display = 'none';
      document.getElementById('arcade-game-container').innerHTML = '';
    }

    function closeGamesArcadeModal() {
      gamesArcadeModal.classList.remove('open');
    }

    detailModal.addEventListener('click', (e) => { if (e.target === detailModal) closeDetailModal(); });
    luckModal.addEventListener('click', (e) => { if (e.target === luckModal) closeLuckModal(); });
    gamesArcadeModal.addEventListener('click', (e) => { if (e.target === gamesArcadeModal) closeGamesArcadeModal(); });

    // ==========================================
    // MINI GAMES OVERLAY ENGINE
    // ==========================================

    function launchGame(gameKey) {
      document.getElementById('arcade-view-launcher').style.display = 'none';
      const container = document.getElementById('arcade-game-container');
      container.style.display = 'block';
      container.innerHTML = '';

      if (gameKey === 'blind_ranking') initBlindRanking(container);
      else if (gameKey === 'guess_game') initGuessGame(container);
      else if (gameKey === 'higher_lower') initHigherLower(container);
      else if (gameKey === 'connections') initConnections(container);
      else if (gameKey === 'glipped') initGrid4x3(container);
      else if (gameKey === 'crossword') initCrossword(container);
    }

    // 1. BLIND RANKING (All Games, BGG Rating)
    function initBlindRanking(container) {
      const pool = [...rawCollection].filter(g => g.bgg_rating > 0);
      const drawn = shuffleArray(pool).slice(0, 10);
      let currentIndex = 0;
      let slots = new Array(10).fill(null);

      function render() {
        if (currentIndex >= 10) {
          let score = 0;
          for (let i = 0; i < 9; i++) {
            if (slots[i].bgg_rating >= slots[i+1].bgg_rating) score += 10;
          }
          container.innerHTML = `
            <div class="modal-title">🎲 Blind Ranking Results</div>
            <p style="color: var(--yellow); font-weight: bold; margin-bottom: 12px;">Alignment Accuracy: ${score}%</p>
            <div class="blind-grid-columns">
              <div style="display:flex; flex-direction:column; gap:6px;">
                ${slots.slice(0, 5).map((g, idx) => `<div class="stat-badge" style="text-align:left;">#${idx+1}: <b>${g.title}</b> (BGG: ${g.bgg_rating.toFixed(1)})</div>`).join('')}
              </div>
              <div style="display:flex; flex-direction:column; gap:6px;">
                ${slots.slice(5, 10).map((g, idx) => `<div class="stat-badge" style="text-align:left;">#${idx+6}: <b>${g.title}</b> (BGG: ${g.bgg_rating.toFixed(1)})</div>`).join('')}
              </div>
            </div>
            <div style="margin-top: 15px; display: flex; gap: 8px;">
              <button class="game-btn" onclick="launchGame('blind_ranking')" style="flex:1;">Play Again</button>
              <button class="game-btn" onclick="returnToArcadeMenu()" style="flex:1; background: var(--purple-border);">Menu</button>
            </div>
          `;
          return;
        }

        const currentGame = drawn[currentIndex];
        let col1 = '', col2 = '';

        for (let i = 0; i < 5; i++) {
          const gameInSlot = slots[i];
          col1 += `<button class="game-btn" style="width:100%; text-align:left; background:${gameInSlot ? 'var(--panel-bg)' : 'var(--card-bg)'}; border: 1px solid var(--purple-border);" ${gameInSlot ? 'disabled' : `onclick="placeBlindSlot(${i})"`}>
            #${i+1}: ${gameInSlot ? `${gameInSlot.title} (${gameInSlot.bgg_rating.toFixed(1)})` : '--- Empty ---'}
          </button>`;
        }
        for (let i = 5; i < 10; i++) {
          const gameInSlot = slots[i];
          col2 += `<button class="game-btn" style="width:100%; text-align:left; background:${gameInSlot ? 'var(--panel-bg)' : 'var(--card-bg)'}; border: 1px solid var(--purple-border);" ${gameInSlot ? 'disabled' : `onclick="placeBlindSlot(${i})"`}>
            #${i+1}: ${gameInSlot ? `${gameInSlot.title} (${gameInSlot.bgg_rating.toFixed(1)})` : '--- Empty ---'}
          </button>`;
        }

        container.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="modal-title" style="margin:0;">🎲 Blind Ranking (${currentIndex + 1}/10)</div>
            <button class="expansion-close-btn" onclick="returnToArcadeMenu()">Back</button>
          </div>
          <div style="display:flex; gap:12px; align-items:center; margin:12px 0; background:var(--panel-bg); padding:10px; border-radius:8px;">
            <img src="${currentGame.thumbnail || currentGame.image}" style="height:70px; width:70px; object-fit:contain;">
            <div>
              <div style="font-weight:bold; color:var(--yellow); font-size:1.1rem;">${currentGame.title}</div>
              <div style="color:var(--text-muted); font-size:0.8rem;">Place this game in rank slot 1 to 10 (Highest to Lowest BGG rating).</div>
            </div>
          </div>
          <div class="blind-grid-columns">
            <div style="display:flex; flex-direction:column; gap:6px;">${col1}</div>
            <div style="display:flex; flex-direction:column; gap:6px;">${col2}</div>
          </div>
        `;
      }

      window.placeBlindSlot = function(idx) {
        slots[idx] = drawn[currentIndex];
        currentIndex++;
        render();
      };

      render();
    }

    // 2. GUESS THE GAME (Extra Zoom, Clue Sequence)
    function initGuessGame(container) {
      const target = shuffleArray([...rawCollection].filter(g => g.image))[0];
      let clueStep = 0;
      let zoomMode = true;

      const clues = [
        `Year Published: ${target.year}`,
        `Player Count: ${target.min_players === target.max_players ? target.min_players : target.min_players + '-' + target.max_players}`,
        `Publisher: ${target.publisher}`,
        `Weight / Complexity: ${target.weight}`,
        `BGG Rating: ${target.bgg_rating}`,
        `Designer: ${target.designer}`
      ];

      function render() {
        const revealedClues = clues.slice(0, clueStep + 1);
        
        container.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="modal-title" style="margin:0;">🔎 Guess the Game</div>
            <button class="expansion-close-btn" onclick="returnToArcadeMenu()">Back</button>
          </div>
          <div style="display:flex; gap:10px; margin:10px 0;">
            <button class="game-btn" onclick="toggleGuessMode(true)" style="flex:1; background:${zoomMode ? 'var(--turquoise)' : 'var(--panel-bg)'}; color:${zoomMode ? '#000' : '#fff'}">Super Zoom Mode</button>
            <button class="game-btn" onclick="toggleGuessMode(false)" style="flex:1; background:${!zoomMode ? 'var(--turquoise)' : 'var(--panel-bg)'}; color:${!zoomMode ? '#000' : '#fff'}">Pixel/Blur Mode</button>
          </div>
          <div style="height:200px; width:100%; overflow:hidden; position:relative; border:2px solid var(--purple-border); border-radius:8px; background:#000; display:flex; align-items:center; justify-content:center;">
            <img id="guess-img" src="${target.image}" style="max-height:100%; transition: all 0.3s ease; ${
              zoomMode 
                ? `transform: scale(12) translate(${(clueStep % 3 - 1) * 15}%, ${(clueStep % 2 - 1) * 15}%);` 
                : `filter: blur(${Math.max(0, 18 - clueStep * 3)}px) pixelate(${Math.max(1, 20 - clueStep * 3)}px);`
            }">
          </div>
          <div style="margin-top:10px; background:var(--panel-bg); padding:10px; border-radius:8px;">
            <div style="font-weight:bold; color:var(--yellow); font-size:0.85rem; margin-bottom:4px;">REVEALED CLUES:</div>
            ${revealedClues.map(c => `<div style="font-size:0.8rem; color:var(--turquoise);">• ${c}</div>`).join('')}
          </div>
          <div class="autocomplete-wrapper" style="margin-top:10px;">
            <input type="text" id="guess-input" class="global-search-input" placeholder="Type game title..." oninput="onGuessInput(this.value)">
            <div id="guess-autocomplete" class="autocomplete-list"></div>
          </div>
          <div style="display:flex; gap:8px; margin-top:10px;">
            <button class="game-btn" onclick="nextClue()" ${clueStep >= clues.length - 1 ? 'disabled' : ''} style="flex:1;">Next Clue (${clueStep + 1}/${clues.length})</button>
            <button class="game-btn" onclick="giveUpGuess()" style="flex:1; background:var(--magenta);">Give Up</button>
          </div>
        `;
      }

      window.toggleGuessMode = function(isZoom) {
        zoomMode = isZoom;
        render();
      };

      window.nextClue = function() {
        if (clueStep < clues.length - 1) {
          clueStep++;
          render();
        }
      };

      window.onGuessInput = function(val) {
        const list = document.getElementById('guess-autocomplete');
        if (!val || val.length < 2) { list.innerHTML = ''; return; }
        const matches = rawCollection.filter(g => g.title.toLowerCase().includes(val.toLowerCase())).slice(0, 5);
        list.innerHTML = matches.map(m => `<div class="autocomplete-item" onclick="submitGuess('${m.title.replace(/'/g, "\\'")}')">${m.title}</div>`).join('');
      };

      window.submitGuess = function(title) {
        if (title.toLowerCase().trim() === target.title.toLowerCase().trim()) {
          alert(`🎉 Correct! The game was indeed ${target.title}!`);
          launchGame('guess_game');
        } else {
          alert(`❌ Wrong answer! Try another clue or guess again.`);
        }
      };

      window.giveUpGuess = function() {
        alert(`The answer was: ${target.title}`);
        launchGame('guess_game');
      };

      render();
    }

    // 3. HIGHER OR LOWER (Ratings/Weight Hidden Until Choice, Select Either Game)
    function initHigherLower(container) {
      let score = 0;
      let pool = shuffleArray([...rawCollection].filter(g => g.weight > 0 && g.bgg_rating > 0));
      let gameA = pool[0];
      let gameB = pool[1];
      let statMode = Math.random() > 0.5 ? 'weight' : 'bgg_rating';

      function render(revealed = false, chosenGame = null) {
        const statLabel = statMode === 'weight' ? 'Weight / Complexity' : 'BGG Rating';
        const valA = gameA[statMode];
        const valB = gameB[statMode];

        container.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="modal-title" style="margin:0;">📈 Higher or Lower (Streak: ${score})</div>
            <button class="expansion-close-btn" onclick="returnToArcadeMenu()">Back</button>
          </div>
          <p style="text-align:center; color:var(--yellow); font-weight:bold; margin-top:8px;">Which game has the HIGHER ${statLabel}?</p>
          <div class="hl-container">
            <div class="hl-card">
              <img src="${gameA.thumbnail || gameA.image}">
              <div style="font-weight:bold; color:var(--turquoise); font-size:0.9rem;">${gameA.title}</div>
              <div style="font-size:1.1rem; font-weight:900; color:var(--yellow); margin:8px 0;">
                ${revealed ? `${statLabel}: ${valA}` : '???'}
              </div>
              <button class="game-btn" style="width:100%;" ${revealed ? 'disabled' : `onclick="makeHLChoice('A')"`}>Select Game 1</button>
            </div>
            <div class="hl-card">
              <img src="${gameB.thumbnail || gameB.image}">
              <div style="font-weight:bold; color:var(--turquoise); font-size:0.9rem;">${gameB.title}</div>
              <div style="font-size:1.1rem; font-weight:900; color:var(--yellow); margin:8px 0;">
                ${revealed ? `${statLabel}: ${valB}` : '???'}
              </div>
              <button class="game-btn" style="width:100%;" ${revealed ? 'disabled' : `onclick="makeHLChoice('B')"`}>Select Game 2</button>
            </div>
          </div>
          ${revealed ? `
            <div style="text-align:center; margin-top:10px;">
              <button class="game-btn" onclick="nextHLRound()">Next Pair ➔</button>
            </div>
          ` : ''}
        `;
      }

      window.makeHLChoice = function(choice) {
        const valA = gameA[statMode];
        const valB = gameB[statMode];
        let correct = false;

        if (choice === 'A' && valA >= valB) correct = true;
        if (choice === 'B' && valB >= valA) correct = true;

        if (correct) {
          score++;
          render(true, choice);
        } else {
          alert(`Game Over! Final Streak: ${score}`);
          launchGame('higher_lower');
        }
      };

      window.nextHLRound = function() {
        pool = shuffleArray(pool);
        gameA = pool[0];
        gameB = pool[1];
        statMode = Math.random() > 0.5 ? 'weight' : 'bgg_rating';
        render(false);
      };

      render(false);
    }

    // 4. CONNECTIONS
    function initConnections(container) {
      let strikes = 5;
      let selectedIndices = [];

      // Category logic: Generates groups dynamically from shared properties
      const categories = [
        { name: "BGG Rating ~ 7.5 - 7.9", filter: g => g.bgg_rating >= 7.5 && g.bgg_rating < 8.0 },
        { name: "BGG Rating 8.0+", filter: g => g.bgg_rating >= 8.0 },
        { name: "Weight <= 2.0 (Light)", filter: g => g.weight > 0 && g.weight <= 2.0 },
        { name: "Weight >= 3.5 (Heavy)", filter: g => g.weight >= 3.5 },
        { name: "Mechanic: Hand Management", filter: g => g.mechanics.includes("Hand Management") },
        { name: "Theme: Sci-Fi / Space", filter: g => g.themes.some(t => t.toLowerCase().includes("sci-fi") || t.toLowerCase().includes("space")) },
        { name: "Published Pre-2015", filter: g => g.year > 0 && g.year < 2015 }
      ];

      const validCats = shuffleArray(categories).filter(c => rawCollection.filter(c.filter).length >= 4).slice(0, 4);
      
      let gridCards = [];
      validCats.forEach((cat, catIdx) => {
        const matches = shuffleArray(rawCollection.filter(cat.filter)).slice(0, 4);
        matches.forEach(m => gridCards.push({ game: m, catIdx, catName: cat.name }));
      });

      gridCards = shuffleArray(gridCards);

      function render() {
        container.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="modal-title" style="margin:0;">🧩 Connections</div>
            <button class="expansion-close-btn" onclick="returnToArcadeMenu()">Back</button>
          </div>
          <div style="text-align:center; color:var(--magenta); font-weight:bold; margin:6px 0;">Strikes Remaining: ${'❤️'.repeat(strikes)}</div>
          <div class="conn-grid">
            ${gridCards.map((c, idx) => `
              <div class="conn-card ${selectedIndices.includes(idx) ? 'selected' : ''}" onclick="toggleConnCard(${idx})">
                ${c.game.title}
              </div>
            `).join('')}
          </div>
          <div style="display:flex; gap:8px; margin-top:12px;">
            <button class="game-btn" onclick="submitConnGroup()" style="flex:1;" ${selectedIndices.length !== 4 ? 'disabled' : ''}>Submit Group</button>
            <button class="game-btn" onclick="deselectConnAll()" style="flex:1; background:var(--purple-border);">Deselect All</button>
          </div>
        `;
      }

      window.toggleConnCard = function(idx) {
        if (selectedIndices.includes(idx)) {
          selectedIndices = selectedIndices.filter(i => i !== idx);
        } else if (selectedIndices.length < 4) {
          selectedIndices.push(idx);
        }
        render();
      };

      window.deselectConnAll = function() {
        selectedIndices = [];
        render();
      };

      window.submitConnGroup = function() {
        const firstCat = gridCards[selectedIndices[0]].catIdx;
        const allSame = selectedIndices.every(i => gridCards[i].catIdx === firstCat);

        if (allSame) {
          alert(`✨ Category Cleared: ${gridCards[selectedIndices[0]].catName}`);
          gridCards = gridCards.filter((_, idx) => !selectedIndices.includes(idx));
          selectedIndices = [];
          if (gridCards.length === 0) {
            alert("🎉 CONGRATULATIONS! You solved Connections!");
            launchGame('connections');
          }
        } else {
          strikes--;
          alert("❌ Incorrect Grouping!");
          if (strikes <= 0) {
            alert("Game Over! Ran out of strikes.");
            launchGame('connections');
          }
        }
        render();
      };

      render();
    }

    // 5. 3x3 GRID (4 Intersecting Rules, 1 Center Overlap Answer)
    function initGrid4x3(container) {
      let strikes = 4;
      const boardPool = shuffleArray([...rawCollection]).slice(0, 9);
      const centerGame = boardPool[4]; // Center element

      container.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div class="modal-title" style="margin:0;">🌀 3X3 Grid</div>
          <button class="expansion-close-btn" onclick="returnToArcadeMenu()">Back</button>
        </div>
        <div style="text-align:center; color:var(--magenta); font-weight:bold; margin:6px 0;">Strikes Remaining: ${'⚡'.repeat(strikes)}</div>
        <p style="font-size:0.8rem; color:var(--text-muted); text-align:center;">Find the card that fits ALL intersecting row & column criteria!</p>
        <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-top:10px;">
          ${boardPool.map((g, idx) => `
            <div class="conn-card" onclick="check3x3Choice(${idx})" style="flex-direction:column; padding:6px; height:90px;">
              <img src="${g.thumbnail || g.image}" style="height:45px; object-fit:contain;">
              <span style="font-size:0.7rem; margin-top:4px;">${g.title}</span>
            </div>
          `).join('')}
        </div>
      `;

      window.check3x3Choice = function(idx) {
        if (idx === 4) {
          alert("🎉 Correct! You identified the intersecting master answer!");
          launchGame('glipped');
        } else {
          strikes--;
          alert(`❌ Incorrect! ${strikes} strikes remaining.`);
          if (strikes <= 0) {
            alert("Game Over!");
            launchGame('glipped');
          }
        }
      };
    }

    // 6. COLLECTION CROSSWORD (Keyboard Nav, 2 Clue Identifiers, Numbered Cells & Grid Rules)
    function initCrossword(container) {
      const pool = shuffleArray([...rawCollection].filter(g => g.title.length >= 3 && g.title.length <= 10)).slice(0, 5);

      const clues = pool.map((g, idx) => {
        let idPair = '';
        if (idx % 3 === 0) idPair = `Year: ${g.year} | Publisher: ${g.publisher}`;
        else if (idx % 3 === 1) idPair = `Designer: ${g.designer} | Weight: ${g.weight}`;
        else idPair = `BGG Rating: ${g.bgg_rating} | Players: ${g.min_players}-${g.max_players}`;

        return {
          num: idx + 1,
          title: g.title.toUpperCase().replace(/[^A-Z0-9]/g, ''),
          clue: idPair
        };
      });

      let gridHtml = '';
      clues.forEach((c, rowIdx) => {
        gridHtml += `<div style="display:flex; gap:4px; margin-bottom:4px; align-items:center;">
          <span style="width:24px; font-weight:bold; color:var(--yellow); font-size:0.8rem;">#${c.num}</span>`;
        for (let colIdx = 0; colIdx < c.title.length; colIdx++) {
          gridHtml += `<input type="text" maxlength="1" class="crossword-cell" id="cw-${rowIdx}-${colIdx}" onkeyup="onCrosswordKey(event, ${rowIdx}, ${colIdx}, ${c.title.length})">`;
        }
        gridHtml += `</div>`;
      });

      container.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div class="modal-title" style="margin:0;">✏️ Collection Crossword</div>
          <button class="expansion-close-btn" onclick="returnToArcadeMenu()">Back</button>
        </div>
        <div style="margin:10px 0; background:var(--panel-bg); padding:10px; border-radius:8px;">
          ${clues.map(c => `<div style="font-size:0.8rem; margin-bottom:4px;"><b style="color:var(--yellow);">#${c.num}:</b> <span style="color:var(--turquoise);">${c.clue}</span></div>`).join('')}
        </div>
        <div class="crossword-board">
          ${gridHtml}
        </div>
        <button class="game-btn" onclick="checkCrosswordAnswers()" style="width:100%; margin-top:12px;">Check Crossword</button>
      `;

      window.onCrosswordKey = function(e, r, c, maxLen) {
        if (e.key >= 'a' && e.key <= 'z' || e.key >= 'A' && e.key <= 'Z' || e.key >= '0' && e.key <= '9') {
          if (c < maxLen - 1) {
            const nextCell = document.getElementById(`cw-${r}-${c+1}`);
            if (nextCell) nextCell.focus();
          }
        } else if (e.key === 'Backspace' && c > 0) {
          const prevCell = document.getElementById(`cw-${r}-${c-1}`);
          if (prevCell) prevCell.focus();
        }
      };

      window.checkCrosswordAnswers = function() {
        let allCorrect = true;
        clues.forEach((c, r) => {
          let entered = '';
          for (let col = 0; col < c.title.length; col++) {
            const val = (document.getElementById(`cw-${r}-${col}`).value || '').toUpperCase();
            entered += val;
          }
          if (entered !== c.title) allCorrect = false;
        });

        if (allCorrect) {
          alert("🎉 Congratulations! You solved the crossword perfectly!");
          launchGame('crossword');
        } else {
          alert("❌ Some answers are incorrect or incomplete. Keep trying!");
        }
      };
    }

    function shuffleArray(array) {
      const arr = [...array];
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
      }
      return arr;
    }
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print("--- STARTING FLASK DEVELOPMENT SERVER ---")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

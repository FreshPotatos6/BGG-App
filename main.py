import json
import os
import re
import random
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
    .crossword-cell-wrapper { position: relative; width: 32px; height: 32px; }
    .crossword-cell-wrapper .cell-number { position: absolute; top: 1px; left: 2px; font-size: 0.55rem; color: var(--turquoise); font-weight: bold; pointer-events: none; }
    .crossword-cell { width: 100%; height: 100%; background: var(--bg); border: 1px solid var(--purple-border); text-align: center; font-weight: bold; text-transform: uppercase; color: var(--yellow); font-size: 1rem; outline: none; }
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
            <h3>🌀 3X3 Grid</h3>
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

    // --- MINI GAMES ENGINE ---
    function launchGame(gameType) {
      document.getElementById('arcade-view-launcher').style.display = 'none';
      const container = document.getElementById('arcade-game-container');
      container.style.display = 'block';
      container.innerHTML = '';

      if (gameType === 'blind_ranking') initBlindRanking(container);
      else if (gameType === 'guess_game') initGuessGame(container);
      else if (gameType === 'higher_lower') initHigherLower(container);
      else if (gameType === 'connections') initConnections(container);
      else if (gameType === 'glipped') init3x3Grid(container);
      else if (gameType === 'crossword') initCrossword(container);
    }

    // 1. BLIND RANKING
    function initBlindRanking(container) {
      let pool = [...rawCollection];
      if (pool.length < 10) pool = [...games];
      let shuffled = [...pool].sort(() => 0.5 - Math.random()).slice(0, 10);
      let rankings = new Array(10).fill(null);
      let currentIndex = 0;

      function render() {
        if (currentIndex >= 10) {
          let score = 0;
          let maxPossible = 0;
          for (let i = 0; i < 10; i++) {
            for (let j = i + 1; j < 10; j++) {
              maxPossible++;
              const rI = rankings[i].bgg_rating || 0;
              const rJ = rankings[j].bgg_rating || 0;
              if (rI >= rJ) score++;
            }
          }
          let pct = Math.round((score / maxPossible) * 100);
          container.innerHTML = `
            <div style="text-align:center;">
              <h2 style="color: var(--yellow);">Game Over!</h2>
              <p style="margin: 10px 0; font-size: 1.2rem;">Accuracy Score: <strong style="color: var(--turquoise);">${pct}%</strong></p>
              <div class="blind-grid-columns" style="margin: 15px 0;">
                <div>
                  ${rankings.slice(0, 5).map((g, idx) => `
                    <div style="background: var(--panel-bg); border: 1px solid var(--purple-border); border-radius: 6px; padding: 6px 10px; margin-bottom: 6px; font-size: 0.85rem; text-align: left;">
                      <strong style="color: var(--yellow);">${idx + 1}.</strong> ${g.title} <span style="color: var(--turquoise); float: right;">★ ${g.bgg_rating ? g.bgg_rating.toFixed(1) : 'N/A'}</span>
                    </div>
                  `).join('')}
                </div>
                <div>
                  ${rankings.slice(5, 10).map((g, idx) => `
                    <div style="background: var(--panel-bg); border: 1px solid var(--purple-border); border-radius: 6px; padding: 6px 10px; margin-bottom: 6px; font-size: 0.85rem; text-align: left;">
                      <strong style="color: var(--yellow);">${idx + 6}.</strong> ${g.title} <span style="color: var(--turquoise); float: right;">★ ${g.bgg_rating ? g.bgg_rating.toFixed(1) : 'N/A'}</span>
                    </div>
                  `).join('')}
                </div>
              </div>
              <div style="display: flex; gap: 8px;">
                <button class="game-btn" style="flex:1;" onclick="launchGame('blind_ranking')">Play Again</button>
                <button class="game-btn" style="flex:1; background: var(--panel-bg); border: 1px solid var(--purple-border);" onclick="returnToArcadeMenu()">Menu</button>
              </div>
            </div>
          `;
          return;
        }

        const currentGame = shuffled[currentIndex];
        container.innerHTML = `
          <div class="game-board">
            <div class="game-status-bar">
              <span>Game ${currentIndex + 1} / 10</span>
              <button class="game-btn" style="padding: 2px 8px; font-size: 0.75rem;" onclick="returnToArcadeMenu()">Exit</button>
            </div>
            <div style="display: flex; gap: 12px; background: var(--panel-bg); padding: 10px; border-radius: 8px; align-items: center;">
              <img src="${currentGame.thumbnail || currentGame.image}" style="width: 70px; height: 70px; object-fit: contain;">
              <div>
                <h3 style="color: var(--yellow); font-size: 1.1rem;">${currentGame.title}</h3>
                <p style="color: var(--text-muted); font-size: 0.8rem;">${currentGame.year || ''} • ${currentGame.publisher || ''}</p>
              </div>
            </div>
            <p style="font-size: 0.85rem; color: var(--turquoise);">Assign to a rank (1 = Highest BGG Rating, 10 = Lowest BGG Rating):</p>
            <div class="blind-grid-columns">
              <div style="display: flex; flex-direction: column; gap: 6px;">
                ${[0,1,2,3,4].map(idx => `
                  <button class="game-btn" style="text-align: left; background: ${rankings[idx] ? 'var(--card-bg)' : 'var(--panel-bg)'}; border: 1px solid var(--purple-border); color: var(--text);" ${rankings[idx] ? 'disabled' : ''} onclick="placeBlindRank(${idx})">
                    <strong style="color: var(--yellow);">${idx + 1}.</strong> ${rankings[idx] ? `${rankings[idx].title} (★ ${rankings[idx].bgg_rating ? rankings[idx].bgg_rating.toFixed(1) : 'N/A'})` : '<em>Empty Slot</em>'}
                  </button>
                `).join('')}
              </div>
              <div style="display: flex; flex-direction: column; gap: 6px;">
                ${[5,6,7,8,9].map(idx => `
                  <button class="game-btn" style="text-align: left; background: ${rankings[idx] ? 'var(--card-bg)' : 'var(--panel-bg)'}; border: 1px solid var(--purple-border); color: var(--text);" ${rankings[idx] ? 'disabled' : ''} onclick="placeBlindRank(${idx})">
                    <strong style="color: var(--yellow);">${idx + 6}.</strong> ${rankings[idx] ? `${rankings[idx].title} (★ ${rankings[idx].bgg_rating ? rankings[idx].bgg_rating.toFixed(1) : 'N/A'})` : '<em>Empty Slot</em>'}
                  </button>
                `).join('')}
              </div>
            </div>
          </div>
        `;
      }

      window.placeBlindRank = function(slotIdx) {
        if (rankings[slotIdx] === null) {
          rankings[slotIdx] = shuffled[currentIndex];
          currentIndex++;
          render();
        }
      };

      render();
    }

    // 2. GUESS THE GAME
    function initGuessGame(container) {
      let pool = rawCollection.filter(g => g.image || g.thumbnail);
      if (!pool.length) pool = games;
      let target = pool[Math.floor(Math.random() * pool.length)];
      let mode = Math.random() > 0.5 ? 'blur' : 'zoom';
      let revealStep = 1;

      function render() {
        const pCountText = target.min_players === target.max_players ? `${target.min_players}` : `${target.min_players}-${target.max_players}`;
        const clues = [
          `Year Published: ${target.year || 'Unknown'}`,
          `Player Count: ${pCountText}`,
          `Publisher: ${target.publisher || 'Unknown'}`,
          `Weight: ${target.weight ? target.weight.toFixed(1) : 'N/A'}`,
          `BGG Rating: ${target.bgg_rating ? target.bgg_rating.toFixed(1) : 'N/A'}`,
          `Designer: ${target.designer || 'Unknown'}`
        ];

        let imgStyle = "width: 100%; height: 200px; object-fit: contain; transition: all 0.3s ease;";
        if (mode === 'blur') {
          let blurAmount = Math.max(0, 24 - (revealStep * 4));
          imgStyle += ` filter: blur(${blurAmount}px);`;
        } else {
          let scaleVal = Math.max(1, 10 - (revealStep * 1.5));
          imgStyle += ` transform: scale(${scaleVal}); transform-origin: center center; clip-path: inset(0px);`;
        }

        container.innerHTML = `
          <div class="game-board">
            <div class="game-status-bar">
              <span>Guess The Game (${mode.toUpperCase()} Mode)</span>
              <button class="game-btn" style="padding: 2px 8px; font-size: 0.75rem;" onclick="returnToArcadeMenu()">Exit</button>
            </div>
            <div style="background: #000; border: 2px solid var(--purple-border); border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center; height: 200px;">
              <img src="${target.image || target.thumbnail}" style="${imgStyle}">
            </div>
            <div style="background: var(--panel-bg); padding: 10px; border-radius: 8px; border: 1px solid var(--purple-border);">
              <h4 style="color: var(--yellow); font-size: 0.85rem; margin-bottom: 6px;">CLUES (${revealStep} / 6):</h4>
              <ul style="padding-left: 18px; font-size: 0.82rem; color: var(--text-muted);">
                ${clues.slice(0, revealStep).map(c => `<li style="margin-bottom: 3px;">${c}</li>`).join('')}
              </ul>
            </div>
            <div class="autocomplete-wrapper">
              <input type="text" id="guess-input" placeholder="Type game title..." style="width: 100%; padding: 8px; background: var(--panel-bg); border: 1px solid var(--purple-border); border-radius: 6px; color: var(--text); outline: none;">
              <div id="guess-autocomplete" class="autocomplete-list" style="display:none;"></div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="game-btn" style="flex: 1;" onclick="submitGuessGame()">Submit Guess</button>
              ${revealStep < 6 ? `<button class="game-btn" style="background: var(--panel-bg); border: 1px solid var(--purple-border);" onclick="nextGuessClue()">Give Clue</button>` : ''}
              <button class="game-btn" style="background: var(--magenta);" onclick="giveUpGuess()">Give Up</button>
            </div>
          </div>
        `;

        const input = document.getElementById('guess-input');
        const autoList = document.getElementById('guess-autocomplete');
        input.addEventListener('input', () => {
          let val = input.value.toLowerCase().trim();
          if (!val) { autoList.style.display = 'none'; return; }
          let matches = rawCollection.filter(g => g.title.toLowerCase().includes(val)).slice(0, 5);
          if (!matches.length) { autoList.style.display = 'none'; return; }
          autoList.innerHTML = matches.map(m => `<div class="autocomplete-item" onclick="selectGuessMatch('${m.title.replace(/'/g, "\\'")}')">${m.title}</div>`).join('');
          autoList.style.display = 'block';
        });
      }

      window.selectGuessMatch = function(title) {
        document.getElementById('guess-input').value = title;
        document.getElementById('guess-autocomplete').style.display = 'none';
      };

      window.nextGuessClue = function() {
        if (revealStep < 6) { revealStep++; render(); }
      };

      window.submitGuessGame = function() {
        const val = document.getElementById('guess-input').value.toLowerCase().trim();
        if (val === target.title.toLowerCase().trim()) {
          container.innerHTML = `
            <div style="text-align: center; padding: 20px;">
              <h2 style="color: var(--turquoise);">🎉 Correct!</h2>
              <p style="margin: 10px 0; color: var(--yellow); font-weight: bold; font-size: 1.2rem;">${target.title}</p>
              <img src="${target.thumbnail || target.image}" style="max-height: 150px; object-fit: contain; margin-bottom: 15px;">
              <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 15px;">You solved it on clue step ${revealStep} of 6!</p>
              <button class="game-btn" onclick="launchGame('guess_game')">Play Next Game</button>
            </div>
          `;
        } else {
          alert("Not quite right! Try again or reveal another clue.");
        }
      };

      window.giveUpGuess = function() {
        container.innerHTML = `
          <div style="text-align: center; padding: 20px;">
            <h2 style="color: var(--magenta);">Answer Revealed!</h2>
            <p style="margin: 10px 0; color: var(--yellow); font-weight: bold; font-size: 1.2rem;">${target.title}</p>
            <img src="${target.thumbnail || target.image}" style="max-height: 150px; object-fit: contain; margin-bottom: 15px;">
            <button class="game-btn" onclick="launchGame('guess_game')">Try Another</button>
          </div>
        `;
      };

      render();
    }

    // 3. HIGHER OR LOWER
    function initHigherLower(container) {
      let pool = [...rawCollection];
      if (pool.length < 2) pool = [...games];

      let streak = 0;
      let metric = Math.random() > 0.5 ? 'weight' : 'bgg_rating';
      let gameA = pool[Math.floor(Math.random() * pool.length)];
      let gameB = pool[Math.floor(Math.random() * pool.length)];
      while (gameB.id === gameA.id) {
        gameB = pool[Math.floor(Math.random() * pool.length)];
      }

      function render(revealed = false, chosenGame = null) {
        const metricName = metric === 'weight' ? 'Weight / Complexity' : 'BGG Rating';
        const valA = metric === 'weight' ? (gameA.weight || 0) : (gameA.bgg_rating || 0);
        const valB = metric === 'weight' ? (gameB.weight || 0) : (gameB.bgg_rating || 0);

        container.innerHTML = `
          <div class="game-board">
            <div class="game-status-bar">
              <span>Higher or Lower (${metricName})</span>
              <span>Streak: <strong style="color: var(--yellow);">${streak}</strong></span>
            </div>
            <p style="text-align: center; font-size: 0.9rem; color: var(--turquoise); margin-top: 5px;">
              Which game has the <strong>HIGHER ${metricName.toUpperCase()}</strong>?
            </p>
            <div class="hl-container">
              <div class="hl-card">
                <img src="${gameA.thumbnail || gameA.image}">
                <h4 style="color: var(--yellow); font-size: 0.9rem;">${gameA.title}</h4>
                <p style="color: var(--text-muted); font-size: 0.8rem; margin: 6px 0;">${metricName}</p>
                <div style="font-size: 1.2rem; font-weight: 900; color: var(--turquoise);">
                  ${revealed ? valA.toFixed(1) : '???'}
                </div>
                ${!revealed ? `<button class="game-btn" style="margin-top: 10px; width: 100%;" onclick="guessHigherLower('A')">Select This</button>` : ''}
              </div>

              <div style="font-weight: 900; color: var(--magenta); font-size: 1.2rem;">VS</div>

              <div class="hl-card">
                <img src="${gameB.thumbnail || gameB.image}">
                <h4 style="color: var(--yellow); font-size: 0.9rem;">${gameB.title}</h4>
                <p style="color: var(--text-muted); font-size: 0.8rem; margin: 6px 0;">${metricName}</p>
                <div style="font-size: 1.2rem; font-weight: 900; color: var(--turquoise);">
                  ${revealed ? valB.toFixed(1) : '???'}
                </div>
                ${!revealed ? `<button class="game-btn" style="margin-top: 10px; width: 100%;" onclick="guessHigherLower('B')">Select This</button>` : ''}
              </div>
            </div>
            ${revealed ? `
              <div style="text-align: center; margin-top: 10px;">
                <button class="game-btn" style="padding: 10px 20px;" onclick="nextHigherLowerRound()">Next Round →</button>
              </div>
            ` : ''}
          </div>
        `;
      }

      window.guessHigherLower = function(choice) {
        const valA = metric === 'weight' ? (gameA.weight || 0) : (gameA.bgg_rating || 0);
        const valB = metric === 'weight' ? (gameB.weight || 0) : (gameB.bgg_rating || 0);
        
        let correct = false;
        if (choice === 'A' && valA >= valB) correct = true;
        if (choice === 'B' && valB >= valA) correct = true;

        if (correct) {
          streak++;
          render(true, choice);
        } else {
          render(true, choice);
          setTimeout(() => {
            alert(`Game Over! Final Streak: ${streak}`);
            streak = 0;
            nextHigherLowerRound();
          }, 600);
        }
      };

      window.nextHigherLowerRound = function() {
        metric = Math.random() > 0.5 ? 'weight' : 'bgg_rating';
        gameA = gameB;
        let newB = pool[Math.floor(Math.random() * pool.length)];
        while (newB.id === gameA.id) {
          newB = pool[Math.floor(Math.random() * pool.length)];
        }
        gameB = newB;
        render(false);
      };

      render(false);
    }

    // 4. CONNECTIONS
    function initConnections(container) {
      let strikes = 0;
      let selectedIds = [];
      let solvedCategories = [];

      let possibleCategories = [
        { name: "Mechanic: Deck Building", check: g => g.mechanics && g.mechanics.some(m => m.toLowerCase().includes('deck')) },
        { name: "Mechanic: Worker Placement", check: g => g.mechanics && g.mechanics.some(m => m.toLowerCase().includes('worker placement')) },
        { name: "Theme: Sci-Fi / Space", check: g => g.themes && g.themes.some(t => t.toLowerCase().includes('sci-fi') || t.toLowerCase().includes('space')) },
        { name: "Theme: Fantasy", check: g => g.themes && g.themes.some(t => t.toLowerCase().includes('fantasy')) },
        { name: "Category: Card Game", check: g => g.categories && g.categories.some(c => c.toLowerCase().includes('card')) },
        { name: "High Complexity (Weight > 3.2)", check: g => g.weight >= 3.2 },
        { name: "Light Complexity (Weight < 2.0)", check: g => g.weight > 0 && g.weight <= 2.0 },
        { name: "Published Before 2010", check: g => g.year > 0 && g.year < 2010 },
        { name: "Published 2020 or Later", check: g => g.year >= 2020 }
      ];

      let selectedGroups = [];
      let usedGameIds = new Set();
      let shuffledCategories = [...possibleCategories].sort(() => 0.5 - Math.random());

      for (let cat of shuffledCategories) {
        let matches = rawCollection.filter(g => !usedGameIds.has(g.id) && cat.check(g));
        if (matches.length >= 4) {
          let chosenFour = matches.sort(() => 0.5 - Math.random()).slice(0, 4);
          chosenFour.forEach(g => usedGameIds.add(g.id));
          selectedGroups.push({ category: cat.name, games: chosenFour });
          if (selectedGroups.length === 4) break;
        }
      }

      if (selectedGroups.length < 4) {
        container.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted);">Not enough varied games in collection to build a Connections puzzle!</div>`;
        return;
      }

      let allBoardGames = [];
      selectedGroups.forEach(grp => {
        grp.games.forEach(g => {
          allBoardGames.push({ ...g, groupName: grp.category });
        });
      });
      allBoardGames.sort(() => 0.5 - Math.random());

      function render() {
        container.innerHTML = `
          <div class="game-board">
            <div class="game-status-bar">
              <span>Connections</span>
              <span>Strikes: <strong style="color: var(--magenta);">${'❌ '.repeat(strikes)}</strong> (${5 - strikes} left)</span>
            </div>
            <p style="font-size: 0.8rem; color: var(--text-muted); text-align: center;">Select 4 games that share a hidden category feature.</p>
            <div class="conn-grid">
              ${allBoardGames.map(g => {
                const isSelected = selectedIds.includes(g.id);
                const isSolved = solvedCategories.includes(g.groupName);
                return `
                  <div class="conn-card ${isSelected ? 'selected' : ''} ${isSolved ? 'solved' : ''}" onclick="toggleConnCard('${g.id}')">
                    ${g.title}
                  </div>
                `;
              }).join('')}
            </div>
            <div style="display: flex; gap: 8px; margin-top: 10px;">
              <button class="game-btn" style="flex:1;" onclick="submitConnGuess()">Submit</button>
              <button class="game-btn" style="flex:1; background: var(--panel-bg); border: 1px solid var(--purple-border);" onclick="deselectConnAll()">Deselect All</button>
            </div>
          </div>
        `;
      }

      window.toggleConnCard = function(id) {
        let gameObj = allBoardGames.find(g => g.id === id);
        if (solvedCategories.includes(gameObj.groupName)) return;

        if (selectedIds.includes(id)) {
          selectedIds = selectedIds.filter(x => x !== id);
        } else {
          if (selectedIds.length < 4) selectedIds.push(id);
        }
        render();
      };

      window.deselectConnAll = function() {
        selectedIds = [];
        render();
      };

      window.submitConnGuess = function() {
        if (selectedIds.length !== 4) {
          alert("Select exactly 4 games!");
          return;
        }

        let selectedObjs = allBoardGames.filter(g => selectedIds.includes(g.id));
        let firstGroup = selectedObjs[0].groupName;
        let isMatch = selectedObjs.every(g => g.groupName === firstGroup);

        if (isMatch) {
          solvedCategories.push(firstGroup);
          selectedIds = [];
          if (solvedCategories.length === 4) {
            alert("🎉 Incredible! You solved all 4 Connections categories!");
          }
        } else {
          strikes++;
          if (strikes >= 5) {
            alert("Game Over! Max strikes reached.");
          } else {
            alert("Incorrect grouping!");
          }
        }
        render();
      };

      render();
    }

    // 5. 3X3 GRID (1 ANSWER IN ALL 4 CATEGORIES)
    function init3x3Grid(container) {
      let strikes = 0;
      let categories = [
        { name: "Top Rated (BGG > 7.5)", check: g => g.bgg_rating >= 7.5 },
        { name: "High Weight (> 3.0)", check: g => g.weight >= 3.0 },
        { name: "Multiplayer (> 4 Players)", check: g => g.max_players >= 4 },
        { name: "Modern Era (>= 2018)", check: g => g.year >= 2018 }
      ];

      let candidateCenter = rawCollection.find(g => categories.every(c => c.check(g)));
      if (!candidateCenter) candidateCenter = rawCollection[0];

      let grid3x3 = new Array(9).fill(null);
      grid3x3[4] = candidateCenter; 

      let used = new Set([candidateCenter.id]);
      for (let i = 0; i < 9; i++) {
        if (i === 4) continue;
        let randomGame = rawCollection.find(g => !used.has(g.id));
        if (randomGame) {
          grid3x3[i] = randomGame;
          used.add(randomGame.id);
        }
      }

      container.innerHTML = `
        <div class="game-board">
          <div class="game-status-bar">
            <span>3X3 Grid Solver</span>
            <span>Strikes: <strong style="color: var(--magenta);">${'❌ '.repeat(strikes)}</strong></span>
          </div>
          <p style="font-size: 0.82rem; color: var(--turquoise); text-align: center;">
            Find the SINGLE game in the 3x3 grid that satisfies ALL 4 active category conditions!
          </p>
          <div style="background: var(--panel-bg); padding: 8px; border-radius: 6px; font-size: 0.78rem; border: 1px solid var(--purple-border);">
            <strong>4 Active Rules:</strong>
            <ul style="padding-left: 18px; color: var(--yellow);">
              ${categories.map(c => `<li>${c.name}</li>`).join('')}
            </ul>
          </div>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px;">
            ${grid3x3.map((g, idx) => `
              <div class="conn-card" onclick="check3x3Answer(${idx})">
                ${g ? g.title : 'Empty'}
              </div>
            `).join('')}
          </div>
        </div>
      `;

      window.check3x3Answer = function(idx) {
        let selectedGame = grid3x3[idx];
        let wins = categories.every(c => c.check(selectedGame));
        if (wins) {
          alert(`🎉 Correct! ${selectedGame.title} meets all 4 criteria!`);
          launchGame('glipped');
        } else {
          strikes++;
          alert(`Incorrect! ${selectedGame.title} does not fit all 4 rules.`);
          if (strikes >= 4) {
            alert("Max strikes reached! Resetting puzzle.");
            launchGame('glipped');
          }
        }
      };
    }

    // 6. COLLECTION CROSSWORD
    function initCrossword(container) {
      let suitableGames = rawCollection.filter(g => g.title && g.title.length >= 3 && g.title.length <= 12 && /^[A-Za-z\s]+$/.test(g.title));
      if (suitableGames.length < 5) suitableGames = games;

      let boardSize = 12;
      let gridCells = Array.from({ length: boardSize }, () => Array(boardSize).fill(null));

      let placedAcross = [];
      let placedDown = [];

      let centerGame = suitableGames[Math.floor(Math.random() * suitableGames.length)];
      let centerClean = centerGame.title.replace(/\s+/g, '').toUpperCase();
      let startCol = Math.floor((boardSize - centerClean.length) / 2);
      let r0 = 4;

      for (let i = 0; i < centerClean.length; i++) {
        gridCells[r0][startCol + i] = { char: centerClean[i], num: i === 0 ? 1 : null };
      }

      function getCluePair(gameObj) {
        const pCount = gameObj.min_players === gameObj.max_players ? `${gameObj.min_players}` : `${gameObj.min_players}-${gameObj.max_players}`;
        const pairs = [
          `Year: ${gameObj.year || 'N/A'}, Publisher: ${gameObj.publisher || 'Unknown'}`,
          `Designer: ${gameObj.designer || 'Unknown'}, Weight: ${gameObj.weight ? gameObj.weight.toFixed(1) : 'N/A'}`,
          `BGG Rating: ${gameObj.bgg_rating ? gameObj.bgg_rating.toFixed(1) : 'N/A'}, Players: ${pCount}`
        ];
        return pairs[Math.floor(Math.random() * pairs.length)];
      }

      placedAcross.push({ num: 1, title: centerClean, game: centerGame, row: r0, col: startCol, clue: getCluePair(centerGame) });

      let clueCounter = 2;
      for (let game of suitableGames) {
        if (game.id === centerGame.id) continue;
        let clean = game.title.replace(/\s+/g, '').toUpperCase();

        for (let i = 0; i < centerClean.length; i++) {
          let charToMatch = centerClean[i];
          let matchIndex = clean.indexOf(charToMatch);

          if (matchIndex !== -1) {
            let col = startCol + i;
            let startRow = r0 - matchIndex;

            if (startRow >= 0 && startRow + clean.length < boardSize) {
              let canPlace = true;
              for (let r = 0; r < clean.length; r++) {
                if (r === matchIndex) continue;
                if (gridCells[startRow + r][col] !== null) { canPlace = false; break; }
              }

              if (canPlace) {
                for (let r = 0; r < clean.length; r++) {
                  if (r === matchIndex) {
                    if (!gridCells[startRow + r][col].num) gridCells[startRow + r][col].num = clueCounter;
                  } else {
                    gridCells[startRow + r][col] = { char: clean[r], num: r === 0 ? clueCounter : null };
                  }
                }
                placedDown.push({ num: clueCounter, title: clean, game: game, row: startRow, col: col, clue: getCluePair(game) });
                clueCounter++;
                break;
              }
            }
          }
        }
        if (placedDown.length >= 3) break;
      }

      container.innerHTML = `
        <div class="game-board">
          <div class="game-status-bar">
            <span>Collection Crossword</span>
            <button class="game-btn" style="padding: 2px 8px; font-size: 0.75rem;" onclick="returnToArcadeMenu()">Exit</button>
          </div>
          
          <div class="crossword-board" style="grid-template-columns: repeat(${boardSize}, 32px);">
            ${gridCells.map((rowArr, r) => rowArr.map((cell, c) => {
              if (!cell) return `<div class="crossword-cell empty"></div>`;
              return `
                <div style="position: relative;">
                  ${cell.num ? `<span style="position: absolute; top: 1px; left: 2px; font-size: 0.55rem; color: var(--turquoise); pointer-events: none;">${cell.num}</span>` : ''}
                  <input type="text" maxlength="1" class="crossword-cell" data-row="${r}" data-col="${c}" data-target="${cell.char}" oninput="autoAdvanceCrossword(this)">
                </div>
              `;
            }).join('')).join('')}
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; font-size: 0.8rem;">
            <div style="background: var(--panel-bg); padding: 8px; border-radius: 6px; border: 1px solid var(--purple-border);">
              <strong style="color: var(--yellow);">ACROSS:</strong>
              ${placedAcross.map(a => `<div style="margin-top: 4px; color: var(--text-muted);"><strong>${a.num}.</strong> ${a.clue}</div>`).join('')}
            </div>
            <div style="background: var(--panel-bg); padding: 8px; border-radius: 6px; border: 1px solid var(--purple-border);">
              <strong style="color: var(--yellow);">DOWN:</strong>
              ${placedDown.map(d => `<div style="margin-top: 4px; color: var(--text-muted);"><strong>${d.num}.</strong> ${d.clue}</div>`).join('')}
            </div>
          </div>

          <button class="game-btn" style="margin-top: 10px;" onclick="checkCrosswordSolution()">Check Answers</button>
        </div>
      `;

      window.autoAdvanceCrossword(this);
    }

    window.autoAdvanceCrossword = function(inputEl) {
      if (!inputEl || !inputEl.value) return;
      let inputs = Array.from(document.querySelectorAll('.crossword-board input'));
      let idx = inputs.indexOf(inputEl);
      if (idx !== -1 && idx < inputs.length - 1) {
        inputs[idx + 1].focus();
      }
    };

    window.checkCrosswordSolution = function() {
      let inputs = document.querySelectorAll('.crossword-board input');
      let allCorrect = true;
      inputs.forEach(inp => {
        let val = inp.value.toUpperCase();
        let target = inp.getAttribute('data-target');
        if (val === target) {
          inp.style.borderColor = 'var(--turquoise)';
          inp.style.color = 'var(--turquoise)';
        } else {
          inp.style.borderColor = 'var(--magenta)';
          inp.style.color = 'var(--magenta)';
          allCorrect = false;
        }
      });

      if (allCorrect) alert("🎉 Congratulations! You solved the crossword perfectly!");
      else alert("Some letters are incorrect. Correct letters are highlighted in green!");
    };
  </script>
</body>
</html>

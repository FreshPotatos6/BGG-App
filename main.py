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
            <p>A 3x3 grid with one game that fits all 4 intersection criteria.</p>
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

    if (globalSearch && globalSearchMobile) {
      globalSearch.addEventListener('input', (e) => { globalSearchMobile.value = e.target.value; handleSearch(); });
      globalSearchMobile.addEventListener('input', (e) => { globalSearch.value = e.target.value; handleSearch(); });
    }

    if (sortSelect && sortSelectMobile) {
      sortSelect.addEventListener('change', () => { sortSelectMobile.value = sortSelect.value; applyFilters(); });
      sortSelectMobile.addEventListener('change', () => { sortSelect.value = sortSelectMobile.value; applyFilters(); });
    }

    if (sortDirBtn && sortDirBtnMobile) {
      sortDirBtn.addEventListener('click', () => {
        isAscending = !isAscending;
        sortDirBtn.innerText = isAscending ? "▲" : "▼";
        sortDirBtnMobile.innerText = isAscending ? "▲" : "▼";
        sortGames();
        renderGames();
      });
      sortDirBtnMobile.addEventListener('click', () => {
        isAscending = !isAscending;
        sortDirBtn.innerText = isAscending ? "▲" : "▼";
        sortDirBtnMobile.innerText = isAscending ? "▲" : "▼";
        sortGames();
        renderGames();
      });
    }

    function handleSearch() {
      renderGames();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    const pMin = document.getElementById('player-min'), pMax = document.getElementById('player-max'), pVal = document.getElementById('player-val'), pTrack = document.getElementById('player-track');
    const wMin = document.getElementById('weight-min'), wMax = document.getElementById('weight-max'), wVal = document.getElementById('weight-val'), wTrack = document.getElementById('weight-track');
    const tMin = document.getElementById('time-min'), tMax = document.getElementById('time-max'), tVal = document.getElementById('time-val'), tTrack = document.getElementById('time-track');
    const bMin = document.getElementById('bgg-min'), bMax = document.getElementById('bgg-max'), bVal = document.getElementById('bgg-val'), bTrack = document.getElementById('bgg-track');
    const lMin = document.getElementById('luke-min'), lMax = document.getElementById('luke-max'), lVal = document.getElementById('luke-val'), lTrack = document.getElementById('luke-track');
    const yMin = document.getElementById('year-min'), yMax = document.getElementById('year-max'), yVal = document.getElementById('year-val'), yTrack = document.getElementById('year-track');

    function updateTrack(minEl, maxEl, trackEl) {
      const minVal = parseFloat(minEl.min);
      const maxVal = parseFloat(minEl.max);
      const curMin = parseFloat(minEl.value);
      const curMax = parseFloat(maxEl.value);
      const leftPercent = ((curMin - minVal) / (maxVal - minVal)) * 100;
      const rightPercent = ((curMax - minVal) / (maxVal - minVal)) * 100;
      trackEl.style.left = leftPercent + '%';
      trackEl.style.width = (rightPercent - leftPercent) + '%';
    }

    function handleRangeInputs(minEl, maxEl, callback) {
      let v1 = parseFloat(minEl.value);
      let v2 = parseFloat(maxEl.value);
      if (v1 > v2) {
        if (window.event && window.event.target === minEl) minEl.value = v2;
        else maxEl.value = v1;
      }
      callback();
      applyFilters();
    }

    [pMin, pMax].forEach(el => el.addEventListener('input', () => handleRangeInputs(pMin, pMax, updatePlayerDisplay)));
    [wMin, wMax].forEach(el => el.addEventListener('input', () => handleRangeInputs(wMin, wMax, updateWeightDisplay)));
    [tMin, tMax].forEach(el => el.addEventListener('input', () => handleRangeInputs(tMin, tMax, updateTimeDisplay)));
    [bMin, bMax].forEach(el => el.addEventListener('input', () => handleRangeInputs(bMin, bMax, updateBggDisplay)));
    [lMin, lMax].forEach(el => el.addEventListener('input', () => handleRangeInputs(lMin, lMax, updateLukeDisplay)));
    [yMin, yMax].forEach(el => el.addEventListener('input', () => handleRangeInputs(yMin, yMax, updateYearDisplay)));

    function updatePlayerDisplay() {
      const mn = pMin.value, mx = pMax.value;
      pVal.innerText = mn === mx ? mn : `${mn} - ${mx}${mx === '10' ? '+' : ''}`;
      updateTrack(pMin, pMax, pTrack);
    }
    function updateWeightDisplay() {
      wVal.innerText = `${parseFloat(wMin.value).toFixed(1)} - ${parseFloat(wMax.value).toFixed(1)}`;
      updateTrack(wMin, wMax, wTrack);
    }
    function updateTimeDisplay() {
      const mn = tMin.value, mx = tMax.value;
      tVal.innerText = `${mn} - ${mx}${mx === '300' ? '+' : ''} min`;
      updateTrack(tMin, tMax, tTrack);
    }
    function updateBggDisplay() {
      bVal.innerText = `${bMin.value} - ${bMax.value}`;
      updateTrack(bMin, bMax, bTrack);
    }
    function updateLukeDisplay() {
      lVal.innerText = `${lMin.value} - ${lMax.value}`;
      updateTrack(lMin, lMax, lTrack);
    }
    function getYearFromSliderVal(val) {
      val = parseInt(val);
      if (val === 0) return 1990;
      return 1998 + (val - 1) * 1;
    }
    function updateYearDisplay() {
      const rawMin = parseInt(yMin.value);
      const rawMax = parseInt(yMax.value);
      const y1 = rawMin === 0 ? "<1990" : getYearFromSliderVal(rawMin);
      const y2 = rawMax === 28 ? "2026" : getYearFromSliderVal(rawMax);
      yVal.innerText = rawMin === rawMax ? y1 : `${y1} - ${y2}`;
      updateTrack(yMin, yMax, yTrack);
    }

    function toggleSidebar() { toolbar.classList.toggle('collapsed'); }
    toggleBtn.addEventListener('click', toggleSidebar);

    function toggleFilterSection(sectionId) {
      document.getElementById(sectionId).classList.toggle('collapsed');
    }

    function setupDropdown(toggleId, menuId, searchId, listId, selectAllId, clearAllId, setCollection, nameKey) {
      const toggle = document.getElementById(toggleId);
      const menu = document.getElementById(menuId);
      const search = document.getElementById(searchId);
      const list = document.getElementById(listId);
      const selectAllBtn = document.getElementById(selectAllId);
      const clearAllBtn = document.getElementById(clearAllId);

      toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        document.querySelectorAll('.dropdown-menu').forEach(m => { if(m !== menu) m.classList.remove('show'); });
        menu.classList.toggle('show');
      });

      menu.addEventListener('click', (e) => e.stopPropagation());

      search.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        list.querySelectorAll('.checkbox-item').forEach(item => {
          const text = item.innerText.toLowerCase();
          item.style.display = text.includes(query) ? 'flex' : 'none';
        });
      });

      selectAllBtn.addEventListener('click', () => {
        list.querySelectorAll('.checkbox-item input[type="checkbox"]').forEach(cb => {
          cb.checked = true;
          setCollection.add(cb.value);
        });
        updateDropdownToggleLabel(toggle, setCollection, nameKey);
        applyFilters();
      });

      clearAllBtn.addEventListener('click', () => {
        list.querySelectorAll('.checkbox-item input[type="checkbox"]').forEach(cb => {
          cb.checked = false;
          setCollection.delete(cb.value);
        });
        updateDropdownToggleLabel(toggle, setCollection, nameKey);
        applyFilters();
      });
    }

    function populateDropdownList(listId, itemsSet, setCollection, toggleId, nameKey) {
      const list = document.getElementById(listId);
      list.innerHTML = '';
      Array.from(itemsSet).sort().forEach(item => {
        const label = document.createElement('label');
        label.className = 'checkbox-item';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = item;
        cb.checked = setCollection.has(item);
        cb.addEventListener('change', () => {
          if (cb.checked) setCollection.add(item);
          else setCollection.delete(item);
          updateDropdownToggleLabel(document.getElementById(toggleId), setCollection, nameKey);
          applyFilters();
        });
        label.appendChild(cb);
        label.appendChild(document.createTextNode(item));
        list.appendChild(label);
      });
    }

    function updateDropdownToggleLabel(toggleBtn, setCollection, nameKey) {
      if (setCollection.size === 0) {
        toggleBtn.innerHTML = `All ${nameKey} <span>▼</span>`;
      } else {
        toggleBtn.innerHTML = `${setCollection.size} ${nameKey} Selected <span>▼</span>`;
      }
    }

    window.addEventListener('click', () => {
      document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
    });

    fetch('/api/collection')
      .then(res => res.json())
      .then(data => {
        rawCollection = data;
        initApp();
      })
      .catch(err => console.error("Error fetching collection:", err));

    function initApp() {
      games = rawCollection;
      
      const stylesSet = new Set();
      const majorAwardsSet = new Set();
      const minorAwardsSet = new Set();
      const themesSet = new Set();
      const catsSet = new Set();
      const mechsSet = new Set();
      const pubsSet = new Set();
      const desSet = new Set();
      const artsSet = new Set();

      rawCollection.forEach(g => {
        if (g.game_mode) stylesSet.add(g.game_mode);
        if (g.major_awards) g.major_awards.forEach(a => majorAwardsSet.add(a));
        if (g.minor_awards) g.minor_awards.forEach(a => minorAwardsSet.add(a));
        if (g.themes) g.themes.forEach(t => themesSet.add(t));
        if (g.categories) g.categories.forEach(c => catsSet.add(c));
        if (g.mechanics) g.mechanics.forEach(m => mechsSet.add(m));
        if (g.publisher && g.publisher !== "Unknown") pubsSet.add(g.publisher);
        if (g.designer && g.designer !== "Unknown") desSet.add(g.designer);
        if (g.artist && g.artist !== "Unknown") artsSet.add(g.artist);
      });

      const styleListEl = document.getElementById('style-list');
      styleListEl.innerHTML = '';
      Array.from(stylesSet).sort().forEach(style => {
        const lbl = document.createElement('label');
        lbl.className = 'style-item';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = style;
        cb.addEventListener('change', () => {
          if (cb.checked) selectedStyles.add(style);
          else selectedStyles.delete(style);
          applyFilters();
        });
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(style));
        styleListEl.appendChild(lbl);
      });

      populateDropdownList('major-award-list', majorAwardsSet, selectedMajorAwards, 'major-award-toggle', 'Major Awards');
      populateDropdownList('minor-award-list', minorAwardsSet, selectedMinorAwards, 'minor-award-toggle', 'Minor Awards');
      populateDropdownList('theme-list', themesSet, selectedThemes, 'theme-toggle', 'Themes');
      populateDropdownList('cat-list', catsSet, selectedCategories, 'cat-toggle', 'Categories');
      populateDropdownList('mech-list', mechsSet, selectedMechanics, 'mech-toggle', 'Mechanics');
      populateDropdownList('pub-list', pubsSet, selectedPublishers, 'pub-toggle', 'Publishers');
      populateDropdownList('des-list', desSet, selectedDesigners, 'des-toggle', 'Designers');
      populateDropdownList('art-list', artsSet, selectedArtists, 'art-toggle', 'Artists');

      setupDropdown('major-award-toggle', 'major-award-menu', 'major-award-search', 'major-award-list', 'major-award-select-all', 'major-award-clear-all', selectedMajorAwards, 'Major Awards');
      setupDropdown('minor-award-toggle', 'minor-award-menu', 'minor-award-search', 'minor-award-list', 'minor-award-select-all', 'minor-award-clear-all', selectedMinorAwards, 'Minor Awards');
      setupDropdown('theme-toggle', 'theme-menu', 'theme-search', 'theme-list', 'theme-select-all', 'theme-clear-all', selectedThemes, 'Themes');
      setupDropdown('cat-toggle', 'cat-menu', 'cat-search', 'cat-list', 'cat-select-all', 'cat-clear-all', selectedCategories, 'Categories');
      setupDropdown('mech-toggle', 'mech-menu', 'mech-search', 'mech-list', 'mech-select-all', 'mech-clear-all', selectedMechanics, 'Mechanics');
      setupDropdown('pub-toggle', 'pub-menu', 'pub-search', 'pub-list', 'pub-select-all', 'pub-clear-all', selectedPublishers, 'Publishers');
      setupDropdown('des-toggle', 'des-menu', 'des-search', 'des-list', 'des-select-all', 'des-clear-all', selectedDesigners, 'Designers');
      setupDropdown('art-toggle', 'art-menu', 'art-search', 'art-list', 'art-select-all', 'art-clear-all', selectedArtists, 'Artists');

      document.getElementById('filter-played').addEventListener('change', applyFilters);
      document.getElementById('filter-unplayed').addEventListener('change', applyFilters);
      document.getElementById('filter-standalone').addEventListener('change', applyFilters);
      document.getElementById('filter-expansions').addEventListener('change', applyFilters);
      document.getElementById('filter-campaign').addEventListener('change', applyFilters);

      updatePlayerDisplay();
      updateWeightDisplay();
      updateTimeDisplay();
      updateBggDisplay();
      updateLukeDisplay();
      updateYearDisplay();

      [globalSearch, globalSearchMobile].forEach(input => {
        if (input) {
          input.addEventListener('input', () => { applyFilters(); });
        }
      });  
      applyFilters();
    }

    function sortGames() {
      const activeSortKey = (sortSelect && sortSelect.value) || "popularity_owned";
      currentlyFilteredGames.sort((a, b) => {
        let valA = a[activeSortKey];
        let valB = b[activeSortKey];

        if (typeof valA === 'string') valA = valA.toLowerCase();
        if (typeof valB === 'string') valB = valB.toLowerCase();

        if (valA < valB) return isAscending ? -1 : 1;
        if (valA > valB) return isAscending ? 1 : -1;
        return 0;
      });
    }

    function applyFilters() {
      const pMinValue = parseInt(pMin.value);
      const pMaxValue = parseInt(pMax.value);
      const wMinValue = parseFloat(wMin.value);
      const wMaxValue = parseFloat(wMax.value);
      const tMinValue = parseInt(tMin.value);
      const tMaxValue = parseInt(tMax.value);
      const bMinValue = parseFloat(bMin.value);
      const bMaxValue = parseFloat(bMax.value);
      const lMinValue = parseFloat(lMin.value);
      const lMaxValue = parseFloat(lMax.value);
      
      const yMinSlider = parseInt(yMin.value);
      const yMaxSlider = parseInt(yMax.value);
      const targetYearMin = yMinSlider === 0 ? 0 : getYearFromSliderVal(yMinSlider);
      const targetYearMax = yMaxSlider === 28 ? 9999 : getYearFromSliderVal(yMaxSlider);

      const filterPlayed = document.getElementById('filter-played').checked;
      const filterUnplayed = document.getElementById('filter-unplayed').checked;
      
      const filterStandalone = document.getElementById('filter-standalone').checked;
      const filterExpansions = document.getElementById('filter-expansions').checked;
      const filterCampaign = document.getElementById('filter-campaign').checked;

      const searchQuery = ((globalSearch && globalSearch.value) || (globalSearchMobile && globalSearchMobile.value) || "").toLowerCase().trim();

      currentlyFilteredGames = games.filter(g => {
        const isExp = g.is_expansion;
        const isCampaign = g.campaign_structure && g.campaign_structure !== "None";
        const isStandalone = g.is_standalone;

        let matchesType = false;
        if (filterStandalone && isStandalone) matchesType = true;
        if (filterExpansions && isExp) matchesType = true;
        if (filterCampaign && isCampaign) matchesType = true;

        if (!matchesType) return false;

        if (g.max_players < pMinValue || g.min_players > pMaxValue) return false;
        if (g.weight < wMinValue || g.weight > wMaxValue) return false;
        if (tMaxValue < 300 && (g.playing_time < tMinValue || g.playing_time > tMaxValue)) return false;
        if (tMaxValue === 300 && g.playing_time < tMinValue) return false;
        if (g.bgg_rating < bMinValue || g.bgg_rating > bMaxValue) return false;
        
        if (lMinValue > 0 && g.user_rating < lMinValue) return false;
        if (g.user_rating > lMaxValue) return false;

        if (g.year > 0) {
          if (yMinSlider > 0 && g.year < targetYearMin) return false;
          if (yMaxSlider < 28 && g.year > targetYearMax) return false;
        }

        if (selectedStyles.size > 0 && !selectedStyles.has(g.game_mode)) return false;

        if (filterPlayed && g.plays_recorded === 0) return false;
        if (filterUnplayed && g.plays_recorded > 0) return false;

        if (selectedMajorAwards.size > 0 && !g.major_awards.some(a => selectedMajorAwards.has(a))) return false;
        if (selectedMinorAwards.size > 0 && !g.minor_awards.some(a => selectedMinorAwards.has(a))) return false;
        if (selectedThemes.size > 0 && !g.themes.some(t => selectedThemes.has(t))) return false;
        if (selectedCategories.size > 0 && !g.categories.some(c => selectedCategories.has(c))) return false;
        if (selectedMechanics.size > 0 && !g.mechanics.some(m => selectedMechanics.has(m))) return false;
        if (selectedPublishers.size > 0 && !selectedPublishers.has(g.publisher)) return false;
        if (selectedDesigners.size > 0 && !selectedDesigners.has(g.designer)) return false;
        if (selectedArtists.size > 0 && !selectedArtists.has(g.artist)) return false;

        if (searchQuery) {
          const matchTitle = g.title.toLowerCase().includes(searchQuery);
          const matchPublisher = g.publisher.toLowerCase().includes(searchQuery);
          const matchDesigner = g.designer.toLowerCase().includes(searchQuery);
          const matchArtist = g.artist.toLowerCase().includes(searchQuery);
          const matchCat = g.categories.some(c => c.toLowerCase().includes(searchQuery));
          const matchMech = g.mechanics.some(m => m.toLowerCase().includes(searchQuery));
          const matchTheme = g.themes.some(t => t.toLowerCase().includes(searchQuery));
          if (!matchTitle && !matchPublisher && !matchDesigner && !matchArtist && !matchCat && !matchMech && !matchTheme) {
            return false;
          }
        }

        return true;
      });

      sortGames();
      renderGames();
    }
    
    function resetToPageLoad() {
      if (globalSearch) globalSearch.value = "";
      if (globalSearchMobile) globalSearchMobile.value = "";

      pMin.value = 1; pMax.value = 10;
      wMin.value = 1.0; wMax.value = 5.0;
      tMin.value = 0; tMax.value = 300;
      bMin.value = 1; bMax.value = 10;
      lMin.value = 0; lMax.value = 10;
      yMin.value = 0; yMax.value = 28;

      updatePlayerDisplay();
      updateWeightDisplay();
      updateTimeDisplay();
      updateBggDisplay();
      updateLukeDisplay();
      updateYearDisplay();

      document.getElementById('filter-played').checked = false;
      document.getElementById('filter-unplayed').checked = false;
      document.getElementById('filter-standalone').checked = true;
      document.getElementById('filter-expansions').checked = false;
      document.getElementById('filter-campaign').checked = false;

      selectedStyles.clear();
      document.querySelectorAll('#style-list input[type="checkbox"]').forEach(cb => cb.checked = false);

      const dropdowns = [
        { set: selectedMajorAwards, toggleId: 'major-award-toggle', listId: 'major-award-list', name: 'Major Awards' },
        { set: selectedMinorAwards, toggleId: 'minor-award-toggle', listId: 'minor-award-list', name: 'Minor Awards' },
        { set: selectedThemes, toggleId: 'theme-toggle', listId: 'theme-list', name: 'Themes' },
        { set: selectedCategories, toggleId: 'cat-toggle', listId: 'cat-list', name: 'Categories' },
        { set: selectedMechanics, toggleId: 'mech-toggle', listId: 'mech-list', name: 'Mechanics' },
        { set: selectedPublishers, toggleId: 'pub-toggle', listId: 'pub-list', name: 'Publishers' },
        { set: selectedDesigners, toggleId: 'des-toggle', listId: 'des-list', name: 'Designers' },
        { set: selectedArtists, toggleId: 'art-toggle', listId: 'art-list', name: 'Artists' }
      ];

      dropdowns.forEach(d => {
        d.set.clear();
        const list = document.getElementById(d.listId);
        if (list) list.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
        const toggle = document.getElementById(d.toggleId);
        if (toggle) updateDropdownToggleLabel(toggle, d.set, d.name);
      });

      if (sortSelect) sortSelect.value = "popularity_owned";
      if (sortSelectMobile) sortSelectMobile.value = "popularity_owned";
      isAscending = false;
      if (sortDirBtn) sortDirBtn.innerText = "▼";
      if (sortDirBtnMobile) sortDirBtnMobile.innerText = "▼";

      applyFilters();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    resetBtn.addEventListener('click', resetToPageLoad);
    headerClearBtn.addEventListener('click', resetToPageLoad);

    function renderGames() {
      grid.innerHTML = '';
      if (currentlyFilteredGames.length === 0) {
        grid.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted); font-size: 1.1rem; font-weight: bold;">No games found matching current filters!</div>`;
        return;
      }
      const rowDiv = document.createElement('div');
      rowDiv.className = 'game-grid-row';
      currentlyFilteredGames.forEach(game => { rowDiv.appendChild(createGameCard(game)); });
      grid.appendChild(rowDiv);
    }

    function createGameCard(game) {
      const card = document.createElement('div');
      card.className = 'game-card';
      if (game.user_rating >= 8.0 || game.bgg_rating >= 8.0) card.classList.add('top-rated');

      const imgWrapper = document.createElement('div');
      imgWrapper.className = 'card-img-wrapper';

      const badgeTopLeft = document.createElement('div');
      badgeTopLeft.className = 'image-badges-top-left';

      if (game.bgg_rating > 0) {
        const bggBadge = document.createElement('div');
        bggBadge.className = 'score-badge-circle score-badge-bgg';
        bggBadge.innerText = game.bgg_rating.toFixed(1);
        bggBadge.title = "BGG Rating";
        badgeTopLeft.appendChild(bggBadge);
      }

      if (game.user_rating > 0) {
        const lukeBadge = document.createElement('div');
        lukeBadge.className = 'score-badge-circle score-badge-luke';
        lukeBadge.innerText = Math.round(game.user_rating);
        lukeBadge.title = "Luke's Rating";
        badgeTopLeft.appendChild(lukeBadge);
      }
      imgWrapper.appendChild(badgeTopLeft);

      const expansionsForGame = rawCollection.filter(item => {
        if (!item.is_expansion) return false;
        const parentRef = String(item.parent_game_id || '').toLowerCase().trim();
        const gId = String(game.id || '').toLowerCase().trim();
        const gTitle = String(game.title || '').toLowerCase().trim();
        return parentRef !== '' && (parentRef === gId || parentRef === gTitle);
      });

      if (expansionsForGame.length > 0) {
        const expBtn = document.createElement('button');
        expBtn.className = 'expansion-icon-btn';
        expBtn.title = `${expansionsForGame.length} Expansion(s) Available`;
        expBtn.innerHTML = `<svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>`;
        expBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          card.classList.toggle('show-expansions');
        });
        imgWrapper.appendChild(expBtn);
      }

      if (game.major_awards && game.major_awards.length > 0) {
        const medalBadge = document.createElement('div');
        medalBadge.className = 'medal-icon-badge';
        medalBadge.innerHTML = '🥇';
        medalBadge.title = game.major_awards.join(', ');
        imgWrapper.appendChild(medalBadge);
      }

      const img = document.createElement('img');
      img.src = game.thumbnail || game.image || '';
      img.alt = game.title;
      img.loading = 'lazy';
      img.onerror = () => { img.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%237209b7'%3E%3Cpath d='M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z'/%3E%3C/svg%3E"; };
      imgWrapper.appendChild(img);
      card.appendChild(imgWrapper);

      const cardContent = document.createElement('div');
      cardContent.className = 'card-content';

      const titleEl = document.createElement('div');
      titleEl.className = 'game-title';
      titleEl.innerText = game.title;
      cardContent.appendChild(titleEl);

      const statsEl = document.createElement('div');
      statsEl.className = 'game-stats';

      const pCountText = game.min_players === game.max_players ? `${game.min_players}` : `${game.min_players}-${game.max_players}`;
      const timeText = game.playing_time_raw ? game.playing_time_raw.replace(/\s*min\.?/gi, '') : `${game.playing_time}`;

      statsEl.innerHTML = `
        <div class="stat-badge" title="Player Count">👥 ${pCountText}</div>
        <div class="stat-badge" title="Play Time">⏱️ ${timeText} min</div>
        <div class="stat-badge" title="Weight / Complexity">⚖️ ${game.weight > 0 ? game.weight.toFixed(1) : 'N/A'}</div>
        <div class="stat-badge" title="Year Published">📅 ${game.year > 0 ? game.year : 'N/A'}</div>
      `;
      cardContent.appendChild(statsEl);
      card.appendChild(cardContent);

      if (expansionsForGame.length > 0) {
        const expOverlay = document.createElement('div');
        expOverlay.className = 'expansions-overlay';

        const expHeader = document.createElement('div');
        expHeader.className = 'expansions-header';
        expHeader.innerHTML = `<span>📦 Expansions (${expansionsForGame.length})</span>`;

        const closeOverlayBtn = document.createElement('button');
        closeOverlayBtn.className = 'expansion-close-btn';
        closeOverlayBtn.innerText = '✕ Close';
        closeOverlayBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          card.classList.remove('show-expansions');
        });
        expHeader.appendChild(closeOverlayBtn);
        expOverlay.appendChild(expHeader);

        expansionsForGame.forEach(exp => {
          const expItem = document.createElement('div');
          expItem.className = 'expansion-item';
          expItem.innerHTML = `
            <div class="expansion-title">${exp.title}</div>
            <div style="color: var(--text-muted); font-size: 0.7rem;">
              👥 ${exp.min_players}-${exp.max_players} | ⏱️ ${exp.playing_time}m | ⚖️ ${exp.weight > 0 ? exp.weight.toFixed(1) : 'N/A'}
            </div>
          `;
          expOverlay.appendChild(expItem);
        });

        card.appendChild(expOverlay);
      }

      card.addEventListener('click', () => openDetailModal(game));

      return card;
    }

    function openDetailModal(game) {
      currentDetailGame = game;
      const pCountText = game.min_players === game.max_players ? `${game.min_players}` : `${game.min_players}-${game.max_players}`;
      const timeText = game.playing_time_raw ? game.playing_time_raw.replace(/\s*min\.?/gi, '') : `${game.playing_time}`;

      detailModalContent.innerHTML = `
        <div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; margin-bottom: 16px;">
          <img src="${game.image || game.thumbnail || ''}" alt="${game.title}" style="max-width: 180px; max-height: 180px; object-fit: contain; border-radius: 8px; border: 2px solid var(--purple-border);">
          <div style="flex: 1; min-width: 200px;">
            <h2 style="color: var(--yellow); font-size: 1.4rem; font-weight: 900; margin-bottom: 6px;">${game.title}</h2>
            <p style="color: var(--turquoise); font-size: 0.85rem; font-weight: bold; margin-bottom: 4px;">Publisher: ${game.publisher}</p>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 4px;">Designer: ${game.designer}</p>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 8px;">Artist: ${game.artist}</p>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
              <span class="stat-badge">👥 ${pCountText} Players</span>
              <span class="stat-badge">⏱️ ${timeText} mins</span>
              <span class="stat-badge">⚖️ Weight ${game.weight > 0 ? game.weight.toFixed(1) : 'N/A'}</span>
              <span class="stat-badge">📅 Year ${game.year > 0 ? game.year : 'N/A'}</span>
            </div>
          </div>
        </div>
        <div style="background: var(--panel-bg); padding: 12px; border-radius: 8px; border: 1px solid var(--purple-border); margin-bottom: 12px; max-height: 200px; overflow-y: auto; font-size: 0.85rem; line-height: 1.4; color: var(--text);">
          ${game.description}
        </div>
        <div style="display: flex; flex-direction: column; gap: 6px; font-size: 0.8rem; color: var(--text-muted);">
          <div><strong>Categories:</strong> ${game.categories && game.categories.length ? game.categories.join(', ') : 'None'}</div>
          <div><strong>Mechanics:</strong> ${game.mechanics && game.mechanics.length ? game.mechanics.join(', ') : 'None'}</div>
          <div><strong>Themes:</strong> ${game.themes && game.themes.length ? game.themes.join(', ') : 'None'}</div>
        </div>
      `;
      detailModal.classList.add('open');
    }

    function closeDetailModal() { detailModal.classList.remove('open'); }

    luckBtn.addEventListener('click', pickRandomGame);
    modalTryAgainBtn.addEventListener('click', pickRandomGame);
    modalChangeFiltersBtn.addEventListener('click', () => {
      closeLuckModal();
      if (toolbar.classList.contains('collapsed')) toggleSidebar();
    });

    function pickRandomGame() {
      if (currentlyFilteredGames.length === 0) {
        modalContent.innerHTML = `<p style="text-align: center; color: var(--magenta); font-weight: bold;">No games match your active filters!</p>`;
        luckModal.classList.add('open');
        return;
      }
      const randomGame = currentlyFilteredGames[Math.floor(Math.random() * currentlyFilteredGames.length)];
      modalContent.innerHTML = `
        <div style="text-align: center; margin-top: 10px;">
          <img src="${randomGame.image || randomGame.thumbnail || ''}" style="max-height: 180px; object-fit: contain; border-radius: 8px; margin-bottom: 12px;">
          <h3 style="color: var(--turquoise); font-size: 1.3rem; font-weight: 900;">${randomGame.title}</h3>
          <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 4px;">⏱️ ${randomGame.playing_time} min | 👥 ${randomGame.min_players}-${randomGame.max_players} players | ⚖️ ${randomGame.weight.toFixed(1)}</p>
        </div>
      `;
      luckModal.classList.add('open');
    }

    function closeLuckModal() { luckModal.classList.remove('open'); }

    /* ==========================================
       MINI-GAMES LOGIC
       ========================================== */
    let arcadeState = {};

    function launchGame(gameKey) {
      document.getElementById('arcade-view-launcher').style.display = 'none';
      const container = document.getElementById('arcade-game-container');
      container.style.display = 'block';
      container.innerHTML = '';

      if (gameKey === 'blind_ranking') startBlindRanking(container);
      else if (gameKey === 'guess_game') startGuessGame(container);
      else if (gameKey === 'higher_lower') startHigherLower(container);
      else if (gameKey === 'connections') startConnections(container);
      else if (gameKey === 'glipped') startGlipped(container);
      else if (gameKey === 'crossword') startCrossword(container);
    }

    /* 1. BLIND RANKING */
    function startBlindRanking(container) {
      // Available: ALL games in rawCollection regardless of rating
      let pool = rawCollection.filter(g => g.bgg_rating > 0);
      if (pool.length < 10) pool = rawCollection;
      
      let shuffled = [...pool].sort(() => 0.5 - Math.random());
      let drawn = shuffled.slice(0, 10);

      arcadeState = {
        drawnGames: drawn,
        currentIndex: 0,
        slots: Array(10).fill(null)
      };

      renderBlindRanking(container);
    }

    function renderBlindRanking(container) {
      const { drawnGames, currentIndex, slots } = arcadeState;
      const isGameOver = currentIndex >= 10;
      const currentGame = !isGameOver ? drawnGames[currentIndex] : null;

      let slotsCol1HTML = '';
      let slotsCol2HTML = '';

      for (let i = 0; i < 10; i++) {
        const gameInSlot = slots[i];
        let slotHTML = '';
        if (gameInSlot) {
          // Display BGG Geek rating instead of Luke's ranking
          slotHTML = `<div style="background: var(--panel-bg); border: 1px solid var(--turquoise); border-radius: 6px; padding: 6px; font-size: 0.8rem; color: var(--yellow); display: flex; align-items: center; justify-content: space-between;">
            <span style="font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${i + 1}. ${gameInSlot.title}</span>
            <span style="background: var(--magenta); color: #fff; border-radius: 4px; padding: 2px 4px; font-size: 0.7rem; flex-shrink: 0; margin-left: 4px;">★ ${gameInSlot.bgg_rating.toFixed(1)}</span>
          </div>`;
        } else {
          slotHTML = `<button class="game-btn" style="width: 100%; text-align: left; padding: 6px 10px; font-size: 0.8rem;" ${isGameOver ? 'disabled' : ''} onclick="placeBlindRank(${i})">
            Slot #${i + 1}
          </button>`;
        }

        if (i < 5) slotsCol1HTML += `<div style="margin-bottom: 6px;">${slotHTML}</div>`;
        else slotsCol2HTML += `<div style="margin-bottom: 6px;">${slotHTML}</div>`;
      }

      let currentCardHTML = '';
      if (!isGameOver) {
        currentCardHTML = `
          <div style="background: var(--card-bg); border: 2px solid var(--turquoise); border-radius: 10px; padding: 12px; text-align: center; margin-bottom: 12px;">
            <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: bold; text-transform: uppercase;">Game ${currentIndex + 1} of 10</span>
            <h4 style="color: var(--yellow); font-size: 1.1rem; margin: 4px 0 8px 0;">${currentGame.title}</h4>
            <img src="${currentGame.image || currentGame.thumbnail}" style="height: 100px; object-fit: contain;">
          </div>
        `;
      } else {
        // Calculate score based on BGG Geek rating order
        let score = 0;
        let sortedSlots = [...slots].filter(Boolean).sort((a, b) => b.bgg_rating - a.bgg_rating);
        for (let i = 0; i < 10; i++) {
          if (slots[i] && sortedSlots[i] && slots[i].id === sortedSlots[i].id) score += 10;
        }

        currentCardHTML = `
          <div style="background: var(--card-bg); border: 2px solid var(--magenta); border-radius: 10px; padding: 16px; text-align: center; margin-bottom: 12px;">
            <h3 style="color: var(--yellow);">Game Over!</h3>
            <p style="color: var(--turquoise); font-size: 1.1rem; font-weight: bold; margin: 8px 0;">Accuracy Score: ${score}/100</p>
            <button class="game-btn" onclick="launchGame('blind_ranking')">Play Again</button>
          </div>
        `;
      }

      container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h3 style="color: var(--magenta);">🎲 Blind Ranking</h3>
          <button onclick="returnToArcadeMenu()" style="padding: 4px 8px; font-size: 0.75rem;">← Menu</button>
        </div>
        ${currentCardHTML}
        <div class="blind-grid-columns">
          <div>${slotsCol1HTML}</div>
          <div>${slotsCol2HTML}</div>
        </div>
      `;
    }

    window.placeBlindRank = function(index) {
      if (arcadeState.slots[index] !== null) return;
      arcadeState.slots[index] = arcadeState.drawnGames[arcadeState.currentIndex];
      arcadeState.currentIndex++;
      renderBlindRanking(document.getElementById('arcade-game-container'));
    };

    /* 2. GUESS THE GAME */
    function startGuessGame(container) {
      let pool = rawCollection.filter(g => g.image || g.thumbnail);
      let target = pool[Math.floor(Math.random() * pool.length)];

      arcadeState = {
        target: target,
        clueStage: 0,
        mode: 'zoom', // 'zoom' or 'pixel'
        zoomLevel: 12, // Starting at level 12 for heavy zoom
        pixelBlur: 20,
        guessedCorrectly: false,
        giveUp: false
      };

      renderGuessGame(container);
    }

    function renderGuessGame(container) {
      const { target, clueStage, mode, zoomLevel, pixelBlur, guessedCorrectly, giveUp } = arcadeState;
      const isEnded = guessedCorrectly || giveUp;

      // Clues order strictly: Year, player count, publisher, Weight, BGG Rating, designer
      const clues = [
        `📅 Year Published: ${target.year > 0 ? target.year : 'Unknown'}`,
        `👥 Player Count: ${target.min_players === target.max_players ? target.min_players : target.min_players + '-' + target.max_players}`,
        `🏢 Publisher: ${target.publisher}`,
        `⚖️ Weight / Complexity: ${target.weight.toFixed(1)}`,
        `⭐ BGG Rating: ${target.bgg_rating.toFixed(1)}`,
        `✍️ Designer: ${target.designer}`
      ];

      let imgStyle = "max-height: 180px; object-fit: contain; transition: all 0.3s ease;";
      if (!isEnded) {
        if (mode === 'zoom') {
          imgStyle += ` transform: scale(${zoomLevel}); clip-path: inset(35% 35% 35% 35%);`;
        } else {
          imgStyle += ` filter: blur(${pixelBlur}px);`;
        }
      }

      let activeCluesHTML = clues.slice(0, clueStage + 1).map(c => `<div style="background: var(--panel-bg); padding: 6px 10px; border-radius: 6px; font-size: 0.85rem; color: var(--turquoise); border: 1px solid var(--purple-border); text-align: left;">${c}</div>`).join('');

      container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h3 style="color: var(--magenta);">🔎 Guess the Game</h3>
          <button onclick="returnToArcadeMenu()" style="padding: 4px 8px; font-size: 0.75rem;">← Menu</button>
        </div>

        <div style="text-align: center;">
          <div style="display: flex; justify-content: center; gap: 8px; margin-bottom: 10px;">
            <button class="game-btn" style="${mode==='zoom'?'background:var(--turquoise);color:#000;':''}" onclick="setGuessMode('zoom')">Zoom Mode</button>
            <button class="game-btn" style="${mode==='pixel'?'background:var(--turquoise);color:#000;':''}" onclick="setGuessMode('pixel')">Blur Mode</button>
          </div>

          <div style="height: 190px; display: flex; align-items: center; justify-content: center; overflow: hidden; background: #000; border-radius: 8px; border: 2px solid var(--purple-border); margin-bottom: 12px; position: relative;">
            <img src="${target.image || target.thumbnail}" style="${imgStyle}">
          </div>

          ${isEnded ? `<div style="background: var(--card-bg); border: 2px solid var(--yellow); padding: 10px; border-radius: 8px; margin-bottom: 12px; color: var(--yellow); font-weight: bold; font-size: 1.1rem;">
            ${guessedCorrectly ? '🎉 Correct! It is ' : 'Game Over! It was '}${target.title}
          </div>` : ''}

          <div class="autocomplete-wrapper" style="margin-bottom: 10px;">
            <input type="text" id="guess-input" autocomplete="off" class="global-search-input" placeholder="Type game title to guess..." ${isEnded?'disabled':''} oninput="handleGuessTyping(this.value)">
            <div id="guess-auto-list" class="autocomplete-list" style="display:none;"></div>
          </div>

          <div style="display: flex; gap: 8px; margin-bottom: 12px;">
            <button class="game-btn" style="flex: 1;" ${clueStage >= clues.length - 1 || isEnded ? 'disabled' : ''} onclick="revealNextClue()">Next Clue (${clueStage + 1}/${clues.length})</button>
            <button class="game-btn" style="flex: 1; background: var(--purple-border);" ${isEnded ? 'disabled' : ''} onclick="giveUpGuess()">Give Up</button>
            ${isEnded ? `<button class="game-btn" style="flex: 1; background: var(--turquoise); color: #000;" onclick="launchGame('guess_game')">Play Again</button>` : ''}
          </div>

          <div style="display: flex; flex-direction: column; gap: 6px;">
            ${activeCluesHTML}
          </div>
        </div>
      `;
    }

    window.setGuessMode = function(m) {
      arcadeState.mode = m;
      renderGuessGame(document.getElementById('arcade-game-container'));
    };

    window.revealNextClue = function() {
      arcadeState.clueStage++;
      arcadeState.zoomLevel = Math.max(1, arcadeState.zoomLevel - 2);
      arcadeState.pixelBlur = Math.max(0, arcadeState.pixelBlur - 4);
      renderGuessGame(document.getElementById('arcade-game-container'));
    };

    window.giveUpGuess = function() {
      arcadeState.giveUp = true;
      renderGuessGame(document.getElementById('arcade-game-container'));
    };

    window.handleGuessTyping = function(val) {
      const autoList = document.getElementById('guess-auto-list');
      if (!val || val.trim().length < 2) {
        autoList.style.display = 'none';
        return;
      }
      const q = val.toLowerCase();
      const matches = rawCollection.filter(g => g.title.toLowerCase().includes(q)).slice(0, 6);
      if (matches.length === 0) {
        autoList.style.display = 'none';
        return;
      }

      autoList.innerHTML = matches.map(g => `<div class="autocomplete-item" onclick="submitGuess('${g.title.replace(/'/g, "\\'")}')">${g.title}</div>`).join('');
      autoList.style.display = 'block';
    };

    window.submitGuess = function(title) {
      document.getElementById('guess-auto-list').style.display = 'none';
      if (title.toLowerCase() === arcadeState.target.title.toLowerCase()) {
        arcadeState.guessedCorrectly = true;
      } else {
        alert("Incorrect guess! Try revealing another clue.");
        return;
      }
      renderGuessGame(document.getElementById('arcade-game-container'));
    };

    /* 3. HIGHER OR LOWER */
    function startHigherLower(container) {
      let pool = rawCollection.filter(g => g.weight > 0 && g.bgg_rating > 0);
      let shuffled = [...pool].sort(() => 0.5 - Math.random());

      let metric = Math.random() > 0.5 ? 'weight' : 'bgg_rating';

      arcadeState = {
        pool: shuffled,
        gameA: shuffled[0],
        gameB: shuffled[1],
        metric: metric, // 'weight' or 'bgg_rating'
        score: 0,
        answered: false,
        userSelection: null // 'A' or 'B'
      };

      renderHigherLower(container);
    }

    function renderHigherLower(container) {
      const { gameA, gameB, metric, score, answered, userSelection } = arcadeState;

      const metricLabel = metric === 'weight' ? 'Weight / Complexity' : 'BGG Rating';

      let valA = metric === 'weight' ? gameA.weight.toFixed(1) : gameA.bgg_rating.toFixed(1);
      let valB = metric === 'weight' ? gameB.weight.toFixed(1) : gameB.bgg_rating.toFixed(1);

      let numA = parseFloat(valA);
      let numB = parseFloat(valB);

      let winner = numA >= numB ? 'A' : 'B';

      container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h3 style="color: var(--magenta);">📈 Higher or Lower</h3>
          <span style="color: var(--yellow); font-weight: bold;">Score: ${score}</span>
        </div>

        <p style="text-align: center; color: var(--turquoise); font-size: 0.95rem; font-weight: bold; margin-bottom: 10px;">
          Select the game with the higher <span style="color: var(--yellow);">${metricLabel}</span>!
        </p>

        <div class="hl-container">
          <div class="hl-card" style="border-color: ${answered && winner === 'A' ? 'var(--turquoise)' : 'var(--purple-border)'};">
            <img src="${gameA.image || gameA.thumbnail}">
            <h4 style="color: var(--yellow); font-size: 0.9rem; margin-bottom: 6px;">${gameA.title}</h4>
            
            ${answered ? `<div style="background: var(--card-bg); color: var(--turquoise); padding: 4px; border-radius: 4px; font-weight: bold; font-size: 1.1rem; margin-bottom: 8px;">${valA}</div>` : ''}

            <button class="game-btn" style="width: 100%; font-size: 0.8rem;" ${answered ? 'disabled' : ''} onclick="submitHigherLowerChoice('A')">
              Select
            </button>
          </div>

          <div style="font-weight: 900; color: var(--magenta); font-size: 1.2rem;">VS</div>

          <div class="hl-card" style="border-color: ${answered && winner === 'B' ? 'var(--turquoise)' : 'var(--purple-border)'};">
            <img src="${gameB.image || gameB.thumbnail}">
            <h4 style="color: var(--yellow); font-size: 0.9rem; margin-bottom: 6px;">${gameB.title}</h4>

            ${answered ? `<div style="background: var(--card-bg); color: var(--turquoise); padding: 4px; border-radius: 4px; font-weight: bold; font-size: 1.1rem; margin-bottom: 8px;">${valB}</div>` : ''}

            <button class="game-btn" style="width: 100%; font-size: 0.8rem;" ${answered ? 'disabled' : ''} onclick="submitHigherLowerChoice('B')">
              Select
            </button>
          </div>
        </div>

        ${answered ? `
          <div style="text-align: center; margin-top: 10px;">
            <p style="font-size: 1.1rem; font-weight: bold; color: ${userSelection === winner ? 'var(--turquoise)' : 'var(--magenta)'};">
              ${userSelection === winner ? '🎉 Correct!' : '❌ Incorrect!'}
            </p>
            <button class="game-btn" style="margin-top: 8px;" onclick="nextHigherLowerRound(${userSelection === winner})">Next Round →</button>
          </div>
        ` : ''}
      `;
    }

    window.submitHigherLowerChoice = function(choice) {
      arcadeState.answered = true;
      arcadeState.userSelection = choice;
      renderHigherLower(document.getElementById('arcade-game-container'));
    };

    window.nextHigherLowerRound = function(isCorrect) {
      if (isCorrect) {
        arcadeState.score++;
        let nextGame = arcadeState.pool[(arcadeState.score + 1) % arcadeState.pool.length];
        arcadeState.gameA = arcadeState.gameB;
        arcadeState.gameB = nextGame;
        arcadeState.metric = Math.random() > 0.5 ? 'weight' : 'bgg_rating';
        arcadeState.answered = false;
        arcadeState.userSelection = null;
        renderHigherLower(document.getElementById('arcade-game-container'));
      } else {
        startHigherLower(document.getElementById('arcade-game-container'));
      }
    };

    /* 4. CONNECTIONS */
    function startConnections(container) {
      // Find 4 distinct metadata buckets with at least 4 games each
      let buckets = [];

      let catCounts = {};
      rawCollection.forEach(g => {
        g.categories.forEach(c => { catCounts[c] = (catCounts[c] || 0) + 1; });
      });

      let validCats = Object.keys(catCounts).filter(c => catCounts[c] >= 4);
      validCats.sort(() => 0.5 - Math.random());

      let chosenCats = validCats.slice(0, 4);

      let gridCards = [];
      chosenCats.forEach((cat, idx) => {
        let gamesInCat = rawCollection.filter(g => g.categories.includes(cat));
        gamesInCat.sort(() => 0.5 - Math.random());
        let selected = gamesInCat.slice(0, 4);
        selected.forEach(g => {
          gridCards.push({ id: g.id, title: g.title, category: cat, catIndex: idx });
        });
      });

      gridCards.sort(() => 0.5 - Math.random());

      arcadeState = {
        cards: gridCards,
        categories: chosenCats,
        selected: [],
        solvedCategories: [],
        strikes: 5
      };

      renderConnections(container);
    }

    function renderConnections(container) {
      const { cards, categories, selected, solvedCategories, strikes } = arcadeState;

      let solvedHTML = solvedCategories.map(cat => `
        <div style="background: var(--turquoise); color: #000; font-weight: bold; text-align: center; padding: 10px; border-radius: 8px; font-size: 0.85rem; margin-bottom: 6px;">
          Category: ${cat}
        </div>
      `).join('');

      let remainingCards = cards.filter(c => !solvedCategories.includes(c.category));

      let cardsHTML = remainingCards.map(c => {
        const isSelected = selected.includes(c.id);
        return `<div class="conn-card ${isSelected ? 'selected' : ''}" onclick="toggleConnCard('${c.id}')">${c.title}</div>`;
      }).join('');

      container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h3 style="color: var(--magenta);">🧩 Connections</h3>
          <span style="color: var(--yellow); font-weight: bold;">Strikes Remaining: ${'❤️'.repeat(strikes)}</span>
        </div>

        <p style="font-size: 0.8rem; color: var(--text-muted); text-align: center; margin-bottom: 8px;">
          Find groups of 4 games that share a common Category/Theme!
        </p>

        ${solvedHTML}

        <div class="conn-grid">
          ${cardsHTML}
        </div>

        <div style="display: flex; gap: 8px; margin-top: 12px;">
          <button class="game-btn" style="flex: 1;" ${selected.length !== 4 ? 'disabled' : ''} onclick="submitConnGuess()">Submit Guess</button>
          <button class="game-btn" style="flex: 1; background: var(--purple-border);" onclick="deselectAllConn()">Deselect All</button>
          <button onclick="returnToArcadeMenu()" style="padding: 4px 8px; font-size: 0.75rem;">← Menu</button>
        </div>
      `;
    }

    window.toggleConnCard = function(id) {
      let sel = arcadeState.selected;
      if (sel.includes(id)) {
        arcadeState.selected = sel.filter(x => x !== id);
      } else {
        if (sel.length < 4) arcadeState.selected.push(id);
      }
      renderConnections(document.getElementById('arcade-game-container'));
    };

    window.deselectAllConn = function() {
      arcadeState.selected = [];
      renderConnections(document.getElementById('arcade-game-container'));
    };

    window.submitConnGuess = function() {
      const { cards, selected, strikes } = arcadeState;
      let chosenCards = cards.filter(c => selected.includes(c.id));
      let firstCat = chosenCards[0].category;
      let allMatch = chosenCards.every(c => c.category === firstCat);

      if (allMatch) {
        arcadeState.solvedCategories.push(firstCat);
        arcadeState.selected = [];
        if (arcadeState.solvedCategories.length === 4) {
          alert("🎉 Congratulations! You solved all 4 Connection categories!");
        }
      } else {
        arcadeState.strikes--;
        alert(`❌ Incorrect grouping! Strikes remaining: ${arcadeState.strikes}`);
        if (arcadeState.strikes <= 0) {
          alert("Game Over! Out of strikes.");
          startConnections(document.getElementById('arcade-game-container'));
          return;
        }
      }
      renderConnections(document.getElementById('arcade-game-container'));
    };

    /* 5. 3X3 GRID (ONE GAME FITS ALL 4 CATEGORIES) */
    function startGlipped(container) {
      // Find 1 core game that has at least 2 distinct categories and 2 distinct mechanics
      let candidates = rawCollection.filter(g => g.categories.length >= 2 && g.mechanics.length >= 2);
      let coreGame = candidates[Math.floor(Math.random() * candidates.length)];

      let rowCat1 = coreGame.categories[0];
      let rowCat2 = coreGame.categories[1];
      let colMech1 = coreGame.mechanics[0];
      let colMech2 = coreGame.mechanics[1];

      // Build a 3x3 grid where cell (1,1) is the core game fitting all 4 criteria
      arcadeState = {
        coreGame: coreGame,
        headers: { row1: rowCat1, row2: rowCat2, col1: colMech1, col2: colMech2 },
        placed: Array(9).fill(null),
        strikes: 4
      };

      renderGlipped(container);
    }

    function renderGlipped(container) {
      const { headers, placed, strikes } = arcadeState;

      container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h3 style="color: var(--magenta);">🌀 3X3 Grid</h3>
          <span style="color: var(--yellow); font-weight: bold;">Strikes: ${'❤️'.repeat(strikes)}</span>
        </div>

        <p style="font-size: 0.8rem; color: var(--text-muted); text-align: center; margin-bottom: 8px;">
          Find games that match intersecting metadata! The center game fits all 4 categories.
        </p>

        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px; text-align: center; font-size: 0.75rem; font-weight: bold;">
          <div></div>
          <div style="background: var(--purple-border); color: var(--yellow); padding: 4px; border-radius: 4px;">${headers.col1}</div>
          <div style="background: var(--purple-border); color: var(--yellow); padding: 4px; border-radius: 4px;">${headers.col2}</div>
          <div style="background: var(--purple-border); color: var(--turquoise); padding: 4px; border-radius: 4px;">Any</div>

          <div style="background: var(--purple-border); color: var(--yellow); padding: 4px; border-radius: 4px; display: flex; align-items: center; justify-content: center;">${headers.row1}</div>
          ${renderGlippedCell(0)}
          ${renderGlippedCell(1)}
          ${renderGlippedCell(2)}

          <div style="background: var(--purple-border); color: var(--yellow); padding: 4px; border-radius: 4px; display: flex; align-items: center; justify-content: center;">${headers.row2}</div>
          ${renderGlippedCell(3)}
          ${renderGlippedCell(4)}
          ${renderGlippedCell(5)}

          <div style="background: var(--purple-border); color: var(--turquoise); padding: 4px; border-radius: 4px; display: flex; align-items: center; justify-content: center;">Any</div>
          ${renderGlippedCell(6)}
          ${renderGlippedCell(7)}
          ${renderGlippedCell(8)}
        </div>

        <div style="margin-top: 12px; text-align: center;">
          <button onclick="returnToArcadeMenu()" style="padding: 4px 8px; font-size: 0.75rem;">← Menu</button>
        </div>
      `;
    }

    function renderGlippedCell(idx) {
      const p = arcadeState.placed[idx];
      if (p) {
        return `<div style="background: var(--panel-bg); border: 1px solid var(--turquoise); border-radius: 6px; padding: 4px; font-size: 0.7rem; color: var(--yellow);">${p.title}</div>`;
      }
      return `<button class="game-btn" style="padding: 4px; font-size: 0.75rem; min-height: 45px;" onclick="searchAndPlaceGlipped(${idx})">+ Select</button>`;
    }

    window.searchAndPlaceGlipped = function(idx) {
      let query = prompt("Enter game title to place in this cell:");
      if (!query) return;

      let found = rawCollection.find(g => g.title.toLowerCase() === query.toLowerCase().trim());
      if (!found) {
        alert("Game not found in collection!");
        return;
      }

      arcadeState.placed[idx] = found;
      renderGlipped(document.getElementById('arcade-game-container'));
    };

    /* 6. COLLECTION CROSSWORD */
    function startCrossword(container) {
      // Pick 3-4 clean titles without spaces or punctuation
      let pool = rawCollection.filter(g => /^[A-Za-z]{3,10}$/.test(g.title));
      pool.sort(() => 0.5 - Math.random());

      let word1 = pool[0];
      let word2 = pool[1];

      arcadeState = {
        grid: Array(8).fill(null).map(() => Array(8).fill('')),
        solution: Array(8).fill(null).map(() => Array(8).fill('')),
        cellNumbers: Array(8).fill(null).map(() => Array(8).fill(0)),
        clues: []
      };

      // Place Word 1 Across (Row 2, Col 1)
      let title1 = word1.title.toUpperCase();
      let title2 = word2.title.toUpperCase();

      for (let i = 0; i < title1.length && i < 8; i++) {
        arcadeState.solution[2][1 + i] = title1[i];
      }
      arcadeState.cellNumbers[2][1] = 1;

      // Place Word 2 Down (Row 0, Col 3) ensuring horizontal rows never touch illegally
      for (let i = 0; i < title2.length && i < 8; i++) {
        arcadeState.solution[i][3] = title2[i];
      }
      arcadeState.cellNumbers[0][3] = 2;

      // Ensure clues always give exactly two pieces of ID (Year & Publisher, or Designer & Weight, or BGG & Player count)
      arcadeState.clues = [
        { num: 1, dir: 'Across', text: `📅 Year: ${word1.year} | 🏢 Publisher: ${word1.publisher}` },
        { num: 2, dir: 'Down', text: `✍️ Designer: ${word2.designer} | ⚖️ Weight: ${word2.weight.toFixed(1)}` }
      ];

      renderCrossword(container);
    }

    function renderCrossword(container) {
      const { solution, cellNumbers, clues } = arcadeState;

      let gridHTML = '';
      for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
          const isLetter = solution[r][c] !== '';
          const num = cellNumbers[r][c];

          if (isLetter) {
            gridHTML += `
              <div class="crossword-cell-wrapper">
                ${num > 0 ? `<span class="cell-number">${num}</span>` : ''}
                <input type="text" maxlength="1" class="crossword-cell" data-row="${r}" data-col="${c}" onkeyup="handleCrosswordKey(event, ${r}, ${c})">
              </div>
            `;
          } else {
            gridHTML += `<div class="crossword-cell-wrapper"><div class="crossword-cell empty"></div></div>`;
          }
        }
      }

      let cluesHTML = clues.map(c => `
        <div style="font-size: 0.8rem; color: var(--turquoise); margin-bottom: 4px;">
          <strong>${c.num}. ${c.dir}:</strong> ${c.text}
        </div>
      `).join('');

      container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <h3 style="color: var(--magenta);">✏️ Collection Crossword</h3>
          <button onclick="returnToArcadeMenu()" style="padding: 4px 8px; font-size: 0.75rem;">← Menu</button>
        </div>

        <div class="crossword-board" style="grid-template-columns: repeat(8, 32px); margin-bottom: 12px;">
          ${gridHTML}
        </div>

        <div style="background: var(--panel-bg); padding: 10px; border-radius: 8px; border: 1px solid var(--purple-border); margin-bottom: 12px;">
          <h4 style="color: var(--yellow); font-size: 0.85rem; margin-bottom: 6px;">Clues:</h4>
          ${cluesHTML}
        </div>

        <div style="display: flex; gap: 8px;">
          <button class="game-btn" style="flex: 1;" onclick="checkCrossword()">Check Answers</button>
          <button class="game-btn" style="flex: 1; background: var(--turquoise); color: #000;" onclick="launchGame('crossword')">New Puzzle</button>
        </div>
      `;
    }

    window.handleCrosswordKey = function(event, r, c) {
      const input = event.target;
      if (input.value.length === 1 && event.key !== 'Backspace') {
        // Auto-advance keyboard focus to next valid square
        let nextInput = document.querySelector(`input[data-row="${r}"][data-col="${c + 1}"]`);
        if (!nextInput) {
          nextInput = document.querySelector(`input[data-row="${r + 1}"][data-col="${c}"]`);
        }
        if (nextInput) nextInput.focus();
      }
    };

    window.checkCrossword = function() {
      const { solution } = arcadeState;
      let correct = true;

      document.querySelectorAll('.crossword-cell').forEach(input => {
        const r = parseInt(input.getAttribute('data-row'));
        const c = parseInt(input.getAttribute('data-col'));
        if (solution[r][c] !== '') {
          if (input.value.toUpperCase() !== solution[r][c]) {
            correct = false;
            input.style.borderColor = 'var(--magenta)';
          } else {
            input.style.borderColor = 'var(--turquoise)';
          }
        }
      });

      if (correct) {
        alert("🎉 Congratulations! All crossword answers are correct!");
      } else {
        alert("❌ Some answers are incorrect or missing.");
      }
    };
  </script>
</body>
</html>

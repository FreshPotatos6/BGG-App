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
    """Parses player count strings (e.g., '1-4', '2', '3-5 players') into min and max integers."""
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
    """Retrieve Google credentials from Environment Variable or local credentials.json."""
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

            is_standalone_val = str(row.get("Is Standalone", "")).strip().lower()
            is_standalone = is_standalone_val in ["yes", "true", "1"]

            supports_one_off_val = str(row.get("Supports One-Off", "")).strip().lower()
            supports_one_off = supports_one_off_val in ["yes", "true", "1"]

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

            games_list.append({
                "id": str(row.get("Game ID", "")).strip(),
                "title": row.get("Title", "Unknown"),
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
                "major_awards": [a.strip() for a in str(row.get("Major Awards", "")).split(",") if a.strip()],
                "minor_awards": [a.strip() for a in str(row.get("Minor Awards", "")).split(",") if a.strip()],
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
      overflow: hidden;
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
    }

    .header-right-column {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 8px;
      flex: 1;
      max-width: 620px;
    }

    .header-actions-top {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
      width: 100%;
      flex-wrap: wrap;
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
      height: calc(100vh - var(--header-height) - 60px);
      overflow-y: auto;
      scroll-snap-type: y mandatory;
      scroll-padding-top: 10px;
      padding-top: 10px;
      padding-right: 10px;
      overscroll-behavior-y: contain;
      -webkit-overflow-scrolling: touch;
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

    .game-row-section {
      scroll-snap-align: start;
      scroll-snap-stop: normal;
      scroll-margin-top: 10px;
      margin-bottom: 25px;
      display: flex;
      flex-direction: column;
    }

    .game-grid-row {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 20px;
      align-items: stretch;
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

    .expansion-icon-btn {
      position: absolute;
      top: 8px;
      right: 8px;
      background: var(--yellow);
      color: #0d0221;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2px solid var(--bg);
      box-shadow: 0 0 8px rgba(254, 228, 64, 0.8);
      cursor: pointer;
      z-index: 10;
      transition: transform 0.2s ease, background 0.2s ease;
    }
    .expansion-icon-btn svg {
      width: 16px;
      height: 16px;
      stroke: #0d0221;
      stroke-width: 4;
      stroke-linecap: round;
    }
    .expansion-icon-btn:hover {
      transform: scale(1.15);
      background: #fff;
    }
    .expansion-icon-btn:hover svg {
      stroke: var(--magenta);
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
      font-size: 1.1rem;
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

    .ratings-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.8rem;
      color: var(--magenta);
      font-weight: 700;
      min-height: 20px;
      margin-top: auto;
    }

    .expansions-overlay {
      display: none;
      position: absolute;
      inset: 0;
      background: rgba(21, 8, 51, 0.98);
      backdrop-filter: blur(4px);
      z-index: 20;
      padding: 10px;
      flex-direction: column;
      overflow-y: auto;
      overflow-x: hidden;
      border-radius: 12px;
    }
    .game-card.show-expansions .expansions-overlay {
      display: flex;
    }

    .expansions-header {
      font-size: 0.75rem;
      font-weight: 900;
      color: var(--yellow);
      text-transform: uppercase;
      border-bottom: 2px dashed var(--magenta);
      padding-bottom: 4px;
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
      background: rgba(13, 2, 33, 0.85);
      backdrop-filter: blur(6px);
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
      background: rgba(13, 2, 33, 0.85);
      backdrop-filter: blur(6px);
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
      max-width: 550px;
      width: 100%;
      padding: 20px;
      box-shadow: 0 0 30px rgba(254, 228, 64, 0.4);
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
      font-size: 1.3rem;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 12px;
      padding-right: 30px;
    }

    .detail-section {
      margin-bottom: 12px;
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    .detail-section strong {
      color: var(--turquoise);
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .meta-tags-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
      margin-bottom: 12px;
      background: rgba(31, 12, 72, 0.3);
      padding: 10px;
      border-radius: 8px;
      border: 1px solid var(--purple-border);
    }

    .description-text {
      margin-top: 4px;
      line-height: 1.4;
      display: -webkit-box;
      -webkit-line-clamp: 6;
      -webkit-box-orient: vertical;
      overflow: hidden;
      transition: all 0.3s ease;
    }

    .description-text.expanded {
      display: block;
      overflow: visible;
    }

    .read-more-btn {
      background: none;
      border: none;
      color: var(--yellow);
      font-size: 0.8rem;
      font-weight: bold;
      padding: 4px 0 0 0;
      cursor: pointer;
      text-decoration: underline;
      display: inline-block;
    }
    .read-more-btn:hover {
      color: var(--turquoise);
      background: none;
    }

    .clickable-tag {
      display: inline-block;
      background: transparent;
      color: var(--yellow);
      border: 1px solid var(--yellow);
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 800;
      margin: 2px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .clickable-tag:hover {
      background: rgba(254, 228, 64, 0.15);
      transform: translateY(-1px);
    }
    .clickable-tag.active-tag {
      background: var(--turquoise);
      color: #0d0221;
      border-color: var(--turquoise);
      box-shadow: 0 0 8px rgba(0, 245, 212, 0.4);
    }
    .clickable-tag.active-tag:hover {
      background: var(--magenta);
      color: #fff;
      border-color: var(--magenta);
    }

    .bgg-link-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      width: 100%;
      margin-top: 15px;
      padding: 10px;
      background: var(--panel-bg);
      color: var(--turquoise);
      border: 2px solid var(--turquoise);
      border-radius: 8px;
      font-weight: 800;
      text-transform: uppercase;
      text-decoration: none;
      letter-spacing: 1px;
      font-size: 0.85rem;
      transition: all 0.2s ease;
    }
    .bgg-link-btn:hover {
      background: var(--turquoise);
      color: #0d0221;
      box-shadow: 0 0 12px rgba(0, 245, 212, 0.4);
    }

    .modal-close-btn {
      margin-top: 16px;
      width: 100%;
    }

    .btn-text-play-desktop { display: inline; }
    .btn-text-play-mobile { display: none; }
    .btn-text-clear-desktop { display: inline; }
    .btn-text-clear-mobile { display: none; }

    @media (max-width: 600px), (max-height: 500px) and (orientation: landscape) {
      body { padding: 0 6px 6px 6px; }
      header { 
        padding: 6px 10px; 
        gap: 6px; 
        flex-direction: row; 
        flex-wrap: nowrap; 
        align-items: center; 
        justify-content: space-between;
      }
      .header-left { width: auto; justify-content: flex-start; }
      .header-left .meeple-logo { width: 28px; height: 28px; }
      h1 { font-size: 0.95rem; letter-spacing: 0.5px; }
      #toggle-filters-btn .filter-icon { display: none; }
      .header-right-column { max-width: none; gap: 4px; align-items: center; flex: initial; }
      .header-actions-top {
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        gap: 4px;
        align-items: center;
        justify-content: flex-end;
      }
      .header-actions-top button,
      .header-actions-top select {
        width: auto;
        text-align: center;
        padding: 4px 6px;
        font-size: 0.7rem;
      }
      .btn-text-play-desktop { display: none; }
      .btn-text-play-mobile { display: inline; }
      .btn-text-clear-desktop { display: none; }
      .btn-text-clear-mobile { display: inline; }
      .desktop-search-slot { display: none; }
      .mobile-search-slot { display: block; width: 100%; max-width: 150px; }
      .global-search-input { padding: 4px 8px 4px 28px; font-size: 0.8rem; }
      .global-search-icon { font-size: 0.75rem; left: 8px; }
      .btn-clear-filters { display: inline-block; padding: 4px 6px; font-size: 0.7rem; }
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
      .range-slider-container input[type="range"]::-webkit-slider-thumb { width: 26px; height: 26px; }
      .app-layout { margin-top: 6px; }
      .main-content { height: calc(100vh - var(--header-height) - 12px); padding-right: 0; }
      .game-grid-row { gap: 6px; }
      .game-card { border-width: 1px; }
      .card-img-wrapper { height: 120px; padding: 4px; }
      .card-content { padding: 6px; gap: 4px; }
      .game-title { font-size: 0.78rem; }
      .ratings-row { font-size: 0.65rem; min-height: 14px; }
      .game-stats { gap: 2px; padding-top: 3px; font-size: 0.62rem; }
      .stat-badge { padding: 2px; }
      .expansion-icon-btn, .medal-icon-badge { width: 24px; height: 24px; font-size: 0.7rem; top: 4px; right: 4px; }
      .medal-icon-badge { bottom: 4px; right: 4px; top: auto; }
      .expansion-close-btn, .sidebar-close-btn { padding: 4px 6px; font-size: 0.7rem; }
      .meta-tags-grid { grid-template-columns: 1fr 1fr; gap: 8px; padding: 8px; }
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
      <div class="global-search-container mobile-search-slot" style="display: none;">
        <span class="global-search-icon">🔍</span>
        <input type="text" id="global-search-mobile" class="global-search-input" placeholder="Search collection...">
      </div>
    </div>

    <div class="header-right-column">
      <div class="header-actions-top">
        <button id="luck-btn" class="btn-luck" title="Play Game">🎲 <span class="btn-text-play-desktop">Play Game</span><span class="btn-text-play-mobile">Play</span></button>
        <button id="toggle-filters-btn" class="btn-primary" title="Filters"><span class="filter-icon">⚙️ </span>Filters</button>
        <button id="header-clear-btn" class="btn-clear-filters" title="Reset All Filters"><span class="btn-text-clear-desktop">Clear Filters</span><span class="btn-text-clear-mobile">Clear</span></button>
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
              <span id="luke-val" class="value-display">1 - 10</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="luke-track" class="range-slider-highlight"></div>
              <input type="range" id="luke-min" min="1" max="10" step="1" value="1">
              <input type="range" id="luke-max" min="1" max="10" step="1" value="10">
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

          <div class="filter-group">
            <div class="filter-label-header">
              <label>Conflict Level</label>
              <span id="conflict-val" class="value-display">Low - High</span>
            </div>
            <div class="range-slider-container">
              <div class="range-slider-track"></div>
              <div id="conflict-track" class="range-slider-highlight"></div>
              <input type="range" id="conflict-min" min="1" max="3" value="1">
              <input type="range" id="conflict-max" min="1" max="3" value="3">
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

          <label class="style-item" style="padding: 4px 2px;">
            <input type="checkbox" id="filter-campaign">
            Campaign
          </label>

          <label class="style-item" style="padding: 4px 2px;">
            <input type="checkbox" id="filter-solo">
            Solo
          </label>
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

      <button id="reset-filters-btn" style="width: 100%;">Reset All Filters</button>

    </aside>

    <main id="game-grid" class="main-content">
    </main>

  </div>

  <div id="detail-modal" class="grid-overlay-container">
    <div class="modal-card" style="position: relative;">
      <div class="modal-close-x" onclick="closeDetailModal()">✕</div>
      <div id="detail-modal-content"></div>
    </div>
  </div>

  <div id="luck-modal" class="modal-overlay">
    <div class="modal-card" style="position: relative;">
      <div class="modal-close-x" onclick="closeLuckModal()">✕</div>
      <div class="modal-title" style="text-align: center;">✨ Play Game ✨</div>
      <div id="modal-content"></div>
      <div style="display: flex; gap: 8px; margin-top: 16px;">
        <button id="modal-try-again-btn" class="btn-luck" style="flex: 1; padding: 10px;">🎲 Try Again</button>
        <button id="modal-change-filters-btn" class="btn-primary" style="flex: 1; padding: 10px;">Filters</button>
        <button id="modal-close-btn" class="btn-clear-filters" style="display: none;">Awesome!</button>
      </div>
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

    const conflictMap = { 1: "Low", 2: "Medium", 3: "High" };
    const conflictValToNum = { "low": 1, "medium": 2, "med": 2, "high": 3 };

    const toolbar = document.getElementById('side-toolbar');
    const toggleBtn = document.getElementById('toggle-filters-btn');
    const resetBtn = document.getElementById('reset-filters-btn');
    const headerClearBtn = document.getElementById('header-clear-btn');
    const grid = document.getElementById('game-grid');
    const sortSelect = document.getElementById('sort-select');
    const sortDirBtn = document.getElementById('sort-dir-btn');
    const luckBtn = document.getElementById('luck-btn');
    const luckModal = document.getElementById('luck-modal');
    const modalContent = document.getElementById('modal-content');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalTryAgainBtn = document.getElementById('modal-try-again-btn');
    const modalChangeFiltersBtn = document.getElementById('modal-change-filters-btn');
    const detailModal = document.getElementById('detail-modal');
    const detailModalContent = document.getElementById('detail-modal-content');
    const globalSearch = document.getElementById('global-search');
    const globalSearchMobile = document.getElementById('global-search-mobile');

    if (globalSearch && globalSearchMobile) {
      globalSearch.addEventListener('input', (e) => { globalSearchMobile.value = e.target.value; handleSearch(); });
      globalSearchMobile.addEventListener('input', (e) => { globalSearch.value = e.target.value; handleSearch(); });
    }

    function handleSearch() {
      renderGames();
      grid.scrollTo({ top: 0, behavior: 'smooth' });
    }

    const pMin = document.getElementById('player-min'), pMax = document.getElementById('player-max'), pVal = document.getElementById('player-val'), pTrack = document.getElementById('player-track');
    const wMin = document.getElementById('weight-min'), wMax = document.getElementById('weight-max'), wVal = document.getElementById('weight-val'), wTrack = document.getElementById('weight-track');
    const tMin = document.getElementById('time-min'), tMax = document.getElementById('time-max'), tVal = document.getElementById('time-val'), tTrack = document.getElementById('time-track');
    const bMin = document.getElementById('bgg-min'), bMax = document.getElementById('bgg-max'), bVal = document.getElementById('bgg-val'), bTrack = document.getElementById('bgg-track');
    const lMin = document.getElementById('luke-min'), lMax = document.getElementById('luke-max'), lVal = document.getElementById('luke-val'), lTrack = document.getElementById('luke-track');
    const yMin = document.getElementById('year-min'), yMax = document.getElementById('year-max'), yVal = document.getElementById('year-val'), yTrack = document.getElementById('year-track');
    const cMin = document.getElementById('conflict-min'), cMax = document.getElementById('conflict-max'), cVal = document.getElementById('conflict-val'), cTrack = document.getElementById('conflict-track');

    const filterPlayed = document.getElementById('filter-played');
    const filterUnplayed = document.getElementById('filter-unplayed');
    const filterCampaign = document.getElementById('filter-campaign');
    const filterSolo = document.getElementById('filter-solo');

    function updateHeaderHeightVariable() {
      const headerElem = document.getElementById('main-header');
      if (headerElem) {
        const height = headerElem.offsetHeight;
        document.documentElement.style.setProperty('--header-height', `${height}px`);
      }
    }

    window.addEventListener('resize', updateHeaderHeightVariable);

    function toggleSidebar() {
      toolbar.classList.toggle('collapsed');
      setTimeout(renderGames, 300);
    }

    toggleBtn.addEventListener('click', toggleSidebar);

    function toggleFilterSection(sectionId) {
      document.getElementById(sectionId).classList.toggle('collapsed');
    }

    sortDirBtn.addEventListener('click', () => {
      isAscending = !isAscending;
      sortDirBtn.textContent = isAscending ? "▲" : "▼";
      renderGames();
      grid.scrollTo({ top: 0, behavior: 'smooth' });
    });

    sortSelect.addEventListener('change', () => {
      const val = sortSelect.value;
      isAscending = (val === 'title' || val === 'year');
      sortDirBtn.textContent = isAscending ? "▲" : "▼";
      renderGames();
      grid.scrollTo({ top: 0, behavior: 'smooth' });
    });

    luckBtn.addEventListener('click', triggerRandomGamePick);
    if (modalTryAgainBtn) modalTryAgainBtn.addEventListener('click', triggerRandomGamePick);
    
    if (modalChangeFiltersBtn) {
      modalChangeFiltersBtn.addEventListener('click', () => {
        luckModal.classList.remove('open');
        if (toolbar.classList.contains('collapsed')) {
          toggleSidebar();
        }
      });
    }

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', () => luckModal.classList.remove('open'));

    function triggerRandomGamePick() {
      if (!currentlyFilteredGames || currentlyFilteredGames.length === 0) {
        modalContent.innerHTML = `<p style="color: var(--yellow); text-align: center;">No games available with your current filter selection!</p>`;
      } else {
        const randomIndex = Math.floor(Math.random() * currentlyFilteredGames.length);
        const randomGame = currentlyFilteredGames[randomIndex];
        modalContent.innerHTML = createGameCardHTML(randomGame);
      }
      luckModal.classList.add('open');
    }

    modalCloseBtn.addEventListener('click', () => luckModal.classList.remove('open'));
    
    function closeDetailModal() {
      detailModal.classList.remove('open');
      currentDetailGame = null;
    }

    detailModal.addEventListener('click', (e) => {
      if (e.target === detailModal) {
        closeDetailModal();
      }
    });

    window.addEventListener('keydown', (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;

      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const scrollDelta = e.key === 'ArrowDown' ? 120 : -120;
        grid.scrollBy({ top: scrollDelta, behavior: 'smooth' });
      } else if (e.key === 'Escape') {
        closeDetailModal();
        luckModal.classList.remove('open');
      }
    });

    function executeResetFilters() {
      pMin.value = 1; pMax.value = 10;
      wMin.value = 1.0; wMax.value = 5.0;
      tMin.value = 0; tMax.value = 300;
      bMin.value = 1; bMax.value = 10;
      lMin.value = 1; lMax.value = 10;
      yMin.value = 0; yMax.value = 28;
      cMin.value = 1; cMax.value = 3;
      filterPlayed.checked = false;
      filterUnplayed.checked = false;
      filterCampaign.checked = false;
      filterSolo.checked = false;
      if (globalSearch) globalSearch.value = '';
      if (globalSearchMobile) globalSearchMobile.value = '';

      selectedPlayerCounts.clear();
      selectedStyles.clear();
      selectedMajorAwards.clear();
      selectedMinorAwards.clear();
      selectedThemes.clear();
      selectedCategories.clear();
      selectedMechanics.clear();
      selectedPublishers.clear();
      selectedDesigners.clear();
      selectedArtists.clear();
      
      setupMultiSelects();
      
      pMin.dispatchEvent(new Event('input'));
      wMin.dispatchEvent(new Event('input'));
      tMin.dispatchEvent(new Event('input'));
      bMin.dispatchEvent(new Event('input'));
      lMin.dispatchEvent(new Event('input'));
      yMin.dispatchEvent(new Event('input'));
      cMin.dispatchEvent(new Event('input'));
      grid.scrollTo({ top: 0, behavior: 'smooth' });

      if (currentDetailGame) {
        openDetailModal(currentDetailGame);
      }
    }

    resetBtn.addEventListener('click', executeResetFilters);
    headerClearBtn.addEventListener('click', executeResetFilters);

    function parseList(val) {
      if (!val) return [];
      if (Array.isArray(val)) return val.map(x => String(x).trim()).filter(Boolean);
      if (typeof val === 'string') return val.split(',').map(x => x.trim()).filter(Boolean);
      return [];
    }

    function cleanTitle(rawTitle) {
      if (!rawTitle) return "Untitled Game";
      return String(rawTitle).replace(/\s*\(\d{4}\)\s*$/, "").trim();
    }

    function yearFromSliderIndex(idx, isMax = false) {
      idx = parseInt(idx);
      if (idx === 0) return isMax ? 1989 : 0;
      if (idx === 1) return isMax ? 1995 : 1990;
      if (idx === 2) return isMax ? 2000 : 1996;
      return 1998 + idx;
    }

    function sliderIndexFromYear(yr) {
      if (yr <= 0) return 0;
      if (yr < 1990) return 0;
      if (yr <= 1995) return 1;
      if (yr <= 2000) return 2;
      let idx = yr - 1998;
      if (idx > 28) idx = 28;
      if (idx < 0) idx = 0;
      return idx;
    }

    function formatYearLabel(minIdx, maxIdx) {
      const minStr = minIdx === 0 ? "<1990" : yearFromSliderIndex(minIdx, false);
      const maxStr = maxIdx >= 28 ? "2026+" : yearFromSliderIndex(maxIdx, true);
      return `${minStr} - ${maxStr}`;
    }

    function formatPlaytimeLabel(minM, maxM) {
      const maxStr = maxM >= 300 ? "300+ min" : `${maxM} min`;
      return `${minM} - ${maxStr}`;
    }

    function formatConflictLabel(minVal, maxVal) {
      return `${conflictMap[minVal]} - ${conflictMap[maxVal]}`;
    }

    function setupDualSlider(minElem, maxElem, valDisplay, trackElem, formatFn) {
      function update(e) {
        let minV = parseFloat(minElem.value);
        let maxV = parseFloat(maxElem.value);

        if (minV > maxV) {
          if (e && e.target === minElem) {
            minElem.value = maxV;
            minV = maxV;
          } else {
            maxElem.value = minV;
            maxV = minV;
          }
        }

        const totalMin = parseFloat(minElem.min);
        const totalMax = parseFloat(minElem.max);
        const leftPercent = ((minV - totalMin) / (totalMax - totalMin)) * 100;
        const rightPercent = 100 - (((maxV - totalMin) / (totalMax - totalMin)) * 100);

        trackElem.style.left = leftPercent + "%";
        trackElem.style.right = rightPercent + "%";

        valDisplay.textContent = formatFn(minV, maxV);
        renderGames();
        grid.scrollTo({ top: 0, behavior: 'smooth' });
      }

      minElem.addEventListener('input', update);
      maxElem.addEventListener('input', update);
      update();
    }

    async function loadCollection() {
      updateHeaderHeightVariable();
      try {
        const response = await fetch('/api/collection');
        if (!response.ok) throw new Error("JSON endpoint returned " + response.status);
        
        let rawData = await response.json();

        if (!Array.isArray(rawData)) {
          if (rawData.games && Array.isArray(rawData.games)) rawData = rawData.games;
          else if (rawData.collection && Array.isArray(rawData.collection)) rawData = rawData.collection;
          else if (rawData.items && Array.isArray(rawData.items)) rawData = rawData.items;
          else rawData = Object.values(rawData);
        }

        rawCollection = rawData.map(g => {
          const parsedUserRating = parseFloat(g.user_rating);
          const parsedBggRating = parseFloat(g.bgg_rating);
          
          const expCol = String(g.is_expansion ?? "").trim().toLowerCase();
          const isExpansion = expCol === 'yes' || expCol === 'true' || expCol === '1' || g.is_expansion === true;

          const saCol = String(g.is_standalone ?? "").trim().toLowerCase();
          const isStandalone = saCol === 'yes' || saCol === 'true' || saCol === '1' || g.is_standalone === true;
          
          const parentId = String(g.parent_game_id ?? "").trim();

          let minP = g.min_players ? parseInt(g.min_players) : 1;
          let maxP = g.max_players ? parseInt(g.max_players) : 4;

          let cStr = String(g.conflict_level ?? "Medium").trim().toLowerCase();
          let cNum = conflictValToNum[cStr] || 2;

          let cStruct = String(g.campaign_structure ?? "").trim().toLowerCase();
          let isCampaign = cStruct !== "" && cStruct !== "none" && cStruct !== "n/a";

          return {
            ...g,
            id: String(g.id ?? "").trim(),
            is_expansion: isExpansion,
            is_standalone: isStandalone,
            parent_game_id: parentId,
            cleanTitle: cleanTitle(g.title),
            parsedCategories: parseList(g.categories),
            parsedMechanics: parseList(g.mechanics),
            parsedThemes: parseList(g.themes),
            parsedMajorAwards: parseList(g.major_awards),
            parsedMinorAwards: parseList(g.minor_awards),
            parsedDesigners: parseList(g.designer),
            parsedArtists: parseList(g.artist),
            publisher: g.publisher ?? "Unknown",
            designer: g.designer ?? "Unknown",
            artist: g.artist ?? "Unknown",
            description: g.description ?? "No description available.",
            game_mode: g.game_mode ?? "Competitive",
            conflict_level_num: cNum,
            is_campaign: isCampaign,
            supports_one_off: g.supports_one_off === true,
            plays_recorded: parseInt(g.plays_recorded ?? 0),
            popularity_owned: parseInt(g.popularity_owned ?? 0),
            min_players: minP,
            max_players: maxP,
            playing_time_raw: g.playing_time_raw || String(g.playing_time || 0),
            playing_time: parseInt(g.playing_time ?? 0),
            weight: parseFloat(g.weight ?? 0) || 0,
            year: parseInt(g.year ?? 0) || 0,
            user_rating: (!isNaN(parsedUserRating) && parsedUserRating > 0) ? parsedUserRating : null,
            bgg_rating: (!isNaN(parsedBggRating) && parsedBggRating > 0) ? parsedBggRating : null
          };
        });

        const baseGamesMap = {};
        const expansionItems = [];

        rawCollection.forEach(item => {
          if (!item.is_expansion || item.is_standalone) {
            item.parsedExpansions = [];
            baseGamesMap[item.id] = item;
          }
          
          if (item.is_expansion) {
            expansionItems.push(item);
          }
        });

        expansionItems.forEach(item => {
          let parent = baseGamesMap[item.parent_game_id];
          if (!parent && item.parent_game_id) {
            parent = Object.values(baseGamesMap).find(bg => 
              bg.cleanTitle.toLowerCase() === item.parent_game_id.toLowerCase()
            );
          }

          if (parent) {
            parent.parsedExpansions.push({
              title: item.cleanTitle,
              weight: item.weight,
              user_rating: item.user_rating,
              bgg_rating: item.bgg_rating
            });
          }
        });

        games = Object.values(baseGamesMap);

      } catch (err) {
        console.error("Could not fetch /api/collection:", err);
      }

      if (!games || games.length === 0) {
        grid.innerHTML = `<p style="grid-column: 1/-1; color: var(--magenta); text-align: center; font-size: 1.2rem; margin-top: 40px;">⚠️ Could not load games from memory or json.</p>`;
        return;
      }

      setupMultiSelects();
      
      setupDualSlider(pMin, pMax, pVal, pTrack, (min, max) => `${min} - ${max >= 10 ? '10+' : max}`);
      setupDualSlider(wMin, wMax, wVal, wTrack, (min, max) => `${min.toFixed(1)} - ${max.toFixed(1)}`);
      
      tMin.min = 0; tMin.max = 300; tMin.step = 15; tMin.value = 0;
      tMax.min = 0; tMax.max = 300; tMax.step = 15; tMax.value = 300;
      setupDualSlider(tMin, tMax, tVal, tTrack, formatPlaytimeLabel);

      setupDualSlider(bMin, bMax, bVal, bTrack, (min, max) => `${min.toFixed(1)} - ${max.toFixed(1)}`);
      setupDualSlider(lMin, lMax, lVal, lTrack, (min, max) => `${Math.round(min)} - ${Math.round(max)}`);

      yMin.max = 28; yMax.max = 28; yMax.value = 28;
      setupDualSlider(yMin, yMax, yVal, yTrack, formatYearLabel);

      setupDualSlider(cMin, cMax, cVal, cTrack, formatConflictLabel);

      filterPlayed.addEventListener('change', () => { renderGames(); grid.scrollTo({ top: 0, behavior: 'smooth' }); });
      filterUnplayed.addEventListener('change', () => { renderGames(); grid.scrollTo({ top: 0, behavior: 'smooth' }); });
      filterCampaign.addEventListener('change', () => { renderGames(); grid.scrollTo({ top: 0, behavior: 'smooth' }); });
      filterSolo.addEventListener('change', () => { renderGames(); grid.scrollTo({ top: 0, behavior: 'smooth' }); });

      renderGames();
      
      setTimeout(() => {
        grid.scrollTo({ top: 0 });
      }, 50);
    }

    function setupMultiSelects() {
      const styles = new Set();
      const majorAwards = new Set();
      const minorAwards = new Set();
      const themes = new Set();
      const categories = new Set();
      const mechanics = new Set();
      const publishers = new Set();
      const designers = new Set();
      const artists = new Set();

      games.forEach(g => {
        if (g.game_mode) styles.add(g.game_mode);
        g.parsedMajorAwards.forEach(a => majorAwards.add(a));
        g.parsedMinorAwards.forEach(a => minorAwards.add(a));
        g.parsedThemes.forEach(t => themes.add(t));
        g.parsedCategories.forEach(c => categories.add(c));
        g.parsedMechanics.forEach(m => mechanics.add(m));
        if (g.publisher && g.publisher !== "Unknown") publishers.add(g.publisher);
        g.parsedDesigners.forEach(d => { if (d !== "Unknown") designers.add(d); });
        g.parsedArtists.forEach(a => { if (a !== "Unknown") artists.add(a); });
      });

      renderStyleCheckboxes(styles);
      renderCheckboxList('major-award-list', majorAwards, selectedMajorAwards, 'major-award');
      renderCheckboxList('minor-award-list', minorAwards, selectedMinorAwards, 'minor-award');
      renderCheckboxList('theme-list', themes, selectedThemes, 'theme');
      renderCheckboxList('cat-list', categories, selectedCategories, 'cat');
      renderCheckboxList('mech-list', mechanics, selectedMechanics, 'mech');
      renderCheckboxList('pub-list', publishers, selectedPublishers, 'pub');
      renderCheckboxList('des-list', designers, selectedDesigners, 'des');
      renderCheckboxList('art-list', artists, selectedArtists, 'art');

      setupDropdownToggle('major-award-toggle', 'major-award-menu');
      setupDropdownToggle('minor-award-toggle', 'minor-award-menu');
      setupDropdownToggle('theme-toggle', 'theme-menu');
      setupDropdownToggle('cat-toggle', 'cat-menu');
      setupDropdownToggle('mech-toggle', 'mech-menu');
      setupDropdownToggle('pub-toggle', 'pub-menu');
      setupDropdownToggle('des-toggle', 'des-menu');
      setupDropdownToggle('art-toggle', 'art-menu');

      setupDropdownSearch('major-award-search', 'major-award-list');
      setupDropdownSearch('minor-award-search', 'minor-award-list');
      setupDropdownSearch('theme-search', 'theme-list');
      setupDropdownSearch('cat-search', 'cat-list');
      setupDropdownSearch('mech-search', 'mech-list');
      setupDropdownSearch('pub-search', 'pub-list');
      setupDropdownSearch('des-search', 'des-list');
      setupDropdownSearch('art-search', 'art-list');

      document.getElementById('major-award-select-all').onclick = () => { toggleAll('major-award', majorAwards, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('major-award-clear-all').onclick = () => { toggleAll('major-award', majorAwards, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('minor-award-select-all').onclick = () => { toggleAll('minor-award', minorAwards, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('minor-award-clear-all').onclick = () => { toggleAll('minor-award', minorAwards, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('theme-select-all').onclick = () => { toggleAll('theme', themes, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('theme-clear-all').onclick = () => { toggleAll('theme', themes, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('cat-select-all').onclick = () => { toggleAll('cat', categories, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('cat-clear-all').onclick = () => { toggleAll('cat', categories, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('mech-select-all').onclick = () => { toggleAll('mech', mechanics, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('mech-clear-all').onclick = () => { toggleAll('mech', mechanics, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('pub-select-all').onclick = () => { toggleAll('pub', publishers, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('pub-clear-all').onclick = () => { toggleAll('pub', publishers, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('des-select-all').onclick = () => { toggleAll('des', designers, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('des-clear-all').onclick = () => { toggleAll('des', designers, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('art-select-all').onclick = () => { toggleAll('art', artists, true); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
      document.getElementById('art-clear-all').onclick = () => { toggleAll('art', artists, false); grid.scrollTo({ top: 0, behavior: 'smooth' }); };
    }

    function renderStyleCheckboxes(stylesSet) {
      const container = document.getElementById('style-list');
      container.innerHTML = Array.from(stylesSet).sort().map(style => `
        <label class="style-item">
          <input type="checkbox" value="${style}" data-style="${style}" ${selectedStyles.has(style) ? 'checked' : ''}>
          ${style}
        </label>
      `).join('');

      container.querySelectorAll('input').forEach(cb => {
        cb.onchange = (e) => {
          if (e.target.checked) selectedStyles.add(e.target.value);
          else selectedStyles.delete(e.target.value);
          renderGames();
          grid.scrollTo({ top: 0, behavior: 'smooth' });
        };
      });
    }

    function setupDropdownToggle(btnId, menuId) {
      const btn = document.getElementById(btnId);
      const menu = document.getElementById(menuId);
      btn.onclick = (e) => {
        e.stopPropagation();
        menu.classList.toggle('show');
      };
      document.addEventListener('click', (e) => {
        if (!menu.contains(e.target) && e.target !== btn) menu.classList.remove('show');
      });
    }

    function setupDropdownSearch(searchId, listId) {
      const searchInput = document.getElementById(searchId);
      searchInput.addEventListener('click', (e) => e.stopPropagation());
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const listContainer = document.getElementById(listId);
        const labels = listContainer.querySelectorAll('.checkbox-item');
        labels.forEach(label => {
          const text = label.textContent.toLowerCase();
          label.style.display = text.includes(query) ? 'flex' : 'none';
        });
      });
    }

    function renderCheckboxList(containerId, itemsSet, targetSet, prefix) {
      const container = document.getElementById(containerId);
      container.innerHTML = Array.from(itemsSet).sort().map(item => `
        <label class="checkbox-item">
          <input type="checkbox" data-prefix="${prefix}" value="${item}" ${targetSet.has(item) ? 'checked' : ''}>
          ${item}
        </label>
      `).join('');

      container.querySelectorAll('input').forEach(input => {
        input.onchange = (e) => {
          if (e.target.checked) targetSet.add(e.target.value);
          else targetSet.delete(e.target.value);
          renderGames();
          grid.scrollTo({ top: 0, behavior: 'smooth' });
        };
      });
    }

    function toggleAll(prefix, fullSet, check) {
      let targetSet;
      if (prefix === 'major-award') targetSet = selectedMajorAwards;
      else if (prefix === 'minor-award') targetSet = selectedMinorAwards;
      else if (prefix === 'theme') targetSet = selectedThemes;
      else if (prefix === 'cat') targetSet = selectedCategories;
      else if (prefix === 'mech') targetSet = selectedMechanics;
      else if (prefix === 'pub') targetSet = selectedPublishers;
      else if (prefix === 'des') targetSet = selectedDesigners;
      else if (prefix === 'art') targetSet = selectedArtists;

      targetSet.clear();
      if (check) fullSet.forEach(item => targetSet.add(item));

      document.querySelectorAll(`input[data-prefix="${prefix}"]`).forEach(cb => cb.checked = check);
      renderGames();
    }

    function sortGames(gameList) {
      const key = sortSelect.value;
      return gameList.sort((a, b) => {
        let valA = a[key];
        let valB = b[key];

        if (key === 'title') {
          valA = a.cleanTitle;
          valB = b.cleanTitle;
          return isAscending ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }

        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;

        return isAscending ? valA - valB : valB - valA;
      });
    }

    function renderGames() {
      if (!games || games.length === 0) return;

      const minP = parseFloat(pMin.value), maxP = parseFloat(pMax.value);
      const minW = parseFloat(wMin.value), maxW = parseFloat(wMax.value);
      const minMinutes = parseFloat(tMin.value);
      const maxMinutes = parseFloat(tMax.value);
      const minBgg = parseFloat(bMin.value);
      const maxBgg = parseFloat(bMax.value);
      const minLuke = parseFloat(lMin.value);
      const maxLuke = parseFloat(lMax.value);

      const minYear = yearFromSliderIndex(yMin.value, false);
      const maxYear = yearFromSliderIndex(yMax.value, true);

      const minConflict = parseInt(cMin.value);
      const maxConflict = parseInt(cMax.value);

      const reqPlayed = filterPlayed.checked;
      const reqUnplayed = filterUnplayed.checked;
      const reqCampaign = filterCampaign.checked;
      const reqSolo = filterSolo.checked;
      const globalQuery = (globalSearch ? globalSearch.value.trim().toLowerCase() : '');

      currentlyFilteredGames = games.filter(g => {
        if (globalQuery) {
          const matchTitle = g.cleanTitle.toLowerCase().includes(globalQuery);
          const matchPub = g.publisher.toLowerCase().includes(globalQuery);
          const matchDes = g.designer.toLowerCase().includes(globalQuery);
          const matchArt = g.artist.toLowerCase().includes(globalQuery);
          if (!matchTitle && !matchPub && !matchDes && !matchArt) return false;
        }

        if (reqPlayed && g.plays_recorded === 0) return false;
        if (reqUnplayed && g.plays_recorded > 0) return false;

        let matchesPlayers = false;
        if (selectedPlayerCounts.size > 0) {
          matchesPlayers = Array.from(selectedPlayerCounts).some(p => g.min_players <= p && g.max_players >= p);
        } else {
          matchesPlayers = g.min_players <= maxP && g.max_players >= minP;
        }

        const matchesWeight = g.weight === 0 || (g.weight >= minW && g.weight <= maxW);
        const matchesTime = g.playing_time === 0 || (g.playing_time >= minMinutes && g.playing_time <= maxMinutes);
        
        let matchesBgg = true;
        if (g.bgg_rating !== null) {
          matchesBgg = g.bgg_rating >= minBgg && g.bgg_rating <= maxBgg;
        } else {
          matchesBgg = (minBgg <= 1.0);
        }

        let matchesLuke = true;
        if (g.user_rating !== null) {
          matchesLuke = g.user_rating >= minLuke && g.user_rating <= maxLuke;
        } else {
          matchesLuke = (minLuke <= 1.0);
        }
        let matchesYear = true;
        if (g.year > 0) {
          if (yMin.value == '0' && g.year < 1990) matchesYear = true;
          else matchesYear = g.year >= minYear && g.year <= maxYear;
        }

        const matchesConflict = g.conflict_level_num >= minConflict && g.conflict_level_num <= maxConflict;
        
        let matchesCampaign = true;
        if (reqCampaign) {
          matchesCampaign = g.is_campaign;
        } else {
          if (g.is_campaign && !g.supports_one_off) {
            matchesCampaign = false;
          }
        }
        
        let matchesSolo = true;
        if (!reqCampaign && reqSolo) {
          matchesSolo = g.supports_one_off;
        }

        const matchesStyle = selectedStyles.size === 0 || selectedStyles.has(g.game_mode);
        const matchesMajorAward = selectedMajorAwards.size === 0 || Array.from(selectedMajorAwards).every(a => g.parsedMajorAwards.includes(a));
        const matchesMinorAward = selectedMinorAwards.size === 0 || Array.from(selectedMinorAwards).every(a => g.parsedMinorAwards.includes(a));
        const matchesTheme = selectedThemes.size === 0 || Array.from(selectedThemes).every(t => g.parsedThemes.includes(t));
        const matchesPub = selectedPublishers.size === 0 || selectedPublishers.has(g.publisher);
        const matchesDes = selectedDesigners.size === 0 || Array.from(selectedDesigners).every(d => g.parsedDesigners.includes(d));
        const matchesArt = selectedArtists.size === 0 || Array.from(selectedArtists).every(a => g.parsedArtists.includes(a));
        const matchesCat = selectedCategories.size === 0 || Array.from(selectedCategories).every(c => g.parsedCategories.includes(c));
        const matchesMech = selectedMechanics.size === 0 || Array.from(selectedMechanics).every(m => g.parsedMechanics.includes(m));

        return matchesPlayers && matchesWeight && matchesTime && matchesBgg && matchesLuke && matchesYear && matchesConflict && matchesCampaign && matchesSolo && matchesStyle && matchesMajorAward && matchesMinorAward && matchesTheme && matchesPub && matchesDes && matchesArt && matchesCat && matchesMech;
      });

      const sorted = sortGames(currentlyFilteredGames);

      if (sorted.length === 0) {
        grid.innerHTML = `<p style="grid-column: 1/-1; color: var(--yellow); text-align: center; font-size: 1.2rem; margin-top: 40px;">No board games match your current filter selection. Try adjusting the filters!</p>`;
        return;
      }

      const isMobile = window.innerWidth <= 600;
      let itemsPerRow = 2;

      if (!isMobile) {
        const gridWidth = grid.clientWidth || 1000;
        const minCardWidth = 220;
        const gap = 20;
        itemsPerRow = Math.floor((gridWidth + gap) / (minCardWidth + gap));
        if (itemsPerRow < 1) itemsPerRow = 1;
      }

      let rowsHTML = "";
      
      for (let i = 0; i < sorted.length; i += itemsPerRow) {
        const rowGames = sorted.slice(i, i + itemsPerRow);
        
        rowsHTML += `
          <div class="game-row-section">
            <div class="game-grid-row" style="${isMobile ? 'grid-template-columns: repeat(2, 1fr);' : ''}">
              ${rowGames.map(g => createGameCardHTML(g)).join('')}
            </div>
          </div>
        `;
      }

      grid.innerHTML = rowsHTML;
      attachCardEventListeners();
    }

    function attachCardEventListeners() {
      document.querySelectorAll('.expansion-icon-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const card = btn.closest('.game-card');
          card.classList.add('show-expansions');
        });
      });

      document.querySelectorAll('.expansions-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
          if (e.target === overlay) {
            overlay.closest('.game-card').classList.remove('show-expansions');
          }
        });
      });

      document.querySelectorAll('.expansion-close-btn').forEach(closeBtn => {
        closeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          const card = closeBtn.closest('.game-card');
          card.classList.remove('show-expansions');
        });
      });

      document.querySelectorAll('.game-card').forEach(card => {
        card.addEventListener('click', (e) => {
          if (e.target.closest('.expansion-icon-btn') || e.target.closest('.expansions-overlay')) return;
          const gameId = card.getAttribute('data-id');
          const game = games.find(g => g.id === gameId);
          if (game) openDetailModal(game);
        });
      });
    }

    function createGameCardHTML(g) {
      const title = g.cleanTitle;
      const year = g.year > 0 ? g.year : "N/A";

      const userRatingVal = g.user_rating ? Math.round(g.user_rating) : null;
      const userRating = userRatingVal ? `⭐ Luke: ${userRatingVal}` : '';
      const bggRating = g.bgg_rating ? `🌐 BGG: ${g.bgg_rating.toFixed(1)}` : '🌐 BGG: N/A';

      const isTopRated = userRatingVal !== null && [8, 9, 10].includes(userRatingVal);
      const cardClass = isTopRated ? "game-card top-rated" : "game-card";

      const minP = g.min_players;
      const maxP = g.max_players;
      const playerStr = minP === maxP ? `${minP}` : `${minP}-${maxP}`;
      
      const timeStr = g.playing_time_raw ? `${g.playing_time_raw}` : `${g.playing_time}`;
      const timeDisplay = timeStr.toLowerCase().replace(/min/g, '').trim();

      const weight = g.weight > 0 ? g.weight.toFixed(1) : 'N/A';

      const hasExpansions = g.parsedExpansions && g.parsedExpansions.length > 0;
      
      const allAwards = [...g.parsedMajorAwards, ...g.parsedMinorAwards].map(a => a.toLowerCase());
      const hasMedalAward = allAwards.some(a => a.includes("spiel des jahres") || a.includes("kennerspiel des jahres"));

      return `
        <div class="${cardClass}" data-id="${g.id}">
          <div class="card-img-wrapper">
            ${g.image ? `<img src="${g.image}" alt="${title}" loading="lazy">` : `<div style="color:var(--text-muted);font-size:0.8rem;">No Image</div>`}
            
            ${hasExpansions ? `
              <button class="expansion-icon-btn" title="View Expansions">
                <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
              </button>
            ` : ''}

            ${hasMedalAward ? `
              <div class="medal-icon-badge" title="Spiel / Kennerspiel des Jahres Winner">
                🎖️
              </div>
            ` : ''}

            <div class="expansions-overlay">
              <div class="expansions-header">
                <span>Expansions (${g.parsedExpansions.length})</span>
                <button class="expansion-close-btn">✕ Close</button>
              </div>
              ${g.parsedExpansions.map(exp => `
                <div class="expansion-item">
                  <div class="expansion-title">${exp.title}</div>
                  <div style="color: var(--text-muted); font-size: 0.7rem;">
                    ${exp.user_rating ? `⭐ Luke: ${Math.round(exp.user_rating)} | ` : ''}
                    ${exp.bgg_rating ? `🌐 BGG: ${exp.bgg_rating.toFixed(1)} | ` : ''}
                    Weight: ${exp.weight > 0 ? exp.weight.toFixed(1) : 'N/A'}
                  </div>
                </div>
              `).join('')}
            </div>
          </div>

          <div class="card-content">
            <div class="game-title">${title} (${year})</div>
            
            <div class="game-stats">
              <div class="stat-badge">👥 ${playerStr}</div>
              <div class="stat-badge">⏱️ ${timeDisplay}m</div>
              <div class="stat-badge">⚖️ ${weight}</div>
              <div class="stat-badge">⚔️ ${g.conflict_level_num === 1 ? 'Low' : g.conflict_level_num === 3 ? 'High' : 'Med'}</div>
            </div>

            <div class="ratings-row">
              <span>${userRating}</span>
              <span>${bggRating}</span>
            </div>
          </div>
        </div>
      `;
    }

function openDetailModal(g) {
    currentDetailGame = g;
    detailModal.classList.add('open');

    const isPlayed = g.plays_recorded > 0;
    const playStateTag = isPlayed 
      ? `<span class="clickable-tag ${filterPlayed.checked ? 'active-tag' : ''}" onclick="togglePlayStateFilter('played')">Played</span>`
      : `<span class="clickable-tag ${filterUnplayed.checked ? 'active-tag' : ''}" onclick="togglePlayStateFilter('unplayed')">Unplayed</span>`;

    const bggUrl = g.id ? `https://boardgamegeek.com/boardgame/${g.id}` : '#';

    // 1. Play on BGA button HTML
    const bgaHTML = (g.bga && g.bga.trim() !== '')
      ? `<a href="${g.bga}" target="_blank" rel="noopener noreferrer" class="bgg-link-btn" style="background-color: #1b2838; margin-bottom: 12px; display: block; text-align: center;">🎲 Play on BGA</a>`
      : '';

    // 2. Awards tags HTML
    const awardsHTML = (g.parsedAwards && g.parsedAwards.length > 0)
      ? g.parsedAwards.map(award => `<span class="clickable-tag">${award}</span>`).join(' ')
      : '';

    // 3. Player tags with Community Rec Warning Icon (⚠️)
    let playerTagsHTML = '';
    const minP = g.min_players || 1;
    const maxP = g.max_players || minP;

    for (let p = minP; p <= maxP; p++) {
      let label = p >= 10 ? '10+' : String(p);
      const isActive = selectedPlayerCounts.has(p);
      
      let isNotRecommended = false;
      if (g.community_rec_players) {
        isNotRecommended = !String(g.community_rec_players).includes(String(p));
      }
      let warningIcon = isNotRecommended ? ' ⚠️' : '';
      
      playerTagsHTML += `<span class="clickable-tag ${isActive ? 'active-tag' : ''}" onclick="filterByPlayerCount(${p})">${label}${warningIcon}</span>`;
    }
    if (!playerTagsHTML) playerTagsHTML = '<span>N/A</span>';

    // 4. BGG Geek Rating Tag (+/- 1 point filter)
    const geekRating = g.geek_rating || g.bgg_rating || 0;
    const geekRatingTagHTML = geekRating > 0 
      ? `<span class="clickable-tag" onclick="filterByGeekRatingRange(${geekRating})">${Number(geekRating).toFixed(1)}</span>`
      : '<span>N/A</span>';

    let weightTagText = 'Medium';
    if (g.weight > 0) {
      if (g.weight < 2.0) weightTagText = 'Light';
      else if (g.weight < 3.5) weightTagText = 'Medium';
      else weightTagText = 'Heavy';
    }
    const curWMin = parseFloat(wMin.value);
    const curWMax = parseFloat(wMax.value);
    let isWeightActive = false;
    if (weightTagText === 'Light' && curWMin === 1.0 && curWMax === 2.0) isWeightActive = true;
    if (weightTagText === 'Medium' && curWMin === 2.0 && curWMax === 3.5) isWeightActive = true;
    if (weightTagText === 'Heavy' && curWMin === 3.5 && curWMax === 5.0) isWeightActive = true;

    const weightTagHTML = `<span class="clickable-tag ${isWeightActive ? 'active-tag' : ''}" onclick="filterByWeightTier('${weightTagText}')">${weightTagText}</span>`;

    let avgMinutes = g.playing_time;
    if (!avgMinutes && g.playing_time_raw) {
      const numbers = g.playing_time_raw.match(/\d+/g);
      if (numbers && numbers.length > 0) {
        const nums = numbers.map(Number);
        avgMinutes = nums.reduce((a, b) => a + b, 0) / nums.length;
      }
    }

    let playTimeTagText = 'Medium';
    if (avgMinutes > 0) {
      if (avgMinutes <= 30) playTimeTagText = 'Short';
      else if (avgMinutes <= 90) playTimeTagText = 'Medium';
      else playTimeTagText = 'Long';
    }

    const curTMin = parseFloat(tMin.value);
    const curTMax = parseFloat(tMax.value);
    let isPlayTimeActive = false;
    if (playTimeTagText === 'Short' && curTMin === 0 && curTMax === 30) isPlayTimeActive = true;
    if (playTimeTagText === 'Medium' && curTMin === 30 && curTMax === 90) isPlayTimeActive = true;
    if (playTimeTagText === 'Long' && curTMin === 90 && curTMax === 300) isPlayTimeActive = true;

    const playTimeTagHTML = `<span class="clickable-tag ${isPlayTimeActive ? 'active-tag' : ''}" onclick="filterByPlaytimeTier('${playTimeTagText}')">${playTimeTagText}</span>`;

    const curCMin = parseInt(cMin.value);
    const curCMax = parseInt(cMax.value);
    const confNum = g.conflict_level_num || 2;
    const isConflictActive = (curCMin === curCMax && curCMin === confNum);
    const conflictTagHTML = `<span class="clickable-tag ${isConflictActive ? 'active-tag' : ''}" onclick="filterByConflictLevel('${g.conflict_level}')">${g.conflict_level || 'Medium'}</span>`;

    const isModeActive = selectedStyles.has(g.game_mode);
    const gameModeTagHTML = `<span class="clickable-tag ${isModeActive ? 'active-tag' : ''}" onclick="filterByGameMode('${g.game_mode}')">${g.game_mode || 'Competitive'}</span>`;

    const curYMinIdx = parseInt(yMin.value);
    const curYMaxIdx = parseInt(yMax.value);
    const gameYrIdx = sliderIndexFromYear(g.year);
    const isYearActive = (curYMinIdx === curYMaxIdx && curYMinIdx === gameYrIdx);
    const yearTagHTML = g.year > 0 
      ? `<span class="clickable-tag ${isYearActive ? 'active-tag' : ''}" onclick="filterByYear(${g.year})">${g.year}</span>`
      : '<span>Unknown</span>';

    const publisherTagHTML = (g.publisher && g.publisher !== 'Unknown')
      ? `<span class="clickable-tag ${selectedPublishers.has(g.publisher) ? 'active-tag' : ''}" onclick="toggleTagFilter('pub', '${g.publisher.replace(/'/g, "\\'")}')">${g.publisher}</span>`
      : '<span>Unknown</span>';

    const designersHTML = g.parsedDesigners.length > 0
      ? g.parsedDesigners.map(d => `<span class="clickable-tag ${selectedDesigners.has(d) ? 'active-tag' : ''}" onclick="toggleTagFilter('des', '${d.replace(/'/g, "\\'")}')">${d}</span>`).join(' ')
      : '<span>Unknown</span>';

    const artistsHTML = g.parsedArtists.length > 0
      ? g.parsedArtists.map(a => `<span class="clickable-tag ${selectedArtists.has(a) ? 'active-tag' : ''}" onclick="toggleTagFilter('art', '${a.replace(/'/g, "\\'")}')">${a}</span>`).join(' ')
      : '<span>Unknown</span>';

    const themesHTML = g.parsedThemes.length > 0
      ? g.parsedThemes.map(t => `<span class="clickable-tag ${selectedThemes.has(t) ? 'active-tag' : ''}" onclick="toggleTagFilter('theme', '${t.replace(/'/g, "\\'")}')">${t}</span>`).join(' ')
      : '<span>None</span>';

    const categoriesHTML = g.parsedCategories.length > 0
      ? g.parsedCategories.map(c => `<span class="clickable-tag ${selectedCategories.has(c) ? 'active-tag' : ''}" onclick="toggleTagFilter('cat', '${c.replace(/'/g, "\\'")}')">${c}</span>`).join(' ')
      : '<span>None</span>';

    const mechanicsHTML = g.parsedMechanics.length > 0
      ? g.parsedMechanics.map(m => `<span class="clickable-tag ${selectedMechanics.has(m) ? 'active-tag' : ''}" onclick="toggleTagFilter('mech', '${m.replace(/'/g, "\\'")}')">${m}</span>`).join(' ')
      : '<span>None</span>';

    detailModalContent.innerHTML = `
      <div class="modal-title">${g.cleanTitle}</div>
      
      <div class="detail-section" style="margin-bottom: 16px;">
        <div class="description-text">${g.description}</div>
        <button class="read-more-btn" onclick="toggleDescription(this)">Read More</button>
      </div>

      ${bgaHTML}

      <div class="meta-tags-grid">
        <div>
          <strong style="display:block; margin-bottom:4px;">Players:</strong>
          <div>${playerTagsHTML}</div>
        </div>
        <div>
          <strong style="display:block; margin-bottom:4px;">Weight:</strong>
          <div>${weightTagHTML}</div>
        </div>
        <div>
          <strong style="display:block; margin-bottom:4px;">Play Time:</strong>
          <div>${playTimeTagHTML}</div>
        </div>
        <div>
          <strong style="display:block; margin-bottom:4px;">Geek Rating:</strong>
          <div>${geekRatingTagHTML}</div>
        </div>
        <div>
          <strong style="display:block; margin-bottom:4px;">Conflict:</strong>
          <div>${conflictTagHTML}</div>
        </div>
        <div>
          <strong style="display:block; margin-bottom:4px;">Game Mode:</strong>
          <div>${gameModeTagHTML}</div>
        </div>
        <div>
          <strong style="display:block; margin-bottom:4px;">Year:</strong>
          <div>${yearTagHTML}</div>
        </div>
      </div>

      ${awardsHTML ? `
      <div class="detail-section">
        <strong>Awards:</strong> <div>${awardsHTML}</div>
      </div>` : ''}

      <div class="detail-section">
        <strong>Publisher:</strong> <div>${publisherTagHTML}</div>
      </div>

      <div class="detail-section">
        <strong>Designers:</strong> <div>${designersHTML}</div>
      </div>

      <div class="detail-section">
        <strong>Artists:</strong> <div>${artistsHTML}</div>
      </div>

      <div class="detail-section">
        <strong>Themes:</strong> <div>${themesHTML}</div>
      </div>

      <div class="detail-section">
        <strong>Categories:</strong> <div>${categoriesHTML}</div>
      </div>

      <div class="detail-section">
        <strong>Mechanics:</strong> <div>${mechanicsHTML}</div>
      </div>

      <div class="detail-section">
        <strong>Play Status:</strong> <div>${playStateTag}</div>
      </div>

      <a href="${bggUrl}" target="_blank" rel="noopener noreferrer" class="bgg-link-btn">
        🌐 View on BGG
      </a>
      `;

      detailModal.classList.add('open');

      setTimeout(() => {
        const descEl = document.getElementById('modal-desc-text');
        const btnEl = document.getElementById('modal-read-more-btn');
        if (descEl && btnEl) {
          if (descEl.scrollHeight > descEl.clientHeight) {
            btnEl.style.display = 'inline-block';
          }
        }
      }, 50);
    }

    function toggleModalDescription() {
      const descEl = document.getElementById('modal-desc-text');
      const btnEl = document.getElementById('modal-read-more-btn');
      if (descEl.classList.contains('expanded')) {
        descEl.classList.remove('expanded');
        btnEl.textContent = 'Read More';
      } else {
        descEl.classList.add('expanded');
        btnEl.textContent = 'Show Less';
      }
    }

    function filterByTag(type, value) {
      closeDetailModal();
      if (toolbar.classList.contains('collapsed')) {
        toggleSidebar();
      }

      if (type === 'theme') {
        selectedThemes.clear();
        selectedThemes.add(value);
        document.querySelectorAll('input[data-prefix="theme"]').forEach(cb => cb.checked = (cb.value === value));
      } else if (type === 'cat') {
        selectedCategories.clear();
        selectedCategories.add(value);
        document.querySelectorAll('input[data-prefix="cat"]').forEach(cb => cb.checked = (cb.value === value));
      } else if (type === 'mech') {
        selectedMechanics.clear();
        selectedMechanics.add(value);
        document.querySelectorAll('input[data-prefix="mech"]').forEach(cb => cb.checked = (cb.value === value));
      } else if (type === 'major-award') {
        selectedMajorAwards.clear();
        selectedMajorAwards.add(value);
        document.querySelectorAll('input[data-prefix="major-award"]').forEach(cb => cb.checked = (cb.value === value));
      } else if (type === 'minor-award') {
        selectedMinorAwards.clear();
        selectedMinorAwards.add(value);
        document.querySelectorAll('input[data-prefix="minor-award"]').forEach(cb => cb.checked = (cb.value === value));
      }

      renderGames();
      grid.scrollTo({ top: 0, behavior: 'smooth' });
    }

    window.onload = loadCollection;
  </script>
</body>
</html>
"""

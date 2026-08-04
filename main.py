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
        gap: 6px;
        align-items: center;
        width: 100%;
        justify-content: space-between;
      }

      .header-actions-top button {
        flex: 1;
        text-align: center;
        padding: 6px 4px;
        font-size: 0.75rem;
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
      .range-slider-container input[type="range"]::-webkit-slider-thumb { width: 26px; height: 26px; }
      
      .app-layout { margin-top: 10px; }
      .main-content { padding-top: 5px; padding-right: 0; }
      
      .game-grid-row { 
        grid-template-columns: repeat(2, minmax(0, 1fr)); 
        gap: 8px; 
      }
      @media (min-orientation: landscape) {
        .game-grid-row {
          grid-template-columns: repeat(3, minmax(0, 1fr));
        }
      }

      .game-card { border-width: 1px; }
      .card-img-wrapper { height: 120px; padding: 4px; }
      .card-content { padding: 6px; gap: 4px; }
      .game-title { font-size: 0.78rem; }
      .game-stats { gap: 2px; padding-top: 3px; font-size: 0.62rem; }
      .stat-badge { padding: 2px; }
      .score-badge-circle { width: 24px; height: 24px; font-size: 0.6rem; }
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
    </div>

    <div class="header-right-column">
      <div class="header-actions-top">
        <button id="luck-btn" class="btn-luck" title="Pick Game"><span class="btn-icon">🎲 </span><span class="btn-text-play-desktop">Pick Game</span><span class="btn-text-play-mobile">Pick</span></button>
        <button id="toggle-filters-btn" class="btn-primary" title="Filters"><span class="btn-icon">⚙️ </span>Filters</button>
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
      <div class="modal-title" style="text-align: center;">✨ Pick Game ✨</div>
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
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalTryAgainBtn = document.getElementById('modal-try-again-btn');
    const modalChangeFiltersBtn = document.getElementById('modal-change-filters-btn');
    const detailModal = document.getElementById('detail-modal');
    const detailModalContent = document.getElementById('detail-modal-content');
    const globalSearch = document.getElementById('global-search');
    const globalSearchMobile = document.getElementById('global-search-mobile');

    detailModal.addEventListener('click', (e) => {
      if (e.target === detailModal) {
        closeDetailModal();
      }
    });

    luckModal.addEventListener('click', (e) => {
      if (e.target === luckModal) {
        closeLuckModal();
      }
    });

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
    function sliderIndexFromYear(yr) {
      if (!yr || yr < 1990) return 0;
      if (yr > 2026) return 28;
      return Math.min(28, Math.max(0, yr - 1997));
    }
    function updateYearDisplay() {
      const rawMin = parseInt(yMin.value);
      const rawMax = parseInt(yMax.value);
      const y1 = rawMin === 0 ? "<1990" : getYearFromSliderVal(rawMin);
      const y2 = rawMax === 28 ? "2026" : getYearFromSliderVal(rawMax);
      yVal.innerText = rawMin === rawMax ? y1 : `${y1} - ${y2}`;
      updateTrack(yMin, yMax, yTrack);
    }

    function toggleSidebar() {
      toolbar.classList.toggle('collapsed');
    }
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
      games = rawCollection.filter(g => !g.is_expansion);
      
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

      updatePlayerDisplay();
      updateWeightDisplay();
      updateTimeDisplay();
      updateBggDisplay();
      updateLukeDisplay();
      updateYearDisplay();

          // --- AUTO-SEARCH INTEGRATION ---
    [globalSearch, globalSearchMobile].forEach(input => {
      if (input) {
        input.addEventListener('input', () => {
          applyFilters();
        });
      }
    });  
      applyFilters();
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
      const filterCampaign = document.getElementById('filter-campaign').checked;
      const filterSolo = document.getElementById('filter-solo').checked;

      const searchQuery = ((globalSearch && globalSearch.value) || (globalSearchMobile && globalSearchMobile.value) || "").toLowerCase().trim();

      currentlyFilteredGames = games.filter(g => {
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
        if (filterCampaign && (!g.campaign_structure || g.campaign_structure === "None")) return false;
        if (filterSolo && g.min_players > 1) return false;

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

    function sortGames() {
      const sortBy = sortSelect.value;
      currentlyFilteredGames.sort((a, b) => {
        let valA = a[sortBy];
        let valB = b[sortBy];

        if (typeof valA === 'string') {
          valA = valA.toLowerCase();
          valB = valB.toLowerCase();
          if (valA < valB) return isAscending ? -1 : 1;
          if (valA > valB) return isAscending ? 1 : -1;
          return 0;
        } else {
          if (valA < valB) return isAscending ? -1 : 1;
          if (valA > valB) return isAscending ? 1 : -1;
          return 0;
        }
      });
    }

    function resetAllFilters() {
      pMin.value = 1; pMax.value = 10; updatePlayerDisplay();
      wMin.value = 1.0; wMax.value = 5.0; updateWeightDisplay();
      tMin.value = 0; tMax.value = 300; updateTimeDisplay();
      bMin.value = 1; bMax.value = 10; updateBggDisplay();
      lMin.value = 0; lMax.value = 10; updateLukeDisplay();
      yMin.value = 0; yMax.value = 28; updateYearDisplay();

      document.getElementById('filter-played').checked = false;
      document.getElementById('filter-unplayed').checked = false;
      document.getElementById('filter-campaign').checked = false;
      document.getElementById('filter-solo').checked = false;

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

      document.querySelectorAll('.style-item input[type="checkbox"]').forEach(cb => cb.checked = false);
      document.querySelectorAll('.dropdown-menu input[type="checkbox"]').forEach(cb => cb.checked = false);
      document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));

      updateDropdownToggleLabel(document.getElementById('major-award-toggle'), selectedMajorAwards, 'Major Awards');
      updateDropdownToggleLabel(document.getElementById('minor-award-toggle'), selectedMinorAwards, 'Minor Awards');
      updateDropdownToggleLabel(document.getElementById('theme-toggle'), selectedThemes, 'Themes');
      updateDropdownToggleLabel(document.getElementById('cat-toggle'), selectedCategories, 'Categories');
      updateDropdownToggleLabel(document.getElementById('mech-toggle'), selectedMechanics, 'Mechanics');
      updateDropdownToggleLabel(document.getElementById('pub-toggle'), selectedPublishers, 'Publishers');
      updateDropdownToggleLabel(document.getElementById('des-toggle'), selectedDesigners, 'Designers');
      updateDropdownToggleLabel(document.getElementById('art-toggle'), selectedArtists, 'Artists');

      if (globalSearch) globalSearch.value = "";
      if (globalSearchMobile) globalSearchMobile.value = "";

      applyFilters();
    }

    resetBtn.addEventListener('click', resetAllFilters);
    headerClearBtn.addEventListener('click', resetAllFilters);

    function renderGames() {
      grid.innerHTML = '';

      if (currentlyFilteredGames.length === 0) {
        grid.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted); font-size: 1.1rem; font-weight: bold;">No games found matching current filters!</div>`;
        return;
      }

      const rowDiv = document.createElement('div');
      rowDiv.className = 'game-grid-row';

      currentlyFilteredGames.forEach(game => {
        const card = createGameCard(game);
        rowDiv.appendChild(card);
      });

      grid.appendChild(rowDiv);
    }

    function createGameCard(game) {
      const card = document.createElement('div');
      card.className = 'game-card';
      if (game.user_rating >= 8.0 || game.bgg_rating >= 8.0) {
        card.classList.add('top-rated');
      }

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
        <div class="stat-badge" title="Play Time">⏱️ ${timeText}</div>
        <div class="stat-badge" title="Weight / Complexity">⚖️ ${game.weight > 0 ? game.weight.toFixed(1) : 'N/A'}</div>
        <div class="stat-badge" title="Year Published">📅 ${game.year > 0 ? game.year : 'N/A'}</div>
      `;
      cardContent.appendChild(statsEl);
      card.appendChild(cardContent);

      if (expansionsForGame.length > 0) {
        const overlay = document.createElement('div');
        overlay.className = 'expansions-overlay';

        const expHeader = document.createElement('div');
        expHeader.className = 'expansions-header';
        expHeader.innerHTML = `<span>Expansions (${expansionsForGame.length})</span>`;
        
        const closeExpBtn = document.createElement('button');
        closeExpBtn.className = 'expansion-close-btn';
        closeExpBtn.innerText = '✕ Close';
        closeExpBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          card.classList.remove('show-expansions');
        });
        expHeader.appendChild(closeExpBtn);
        overlay.appendChild(expHeader);

        expansionsForGame.forEach(exp => {
          const itemDiv = document.createElement('div');
          itemDiv.className = 'expansion-item';
          itemDiv.innerHTML = `<div class="expansion-title">${exp.title}</div>`;
          overlay.appendChild(itemDiv);
        });

        card.appendChild(overlay);
      }

      card.addEventListener('click', () => {
        openDetailModal(game);
      });

      return card;
    }

    function closeDetailModal() {
      detailModal.classList.remove('open');
      currentDetailGame = null;
    }

    function closeLuckModal() {
      luckModal.classList.remove('open');
    }

    function togglePlayStateFilter(state) {
      const filterPlayed = document.getElementById('filter-played');
      const filterUnplayed = document.getElementById('filter-unplayed');
      if (state === 'played') {
        filterPlayed.checked = !filterPlayed.checked;
        filterUnplayed.checked = false;
      } else {
        filterUnplayed.checked = !filterUnplayed.checked;
        filterPlayed.checked = false;
      }
      applyFilters();
      if (currentDetailGame) openDetailModal(currentDetailGame);
    }

    function filterByPlayerCount(count) {
      if (selectedPlayerCounts.has(count)) {
        selectedPlayerCounts.delete(count);
      } else {
        selectedPlayerCounts.clear();
        selectedPlayerCounts.add(count);
        pMin.value = count;
        pMax.value = count;
        updatePlayerDisplay();
      }
      applyFilters();
      if (currentDetailGame) openDetailModal(currentDetailGame);
    }

    function filterByWeightTier(tier) {
      if (tier === 'Light') { wMin.value = 1.0; wMax.value = 2.0; }
      else if (tier === 'Medium') { wMin.value = 2.0; wMax.value = 3.0; }
      else if (tier === 'Heavy') { wMin.value = 3.0; wMax.value = 5.0; }
      updateWeightDisplay();
      applyFilters();
      if (currentDetailGame) openDetailModal(currentDetailGame);
    }

    function filterByPlaytimeTier(tier) {
      if (tier === 'Short') { tMin.value = 0; tMax.value = 30; }
      else if (tier === 'Medium') { tMin.value = 30; tMax.value = 90; }
      else if (tier === 'Long') { tMin.value = 90; tMax.value = 300; }
      updateTimeDisplay();
      applyFilters();
      if (currentDetailGame) openDetailModal(currentDetailGame);
    }

    function filterByGameMode(mode) {
      if (selectedStyles.has(mode)) selectedStyles.delete(mode);
      else selectedStyles.add(mode);
      applyFilters();
      if (currentDetailGame) openDetailModal(currentDetailGame);
    }

    function filterByYear(yr) {
      const idx = sliderIndexFromYear(yr);
      yMin.value = idx;
      yMax.value = idx;
      updateYearDisplay();
      applyFilters();
      if (currentDetailGame) openDetailModal(currentDetailGame);
    }

    function toggleTagFilter(type, val) {
      let setRef = null;
      let toggleId = '';
      let nameKey = '';

      if (type === 'major_award') { setRef = selectedMajorAwards; toggleId = 'major-award-toggle'; nameKey = 'Major Awards'; }
      else if (type === 'minor_award') { setRef = selectedMinorAwards; toggleId = 'minor-award-toggle'; nameKey = 'Minor Awards'; }
      else if (type === 'theme') { setRef = selectedThemes; toggleId = 'theme-toggle'; nameKey = 'Themes'; }
      else if (type === 'cat') { setRef = selectedCategories; toggleId = 'cat-toggle'; nameKey = 'Categories'; }
      else if (type === 'mech') { setRef = selectedMechanics; toggleId = 'mech-toggle'; nameKey = 'Mechanics'; }
      else if (type === 'pub') { setRef = selectedPublishers; toggleId = 'pub-toggle'; nameKey = 'Publishers'; }
      else if (type === 'des') { setRef = selectedDesigners; toggleId = 'des-toggle'; nameKey = 'Designers'; }
      else if (type === 'art') { setRef = selectedArtists; toggleId = 'art-toggle'; nameKey = 'Artists'; }

      if (setRef) {
        if (setRef.has(val)) setRef.delete(val);
        else setRef.add(val);
        updateDropdownToggleLabel(document.getElementById(toggleId), setRef, nameKey);
        applyFilters();
        if (currentDetailGame) openDetailModal(currentDetailGame);
      }
    }

function openDetailModal(g) {
      currentDetailGame = g;
      detailModal.classList.add('open');

      const filterPlayed = document.getElementById('filter-played');
      const filterUnplayed = document.getElementById('filter-unplayed');

      const isPlayed = g.plays_recorded > 0;
      const playStateTag = isPlayed 
        ? `<span class="clickable-tag ${filterPlayed.checked ? 'active-tag' : ''}" onclick="togglePlayStateFilter('played')">Played</span>`
        : `<span class="clickable-tag ${filterUnplayed.checked ? 'active-tag' : ''}" onclick="togglePlayStateFilter('unplayed')">Unplayed</span>`;

      const bggUrl = g.id ? `https://boardgamegeek.com/boardgame/${g.id}` : '#';

      let playerTagsHTML = '';
      const minP = g.min_players || 1;
      const maxP = g.max_players || minP;

      for (let p = minP; p <= maxP; p++) {
        let label = p >= 10 ? '10+' : String(p);
        const isActive = selectedPlayerCounts.has(p);
        playerTagsHTML += `<span class="clickable-tag ${isActive ? 'active-tag' : ''}" onclick="filterByPlayerCount(${p})">${label}</span>`;
      }
      if (!playerTagsHTML) playerTagsHTML = '<span>N/A</span>';

      let weightTagText = 'Medium';
      if (g.weight > 0) {
        if (g.weight < 2.0) weightTagText = 'Light';
        else if (g.weight < 3.0001) weightTagText = 'Medium';
        else weightTagText = 'Heavy';
      }
      const curWMin = parseFloat(wMin.value);
      const curWMax = parseFloat(wMax.value);
      let isWeightActive = false;
      if (weightTagText === 'Light' && curWMin === 1.0 && curWMax === 2.0) isWeightActive = true;
      if (weightTagText === 'Medium' && curWMin === 2.0 && curWMax === 3.0) isWeightActive = true;
      if (weightTagText === 'Heavy' && curWMin === 3.0 && curWMax === 5.0) isWeightActive = true;

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

      const isModeActive = selectedStyles.has(g.game_mode);
      const gameModeTagHTML = `<span class="clickable-tag ${isModeActive ? 'active-tag' : ''}" onclick="filterByGameMode('${g.game_mode}')">${g.game_mode || 'Competitive'}</span>`;

      const conflictVal = g.conflict_level || g.conflict || 'Medium';
      const conflictTagHTML = `<span class="clickable-tag">${conflictVal}</span>`;

      const curYMinIdx = parseInt(yMin.value);
      const curYMaxIdx = parseInt(yMax.value);
      const gameYrIdx = sliderIndexFromYear(g.year);
      const isYearActive = (curYMinIdx === curYMaxIdx && curYMinIdx === gameYrIdx);
      const yearTagHTML = g.year > 0 
        ? `<span class="clickable-tag ${isYearActive ? 'active-tag' : ''}" onclick="filterByYear(${g.year})">${g.year}</span>`
        : '<span>Unknown</span>';

      const majorAwardsList = g.major_awards || [];
      const majorAwardsHTML = majorAwardsList.length > 0
          ? majorAwardsList.map(a => `<span class="clickable-tag ${selectedMajorAwards.has(a) ? 'active-tag' : ''}" onclick="toggleTagFilter('major_award', '${a.replace(/'/g, "\\'")}')">🥇 ${a}</span>`).join(' ')
          : '<span>None</span>';
          
      const publisherTagHTML = (g.publisher && g.publisher !== 'Unknown')
        ? `<span class="clickable-tag ${selectedPublishers.has(g.publisher) ? 'active-tag' : ''}" onclick="toggleTagFilter('pub', '${g.publisher.replace(/'/g, "\\'")}')">${g.publisher}</span>`
        : '<span>Unknown</span>';

      const designers = g.designer && g.designer !== "Unknown" ? g.designer.split(',').map(d => d.strip ? d.strip() : d.trim()) : [];
      const designersHTML = designers.length > 0
        ? designers.map(d => `<span class="clickable-tag ${selectedDesigners.has(d) ? 'active-tag' : ''}" onclick="toggleTagFilter('des', '${d.replace(/'/g, "\\'")}')">${d}</span>`).join(' ')
        : '<span>Unknown</span>';

      const artists = g.artist && g.artist !== "Unknown" ? g.artist.split(',').map(a => a.strip ? a.strip() : a.trim()) : [];
      const artistsHTML = artists.length > 0
        ? artists.map(a => `<span class="clickable-tag ${selectedArtists.has(a) ? 'active-tag' : ''}" onclick="toggleTagFilter('art', '${a.replace(/'/g, "\\'")}')">${a}</span>`).join(' ')
        : '<span>Unknown</span>';

      const themesHTML = (g.themes && g.themes.length > 0)
        ? g.themes.map(t => `<span class="clickable-tag ${selectedThemes.has(t) ? 'active-tag' : ''}" onclick="toggleTagFilter('theme', '${t.replace(/'/g, "\\'")}')">${t}</span>`).join(' ')
        : '<span>None</span>';

      const categoriesHTML = (g.categories && g.categories.length > 0)
        ? g.categories.map(c => `<span class="clickable-tag ${selectedCategories.has(c) ? 'active-tag' : ''}" onclick="toggleTagFilter('cat', '${c.replace(/'/g, "\\'")}')">${c}</span>`).join(' ')
        : '<span>None</span>';

      const mechanicsHTML = (g.mechanics && g.mechanics.length > 0)
        ? g.mechanics.map(m => `<span class="clickable-tag ${selectedMechanics.has(m) ? 'active-tag' : ''}" onclick="toggleTagFilter('mech', '${m.replace(/'/g, "\\'")}')">${m}</span>`).join(' ')
        : '<span>None</span>';

detailModalContent.innerHTML = `
        <div class="modal-header" style="position: sticky; top: 0; background: inherit; z-index: 10; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #ddd;">
          <div class="modal-title" style="margin: 0; font-size: 1.25rem;">${g.title}</div>
        </div>

        <div class="modal-scrollable-body" style="overflow-y: auto; max-height: 70vh; padding-top: 10px;">
          <div class="detail-section" style="margin-bottom: 15px;">
            <strong>Description:</strong>
            <div id="modal-desc" class="description-text">${g.description || 'No description available.'}</div>
            <button id="desc-read-more" class="read-more-btn" onclick="toggleDescription()">Read More</button>
          </div>

          <div class="meta-tags-grid">
            <div><strong>Players:</strong> ${playerTagsHTML}</div>
            <div><strong>Length:</strong> ${playTimeTagHTML}</div>
            <div><strong>Weight:</strong> ${weightTagHTML}</div>
            <div><strong>Year:</strong> ${yearTagHTML}</div>
            <div><strong>Mode:</strong> ${gameModeTagHTML}</div>
            <div><strong>Conflict:</strong> ${conflictTagHTML}</div>
          </div>

          <div class="detail-section"><strong>Awards:</strong> ${majorAwardsHTML}</div>          
          <div class="detail-section"><strong>Publisher:</strong> ${publisherTagHTML}</div>
          <div class="detail-section"><strong>Designer:</strong> ${designersHTML}</div>
          <div class="detail-section"><strong>Artist:</strong> ${artistsHTML}</div>
          <div class="detail-section"><strong>Themes:</strong> ${themesHTML}</div>
          <div class="detail-section"><strong>Categories:</strong> ${categoriesHTML}</div>
          <div class="detail-section"><strong>Mechanics:</strong> ${mechanicsHTML}</div>

          <div class="detail-section"><strong>Status:</strong> ${playStateTag}</div>

          <a href="${bggUrl}" target="_blank" class="bgg-link-btn">View on BoardGameGeek ↗</a>
        </div>
      `;
    }

    function toggleDescription() {
      const desc = document.getElementById('modal-desc');
      const btn = document.getElementById('desc-read-more');
      if (desc.classList.contains('expanded')) {
        desc.classList.remove('expanded');
        btn.innerText = 'Read More';
      } else {
        desc.classList.add('expanded');
        btn.innerText = 'Show Less';
      }
    }

    luckBtn.addEventListener('click', () => {
      if (currentlyFilteredGames.length === 0) {
        modalContent.innerHTML = `<div style="text-align: center; padding: 20px;">No games available under current filters!</div>`;
      } else {
        const randomGame = currentlyFilteredGames[Math.floor(Math.random() * currentlyFilteredGames.length)];
        modalContent.innerHTML = `
          <div style="text-align: center;">
            <img src="${randomGame.image || randomGame.thumbnail}" style="max-height: 200px; max-width: 100%; border-radius: 8px; margin-bottom: 12px;">
            <h2 style="color: var(--yellow); margin-bottom: 8px;">${randomGame.title}</h2>
            <p style="color: var(--text-muted); font-size: 0.9rem;">👥 ${randomGame.min_players}-${randomGame.max_players} Players | ⏱️ ${randomGame.playing_time} min | ⚖️ ${randomGame.weight.toFixed(1)}</p>
          </div>
        `;
      }
      luckModal.classList.add('open');
    });

    modalTryAgainBtn.addEventListener('click', () => {
      luckBtn.click();
    });

    modalChangeFiltersBtn.addEventListener('click', () => {
      closeLuckModal();
      if (toolbar.classList.contains('collapsed')) {
        toggleSidebar();
      }
    });
  </script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

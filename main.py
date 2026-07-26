import json
import os
import re
from flask import Flask, render_template_string, jsonify

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

def get_google_creds():
    """Retrieve Google credentials from Environment Variable or local credentials.json."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file"
    ]
    
    # First check Render Environment Variable
    env_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if env_creds:
        try:
            cred_dict = json.loads(env_creds)
            return Credentials.from_service_account_info(cred_dict, scopes=scope)
        except Exception as e:
            print(f"Error parsing GOOGLE_CREDENTIALS_JSON env var: {e}")

    # Second check local file
    cred_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(cred_path):
        return Credentials.from_service_account_file(cred_path, scopes=scope)

    print("No valid credentials found (checked GOOGLE_CREDENTIALS_JSON env var and credentials.json file).")
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

            games_list.append({
                "id": str(row.get("Game ID", "")).strip(),
                "title": row.get("Title", "Unknown"),
                "year": clean_int(row.get("Year Published"), 0),
                "playing_time_raw": raw_play_time if raw_play_time else "0",
                "playing_time": clean_int(row.get("Play Time"), 0),
                "weight": clean_float(row.get("Weight / Complexity"), 0.0),
                "bgg_rating": clean_float(row.get("BGG Rating"), 0.0),
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
                "min_players": clean_int(row.get("Min Players", 1), 1),
                "max_players": clean_int(row.get("Max Players", 4), 4),
                "image": row.get("Full Image URL", ""),
                "thumbnail": row.get("Thumbnail URL", ""),
                "categories": [c.strip() for c in str(row.get("Categories", "")).split(",") if c.strip()],
                "mechanics": [m.strip() for m in str(row.get("Mechanics", "")).split(",") if m.strip()],
                "themes": [t.strip() for t in str(row.get("Themes", "")).split(",") if t.strip()],
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

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>RENGAW'S MEEPLES // Collection Dash</title>
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
      font-size: 1.8rem;
      filter: drop-shadow(0 0 8px var(--magenta));
    }

    h1 { 
      font-size: 1.6rem; 
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
      color: var(--yellow);
      border: 2px solid var(--yellow);
      text-transform: uppercase;
      letter-spacing: 1px;
      font-size: 0.8rem;
    }
    .btn-clear-filters:hover {
      background: var(--yellow);
      color: var(--bg);
      border-color: var(--yellow);
      box-shadow: 0 0 10px rgba(254, 228, 64, 0.4);
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
      width: 14px;
      height: 14px;
      stroke: #0d0221;
      stroke-width: 3.5;
      stroke-linecap: round;
    }
    .expansion-icon-btn:hover {
      transform: scale(1.15);
      background: #fff;
    }
    .expansion-icon-btn:hover svg {
      stroke: var(--magenta);
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
      background: var(--panel-bg);
      color: var(--turquoise);
      border: 1px solid var(--purple-border);
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 700;
      margin: 2px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .clickable-tag:hover {
      background: var(--magenta);
      color: #fff;
      border-color: var(--turquoise);
    }
    .clickable-tag.active-tag {
      background: var(--yellow);
      color: #0d0221;
      border-color: var(--yellow);
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

    /* MOBILE OPTIMIZATIONS */
    @media (max-width: 600px) {
      body {
        padding: 0 6px 6px 6px;
      }

      header {
        padding: 6px 10px;
        gap: 6px;
      }

      .header-left {
        width: 100%;
        justify-content: space-between;
      }

      .header-left .meeple-logo {
        font-size: 1.2rem;
      }

      h1 {
        font-size: 0.95rem;
        letter-spacing: 0.5px;
      }

      .header-right-column {
        max-width: 100%;
        gap: 4px;
        align-items: stretch;
      }

      .header-actions-top {
        display: grid;
        grid-template-columns: repeat(4, 1fr) auto;
        gap: 4px;
        justify-content: stretch;
      }

      .header-actions-top button,
      .header-actions-top select {
        width: 100%;
        text-align: center;
        padding: 4px 2px;
        font-size: 0.7rem;
      }

      .global-search-container {
        width: 100%;
      }

      .global-search-input {
        padding: 4px 8px 4px 28px;
        font-size: 0.8rem;
      }

      .global-search-icon {
        font-size: 0.75rem;
        left: 8px;
      }

      .btn-clear-filters {
        display: inline-block;
        padding: 4px 6px;
        font-size: 0.7rem;
      }

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

      .sidebar-toggle-tab {
        display: none;
      }

      .range-slider-container input[type="range"]::-webkit-slider-thumb {
        width: 26px;
        height: 26px;
      }

      .app-layout {
        margin-top: 6px;
      }

      .main-content {
        height: calc(100vh - var(--header-height) - 12px);
        padding-right: 0;
      }

      .game-grid-row {
        gap: 6px;
      }

      .game-card {
        border-width: 1px;
      }

      .card-img-wrapper {
        height: 120px;
        padding: 4px;
      }

      .card-content {
        padding: 6px;
        gap: 4px;
      }

      .game-title {
        font-size: 0.78rem;
      }

      .ratings-row {
        font-size: 0.65rem;
        min-height: 14px;
      }

      .game-stats {
        gap: 2px;
        padding-top: 3px;
        font-size: 0.62rem;
      }

      .stat-badge {
        padding: 2px;
      }

      .expansion-icon-btn {
        width: 32px;
        height: 32px;
        top: 4px;
        right: 4px;
      }

      .expansion-close-btn, .sidebar-close-btn {
        padding: 4px 6px;
        font-size: 0.7rem;
      }

      .expansion-close-btn {
        width: 22px;
        height: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.65rem;
        padding: 0;
        border-radius: 50%;
      }
    }
  </style>
</head>
<body>

  <header id="main-header">
    <div class="header-left">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span class="meeple-logo">♟️</span>
        <h1>Rengaw's Meeples</h1>
      </div>
      <div class="global-search-container mobile-search-slot" style="display: none;">
        <span class="global-search-icon">🔍</span>
        <input type="text" id="global-search-mobile" class="global-search-input" placeholder="Search collection...">
      </div>
    </div>

    <div class="header-right-column">
      <div class="header-actions-top">
        <button id="luck-btn" class="btn-luck" title="Pick For Me">🎲 <span class="btn-text-pick">Pick For Me</span><span class="btn-text-pick-short" style="display:none;">Pick</span></button>
        <button id="toggle-filters-btn" class="btn-primary" title="Filters">⚙️ Filters</button>
        <button id="header-clear-btn" class="btn-clear-filters" title="Reset All Filters"><span class="btn-text-clear">Clear Filters</span><span class="btn-text-clear-short" style="display:none;">Clear</span></button>
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
    <div class="modal-card">
      <div class="modal-title" style="text-align: center;">✨ Pick For Me ✨</div>
      <div id="modal-content"></div>
      <button id="modal-close-btn" class="btn-primary modal-close-btn">Awesome!</button>
    </div>
  </div>

  <script>
    let games = [];
    let rawCollection = [];
    let currentlyFilteredGames = [];
    let isAscending = false;

    let selectedStyles = new Set();
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
    const detailModal = document.getElementById('detail-modal');
    const detailModalContent = document.getElementById('detail-modal-content');
    const globalSearch = document.getElementById('global-search');
    const globalSearchMobile = document.getElementById('global-search-mobile');

    // Keep inputs in sync
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

    luckBtn.addEventListener('click', () => {
      if (!currentlyFilteredGames || currentlyFilteredGames.length === 0) {
        modalContent.innerHTML = `<p style="color: var(--yellow); text-align: center;">No games available with your current filter selection!</p>`;
      } else {
        const randomIndex = Math.floor(Math.random() * currentlyFilteredGames.length);
        const randomGame = currentlyFilteredGames[randomIndex];
        modalContent.innerHTML = createGameCardHTML(randomGame);
      }
      luckModal.classList.add('open');
    });

    modalCloseBtn.addEventListener('click', () => luckModal.classList.remove('open'));
    
    function closeDetailModal() {
      detailModal.classList.remove('open');
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
      yMin.value = 0; yMax.value = 28;
      cMin.value = 1; cMax.value = 3;
      filterPlayed.checked = false;
      filterUnplayed.checked = false;
      filterCampaign.checked = false;
      filterSolo.checked = false;
      if (globalSearch) globalSearch.value = '';
      if (globalSearchMobile) globalSearchMobile.value = '';

      selectedStyles.clear();
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
      yMin.dispatchEvent(new Event('input'));
      cMin.dispatchEvent(new Event('input'));
      grid.scrollTo({ top: 0, behavior: 'smooth' });
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

          let minP = 1, maxP = 4;
          if (g.min_players) {
            minP = parseInt(g.min_players);
            maxP = g.max_players ? parseInt(g.max_players) : minP;
          }

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
      const themes = new Set();
      const categories = new Set();
      const mechanics = new Set();
      const publishers = new Set();
      const designers = new Set();
      const artists = new Set();

      games.forEach(g => {
        if (g.game_mode) styles.add(g.game_mode);
        g.parsedThemes.forEach(t => themes.add(t));
        g.parsedCategories.forEach(c => categories.add(c));
        g.parsedMechanics.forEach(m => mechanics.add(m));
        if (g.publisher && g.publisher !== "Unknown") publishers.add(g.publisher);
        g.parsedDesigners.forEach(d => { if (d !== "Unknown") designers.add(d); });
        g.parsedArtists.forEach(a => { if (a !== "Unknown") artists.add(a); });
      });

      renderStyleCheckboxes(styles);
      renderCheckboxList('theme-list', themes, selectedThemes, 'theme');
      renderCheckboxList('cat-list', categories, selectedCategories, 'cat');
      renderCheckboxList('mech-list', mechanics, selectedMechanics, 'mech');
      renderCheckboxList('pub-list', publishers, selectedPublishers, 'pub');
      renderCheckboxList('des-list', designers, selectedDesigners, 'des');
      renderCheckboxList('art-list', artists, selectedArtists, 'art');

      setupDropdownToggle('theme-toggle', 'theme-menu');
      setupDropdownToggle('cat-toggle', 'cat-menu');
      setupDropdownToggle('mech-toggle', 'mech-menu');
      setupDropdownToggle('pub-toggle', 'pub-menu');
      setupDropdownToggle('des-toggle', 'des-menu');
      setupDropdownToggle('art-toggle', 'art-menu');

      setupDropdownSearch('theme-search', 'theme-list');
      setupDropdownSearch('cat-search', 'cat-list');
      setupDropdownSearch('mech-search', 'mech-list');
      setupDropdownSearch('pub-search', 'pub-list');
      setupDropdownSearch('des-search', 'des-list');
      setupDropdownSearch('art-search', 'art-list');

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
      if (prefix === 'theme') targetSet = selectedThemes;
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

        const matchesPlayers = g.min_players <= maxP && g.max_players >= minP;
        const matchesWeight = g.weight === 0 || (g.weight >= minW && g.weight <= maxW);
        const matchesTime = g.playing_time === 0 || (g.playing_time >= minMinutes && g.playing_time <= maxMinutes);
        
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
        const matchesTheme = selectedThemes.size === 0 || g.parsedThemes.some(t => selectedThemes.has(t));
        const matchesPub = selectedPublishers.size === 0 || selectedPublishers.has(g.publisher);
        const matchesDes = selectedDesigners.size === 0 || g.parsedDesigners.some(d => selectedDesigners.has(d));
        const matchesArt = selectedArtists.size === 0 || g.parsedArtists.some(a => selectedArtists.has(a));
        const matchesCat = selectedCategories.size === 0 || g.parsedCategories.some(c => selectedCategories.has(c));
        const matchesMech = selectedMechanics.size === 0 || g.parsedMechanics.some(m => selectedMechanics.has(m));

        return matchesPlayers && matchesWeight && matchesTime && matchesYear && matchesConflict && matchesCampaign && matchesSolo && matchesStyle && matchesTheme && matchesPub && matchesDes && matchesArt && matchesCat && matchesMech;
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
      const img = g.image ?? g.thumbnail ?? 'https://via.placeholder.com/300x200?text=No+Image';

      let expansionIconHTML = '';
      let expansionListHTML = '';

      if (g.parsedExpansions && g.parsedExpansions.length > 0) {
        expansionIconHTML = `
          <div class="expansion-icon-btn" title="View Expansions">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 5v14M5 12h14"/>
            </svg>
          </div>`;
        
        expansionListHTML = `
          <div class="expansions-overlay">
            <div class="expansions-header">
              <span>🧩 Expansions (${g.parsedExpansions.length})</span>
              <button class="expansion-close-btn" title="Close Expansions">✕</button>
            </div>
            ${g.parsedExpansions.map(ex => {
              const exRatingVal = ex.user_rating ? Math.round(ex.user_rating) : null;
              const exRatingStr = exRatingVal ? `⭐ ${exRatingVal}` : (ex.bgg_rating ? `🌐 ${ex.bgg_rating.toFixed(1)}` : '');
              const exWeightStr = ex.weight > 0 ? `⚖️ ${ex.weight.toFixed(1)}` : '';
              return `
                <div class="expansion-item">
                  <div class="expansion-title">${ex.title}</div>
                  <div style="display:flex; justify-content:space-between; color: var(--text-muted); font-size: 0.7rem;">
                    <span>${exWeightStr}</span>
                    <span style="color: var(--magenta); font-weight:700;">${exRatingStr}</span>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        `;
      }

      return `
        <div class="${cardClass}" data-id="${g.id}">
          ${expansionListHTML}
          <div class="card-img-wrapper">
            ${expansionIconHTML}
            <img src="${img}" alt="${title}" onerror="this.src='https://via.placeholder.com/300x200?text=No+Image'">
          </div>
          <div class="card-content">
            <div class="game-title">${title}</div>
            <div class="ratings-row">
              <span>${bggRating}</span>
              <span>${userRating}</span>
            </div>
            <div class="game-stats">
              <div class="stat-badge">👥 ${playerStr}</div>
              <div class="stat-badge">⏱️ ${timeDisplay}</div>
              <div class="stat-badge">⚖️ ${weight}</div>
              <div class="stat-badge">📅 ${year}</div>
            </div>
          </div>
        </div>
      `;
    }

    function toggleDescription(btn) {
      const descElem = btn.previousElementSibling;
      descElem.classList.toggle('expanded');
      if (descElem.classList.contains('expanded')) {
        btn.textContent = 'Show Less';
      } else {
        btn.textContent = 'Read More';
      }
    }

    function openDetailModal(g) {
      const isPlayed = g.plays_recorded > 0;
      const playStateTag = isPlayed 
        ? `<span class="clickable-tag ${filterPlayed.checked ? 'active-tag' : ''}" onclick="togglePlayStateFilter('played')">Played</span>`
        : `<span class="clickable-tag ${filterUnplayed.checked ? 'active-tag' : ''}" onclick="togglePlayStateFilter('unplayed')">Unplayed</span>`;

      const bggUrl = g.id ? `https://boardgamegeek.com/boardgame/${g.id}` : '#';

      detailModalContent.innerHTML = `
        <div class="modal-title">${g.cleanTitle}</div>

        <div class="detail-section">
          <strong>Description:</strong>
          <div id="modal-desc" class="description-text">${g.description}</div>
          <button id="read-more-btn" class="read-more-btn" onclick="toggleDescription(this)" style="display: none;">Read More</button>
        </div>

        <div class="detail-section">
          <strong>Publisher:</strong> 
          <span class="clickable-tag ${selectedPublishers.has(g.publisher) ? 'active-tag' : ''}" onclick="toggleTagFilter('pub', '${g.publisher}')">${g.publisher}</span>
        </div>

        <div class="detail-section">
          <strong>Designers:</strong> 
          ${g.parsedDesigners.length > 0 
            ? g.parsedDesigners.map(d => `<span class="clickable-tag ${selectedDesigners.has(d) ? 'active-tag' : ''}" onclick="toggleTagFilter('des', '${d}')">${d}</span>`).join('') 
            : g.designer}
        </div>

        <div class="detail-section">
          <strong>Artists:</strong> 
          ${g.parsedArtists.length > 0 
            ? g.parsedArtists.map(a => `<span class="clickable-tag ${selectedArtists.has(a) ? 'active-tag' : ''}" onclick="toggleTagFilter('art', '${a}')">${a}</span>`).join('') 
            : g.artist}
        </div>

        <div class="detail-section">
          <strong>Themes:</strong><br>
          ${g.parsedThemes.length > 0 
            ? g.parsedThemes.map(t => `<span class="clickable-tag ${selectedThemes.has(t) ? 'active-tag' : ''}" onclick="toggleTagFilter('theme', '${t}')">${t}</span>`).join('') 
            : 'None'}
        </div>

        <div class="detail-section">
          <strong>Categories:</strong><br>
          ${g.parsedCategories.length > 0 
            ? g.parsedCategories.map(c => `<span class="clickable-tag ${selectedCategories.has(c) ? 'active-tag' : ''}" onclick="toggleTagFilter('cat', '${c}')">${c}</span>`).join('') 
            : 'None'}
        </div>

        <div class="detail-section">
          <strong>Mechanics:</strong><br>
          ${g.parsedMechanics.length > 0 
            ? g.parsedMechanics.map(m => `<span class="clickable-tag ${selectedMechanics.has(m) ? 'active-tag' : ''}" onclick="toggleTagFilter('mech', '${m}')">${m}</span>`).join('') 
            : 'None'}
        </div>

        <div class="detail-section">
          <strong>Status:</strong> ${playStateTag}
        </div>

        ${g.id ? `<a href="${bggUrl}" target="_blank" class="bgg-link-btn">🌐 View on BGG</a>` : ''}
      `;

      detailModal.classList.add('open');

      setTimeout(() => {
        const descElem = document.getElementById('modal-desc');
        const readMoreBtn = document.getElementById('read-more-btn');
        if (descElem && readMoreBtn) {
          if (descElem.scrollHeight > descElem.clientHeight + 2) {
            readMoreBtn.style.display = 'inline-block';
          }
        }
      }, 50);
    }

    function togglePlayStateFilter(state) {
      closeDetailModal();
      if (state === 'played') {
        filterPlayed.checked = !filterPlayed.checked;
        if (filterPlayed.checked) filterUnplayed.checked = false;
      } else if (state === 'unplayed') {
        filterUnplayed.checked = !filterUnplayed.checked;
        if (filterUnplayed.checked) filterPlayed.checked = false;
      }
      renderGames();
      grid.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function toggleTagFilter(prefix, val) {
      closeDetailModal();

      let targetSet, checkboxes;
      if (prefix === 'theme') { targetSet = selectedThemes; checkboxes = document.querySelectorAll('input[data-prefix="theme"]'); }
      else if (prefix === 'cat') { targetSet = selectedCategories; checkboxes = document.querySelectorAll('input[data-prefix="cat"]'); }
      else if (prefix === 'mech') { targetSet = selectedMechanics; checkboxes = document.querySelectorAll('input[data-prefix="mech"]'); }
      else if (prefix === 'pub') { targetSet = selectedPublishers; checkboxes = document.querySelectorAll('input[data-prefix="pub"]'); }
      else if (prefix === 'des') { targetSet = selectedDesigners; checkboxes = document.querySelectorAll('input[data-prefix="des"]'); }
      else if (prefix === 'art') { targetSet = selectedArtists; checkboxes = document.querySelectorAll('input[data-prefix="art"]'); }

      if (targetSet.has(val)) {
        targetSet.delete(val);
      } else {
        targetSet.add(val);
      }

      checkboxes.forEach(cb => {
        if (cb.value === val) cb.checked = targetSet.has(val);
      });

      renderGames();
      grid.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Dynamic mobile vs desktop text / search layout adjustments
    function handleResponsiveLayoutChanges() {
      const isMobile = window.innerWidth <= 600;
      const pickFull = document.querySelector('.btn-text-pick');
      const pickShort = document.querySelector('.btn-text-pick-short');
      const clearFull = document.querySelector('.btn-text-clear');
      const clearShort = document.querySelector('.btn-text-clear-short');
      const mobileSearchSlot = document.querySelector('.mobile-search-slot');
      const desktopSearchSlot = document.querySelector('.desktop-search-slot');

      if (isMobile) {
        if (pickFull) pickFull.style.display = 'none';
        if (pickShort) pickShort.style.display = 'inline';
        if (clearFull) clearFull.style.display = 'none';
        if (clearShort) clearShort.style.display = 'inline';
        if (mobileSearchSlot) mobileSearchSlot.style.display = 'block';
        if (desktopSearchSlot) desktopSearchSlot.style.display = 'none';
      } else {
        if (pickFull) pickFull.style.display = 'inline';
        if (pickShort) pickShort.style.display = 'none';
        if (clearFull) clearFull.style.display = 'inline';
        if (clearShort) clearShort.style.display = 'none';
        if (mobileSearchSlot) mobileSearchSlot.style.display = 'none';
        if (desktopSearchSlot) desktopSearchSlot.style.display = 'block';
      }
    }

    window.addEventListener('resize', handleResponsiveLayoutChanges);
    window.addEventListener('DOMContentLoaded', () => {
      loadCollection();
      handleResponsiveLayoutChanges();
    });
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/collection')
def get_collection():
    if GAMES_CACHE:
        return jsonify(GAMES_CACHE)
        
    json_path = os.path.join(os.path.dirname(__file__), JSON_FILENAME)
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return jsonify(data)
            
    return jsonify([])

if __name__ == '__main__':
    app.run(debug=True, port=5000)

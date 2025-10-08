import pyautogui
import json
import os
from datetime import datetime, timezone
import uuid
import game_gui_navigator as nav
import pytesseract

# --- Config Loading ---
try:
    with open('game_config.json', 'r') as f:
        config = json.load(f)
    pytesseract.pytesseract.tesseract_cmd = config['tesseract_path']
except FileNotFoundError:
    print("FATAL ERROR: game_config.json not found.")
    exit()

STATE_FILE = 'run_state.json'

def load_or_initialize_scan_id():
    """Reads the last scan_id from the state file, or creates it if it doesn't exist."""
    try:
        with open(STATE_FILE, 'r') as f:
            state_data = json.load(f)
            return state_data.get('last_scan_id', -1)
    except FileNotFoundError:
        # If the file doesn't exist, start from scratch
        print(f"[INFO] '{STATE_FILE}' not found. Initializing with scan_id -1.")
        return -1

def save_scan_id(new_id):
    """Saves the new last_scan_id to the state file."""
    state_data = {'last_scan_id': new_id}
    with open(STATE_FILE, 'w') as f:
        json.dump(state_data, f, indent=4)

# --- Helper Flows ---
def select_currency_flow(currency_name, window_config_key):
    print(f"\n--- Starting Currency Selection Flow for '{currency_name}' ---")
    if not nav.perform_action_on_template(window_config_key, action='click'): return False
    print("  [INFO] Waiting for currency selection window to open...")
    nav.human_like_delay(0.75, 1.75)
    
    if not nav.perform_action_on_template("search_box", action='click'): return False
    print("  [INFO] Waiting for search box to activate...")
    nav.human_like_delay(0.25, 0.55)
    nav.type_text(currency_name)
    if not nav.find_and_click_currency_template(currency_name): return False
    print("[INFO] Waiting for currency to be selected...")
    nav.human_like_delay(0.45, 0.75)
    print(f"--- Successfully Selected '{currency_name}' ---")
    return True

# --- Main Capture Function ---
def capture_market_data_for_pair(scan_id, currency_want, currency_have):
    print(f"\n{'='*50}\n--- Starting Data Collection for {currency_want}/{currency_have} ---\n{'='*50}")
    
    # Step 1: Navigate to Trader
    print("\n[STEP 1/4] Navigating to Trader...")
    if not nav.perform_action_on_template("trader_npc", action='click'):
        print("[FATAL] Failed to find trader NPC. Aborting run.")
        return
    print("[INFO] Waiting for character to run to the trader...")
    nav.human_like_delay(1.75, 2.75)
    
    if not nav.perform_action_on_template("dialogue_option", action='click'):
        print("[FATAL] Failed to find dialogue option. Aborting run.")
        return
    print("[SUCCESS] Navigation to trade window complete.")
    print("[INFO] Waiting for trade window to load...")
    nav.human_like_delay(0.75, 1.75)

    # Step 2: Select Currencies
    print("\n[STEP 2/4] Selecting Currencies...")
    if not select_currency_flow(currency_want, "currency_want_window"):
        print(f"[FATAL] Failed to select currency_want: {currency_want}. Aborting run.")
        return
    print("[INFO] Waiting for trade window to load...")
    nav.human_like_delay(0.35, 0.50)
    
    if not select_currency_flow(currency_have, "currency_have_window"):
        print(f"[FATAL] Failed to select currency_have: {currency_have}. Aborting run.")
        return
    print("[SUCCESS] Both currencies selected.")
    print("[INFO] Waiting for trade window to load...")
    nav.human_like_delay(0.35, 0.50)

    # Step 3: Prepare for Screenshot
    print("\n[STEP 3/4] Preparing for Screenshot...")
    if not nav.perform_action_on_template("pre_screenshot_hover_target", action='hover'):
        print("[FATAL] Failed to find pre-screenshot hover target. Aborting run.")
        return
    print("[SUCCESS] Mouse is in position.")

    # Step 4: Capture Screenshot and Metadata
    print("\n[STEP 4/4] Capturing Data...")
    try:
        pyautogui.keyDown('alt')
        print("  [INFO] ALT key down.")
        nav.human_like_delay(0.25, 0.33)

        
        anchor_location = nav.perform_action_on_template("market_data_anchor", action='hover')
        if not anchor_location:
            pyautogui.keyUp('alt')
            print("  [ERROR] Could not find the primary 'available_trades' anchor. Aborting capture.")
            return

        ss_conf = config['navigation']['market_data_anchor']['full_screenshot_zone']
        capture_region = (
            int(anchor_location.left + ss_conf[0]),
            int(anchor_location.top + ss_conf[1]),
            int(ss_conf[2]),
            int(ss_conf[3])
        )
        print(f"  [INFO] Calculated screenshot region: {capture_region}")
        
        screenshots_dir = 'screenshots'
        os.makedirs(screenshots_dir, exist_ok=True)
        lot_id = str(uuid.uuid4())
        
        screenshot_path = os.path.join(screenshots_dir, f'{lot_id}.png')
        pyautogui.screenshot(screenshot_path, region=capture_region)
        print(f"  [SUCCESS] Screenshot saved to {screenshot_path}")
        print(" [INFO] Keeping window up. Like I'm looking at it, or something. ;)")
        nav.human_like_delay(1.75,4)
        pyautogui.keyUp('alt')
        print("  [INFO] ALT key up.")
        
        # Save Metadata
        metadata = {
            "scan_id": scan_id, "lot_id": lot_id,
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "currency_want": currency_want, "currency_have": currency_have,
            "status": "unprocessed"
        }
        metadata_path = os.path.join(screenshots_dir, f'{lot_id}.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=4)
        print(f"  [SUCCESS] Metadata saved for Lot ID: {lot_id}")
        nav.human_like_delay(1, 2)
    except Exception as e:
        pyautogui.keyUp('alt')
        print(f"  [FATAL] An exception occurred during screenshot capture: {e}")

if __name__ == '__main__':
    # Load the last scan_id and increment it for the new run
    last_id = load_or_initialize_scan_id()
    current_scan_id = last_id + 1
    
    print(f"Starting test run with Scan ID: {current_scan_id}")

    capture_market_data_for_pair(
        current_scan_id,
        currency_want="Chaos Orb",
        currency_have="Exalted Orb"
    )

    # Save the new scan_id for the next run
    save_scan_id(current_scan_id)
    print(f"\nTest run finished. Last Scan ID saved: {current_scan_id}")
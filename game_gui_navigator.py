import pyautogui
import json
import os
import uuid
from datetime import datetime, timezone
from game_helper_functions import (
    human_like_delay,
    get_mouse_speed,
    secs_between_keys,
    gaussian_random_point_in_rect,
    retry_action,
    ActionFailedException,
    random_int
)

# --- Config Loading ---
try:
    with open('game_config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("FATAL ERROR: game_config.json not found.")
    exit()


# --- PRIVATE HELPER FUNCTIONS (Internal Logic) ---

def _find_and_click(config_key, action='click', search_region=None, confidence=0.8):
    """Internal function to find a template and perform a mouse action."""
    print(f"[INFO] Searching for template '{config_key}'...")
    item_config = config['navigation'].get(config_key)
    if not item_config:
        raise ActionFailedException(f"Config key '{config_key}' not found in game_config.json")

    template_path = item_config.get('template')
    location = pyautogui.locateOnScreen(template_path, region=search_region, confidence=confidence)

    if not location:
        print(f"  [ERROR] Could not find template '{config_key}'.")
        return None

    print(f"  [SUCCESS] Found '{config_key}' at {location}.")

    if action == 'click':
        click_zone = item_config.get('click_zone')
        if not isinstance(click_zone, list) or len(click_zone) != 4:
            raise ActionFailedException(f"Invalid click_zone for '{config_key}'.")

        zone_x, zone_y = location.left + click_zone[0], location.top + click_zone[1]
        zone_w, zone_h = click_zone[2], click_zone[3]
        target_x, target_y = gaussian_random_point_in_rect(zone_x, zone_y, zone_w, zone_h)

        print(f"  [ACTION] Clicking '{config_key}' at ({target_x}, {target_y})")
        pyautogui.moveTo(target_x, target_y, duration=get_mouse_speed(), tween=pyautogui.easeOutQuad)
        human_like_delay(0.55, 0.70)

        # --- CORRECTED LOGIC: Preserving the special case for the NPC ---
        if config_key == "trader_npc":
            pyautogui.click()  # First click to ensure focus/registration
            pyautogui.click()  # Second click for the actual interaction
            print("  [INFO] Performed special double-click for trader NPC.")
        else:
            pyautogui.mouseDown()
            human_like_delay(0.027, 0.035)
            pyautogui.mouseUp()
        # -----------------------------------------------------------------

    elif action == 'hover':
        hover_zone = item_config.get('hover_zone', [0, 0, location.width, location.height])
        zone_x, zone_y = location.left + hover_zone[0], location.top + hover_zone[1]
        zone_w, zone_h = hover_zone[2], hover_zone[3]
        target_x, target_y = gaussian_random_point_in_rect(zone_x, zone_y, zone_w, zone_h)

        print(f"  [ACTION] Hovering '{config_key}' in zone at ({target_x}, {target_y})")
        pyautogui.moveTo(target_x, target_y, duration=get_mouse_speed())

    return location

def _find_and_click_currency(currency_name):
    """Internal function to find and click a specific currency template."""
    print(f"[INFO] Searching for currency template '{currency_name}'...")
    template_path = config['currency_name_templates'].get(currency_name)
    if not template_path:
        raise ActionFailedException(f"No template for currency '{currency_name}' in config.")

    search_region = config['navigation']['currency_search_results_region']
    location = pyautogui.locateOnScreen(template_path, region=search_region, confidence=0.9)

    if location:
        center = pyautogui.center(location)
        print(f"  [SUCCESS] Found currency '{currency_name}' at {location}.")
        pyautogui.moveTo(center, duration=get_mouse_speed(), tween=pyautogui.easeOutQuad)
        pyautogui.mouseDown()
        human_like_delay(0.05, 0.12)
        pyautogui.mouseUp()
        human_like_delay(0.086, 0.122)
        return True

    print(f"  [ERROR] Could not find template for currency '{currency_name}'.")
    return False

# --- PUBLIC API FUNCTIONS (Called from the main script) ---

def open_trade_window():
    """Finds the NPC, clicks, and navigates the dialogue to open the trade window."""
    print("\n--- Opening Trade Window ---")
    retry_action(_find_and_click, config_key="trader_npc", action='click')
    human_like_delay(1.75, 2.75)
    retry_action(_find_and_click, config_key="dialogue_option", action='click')
    human_like_delay(0.75, 1.75)
    print("[SUCCESS] Trade window is open.")

def select_currency(currency_name, window_config_key):
    """Selects a currency in either the 'want' or 'have' window."""
    print(f"\n--- Selecting '{currency_name}' in '{window_config_key}' ---")
    retry_action(_find_and_click, config_key=window_config_key, action='click')
    human_like_delay(0.75, 1.75)
    retry_action(_find_and_click, config_key="search_box", action='click')
    human_like_delay(0.25, 0.55)

    print(f"[ACTION] Typing: '{currency_name}'")
    pyautogui.typewrite(currency_name, interval=secs_between_keys())

    retry_action(_find_and_click_currency, currency_name=currency_name)
    human_like_delay(0.45, 0.75)
    print(f"[SUCCESS] Selected '{currency_name}'.")

def capture_market_data(scan_id, currency_want, currency_have):
    """Hovers, presses ALT, finds the anchor, and takes a screenshot."""
    print("\n--- Capturing Market Data ---")
    try:
        retry_action(_find_and_click, config_key="pre_screenshot_hover_target", action='hover')
        random_x_movement = random_int(1,10)
        random_x_movement_return = random_x_movement - random_int(0,3)
        random_y_movement = random_int(-3,3)
        random_y_movement_return = random_y_movement - random_int(-1,1)
        pyautogui.moveRel(random_x_movement, random_y_movement, duration=get_mouse_speed(), tween=pyautogui.easeOutQuad)
        pyautogui.moveRel(-random_x_movement_return, -random_y_movement_return, duration=get_mouse_speed(), tween=pyautogui.easeOutQuad)
        
        pyautogui.keyDown('alt')
        print("  [INFO] ALT key down.")
        human_like_delay(0.095, 0.13)
        pyautogui.keyUp('alt')
        pyautogui.keyDown('alt')
        human_like_delay(0.095, 0.13)

        anchor_location = retry_action(
            pyautogui.locateOnScreen,
            image=config['navigation']['market_data_anchor']['template'],
            confidence=0.8
        )
        print(f"  [SUCCESS] Found anchor at {anchor_location}")

        ss_conf = config['navigation']['market_data_anchor']['full_screenshot_zone']
        capture_region = (
            int(anchor_location.left + ss_conf[0]),
            int(anchor_location.top + ss_conf[1]),
            int(ss_conf[2]),
            int(ss_conf[3])
        )
        screenshots_dir = 'screenshots'
        os.makedirs(screenshots_dir, exist_ok=True)
        lot_id = str(uuid.uuid4())
        screenshot_path = os.path.join(screenshots_dir, f'{lot_id}.png')
        pyautogui.screenshot(screenshot_path, region=capture_region)
        print(f"  [SUCCESS] Screenshot saved to {screenshot_path}")

        human_like_delay(1.75, 3)

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

    finally:
        pyautogui.keyUp('alt')
        print("  [INFO] ALT key up.")

def close_trade_window():
    """Presses the Escape key to close the main trade window."""
    print("\n--- Closing Trade Window ---")
    pyautogui.press('esc')
    human_like_delay(1.0, 1.5) # Wait for the window to close
    print("[SUCCESS] Trade window closed. Returning to main game world.")
import pyautogui
import json
from game_helper_functions import (
    human_like_delay,
    get_mouse_speed,
    secs_between_keys,
    gaussian_random_point_in_rect
)

try:
    with open('game_config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("FATAL ERROR: game_config.json not found.")
    exit()


def perform_action_on_template(config_key, action='click', search_region=None, confidence=0.8):
    try:
        print(f"[INFO] Searching for template '{config_key}'...")
        item_config = config['navigation'].get(config_key)
        template_path = item_config.get('template')
        
        location = pyautogui.locateOnScreen(template_path, region=search_region, confidence=confidence)
        if not location:
            print(f"  [ERROR] Could not find template '{config_key}' with confidence {confidence}.")
            return None
        
        print(f"  [SUCCESS] Found '{config_key}' at {location}.")

        if action == 'click':
            click_zone_relative = item_config.get('click_zone')
            
            # BUG FIX: Ensure the click_zone is a valid, non-empty list
            if not isinstance(click_zone_relative, list) or len(click_zone_relative) != 4:
                print(f"  [ERROR] Invalid or empty click_zone for '{config_key}'. Aborting click.")
                return None

            zone_x = location.left + click_zone_relative[0]
            zone_y = location.top + click_zone_relative[1]
            zone_width, zone_height = click_zone_relative[2], click_zone_relative[3]
            target_x, target_y = gaussian_random_point_in_rect(zone_x, zone_y, zone_width, zone_height)
            
            print(f"  [ACTION] Clicking '{config_key}' at ({target_x}, {target_y})")
            pyautogui.moveTo(target_x, target_y, duration=get_mouse_speed(), tween=pyautogui.easeOutQuad)
            human_like_delay(0.35, 0.45)
            pyautogui.mouseDown()
            human_like_delay(0.05, 0.08) # Hold the click for a brief, human-like duration
            pyautogui.mouseUp()
            if config_key == "trader_npc":
                pyautogui.click()  # Ensure the click is registered
        elif action == 'hover':
            hover_zone_relative = item_config.get('hover_zone')
            if not hover_zone_relative or len(hover_zone_relative) != 4:
                target_x, target_y = pyautogui.center(location)
                print(f"  [ACTION] Hovering '{config_key}' at center ({target_x}, {target_y})")
            else:
                zone_x = location.left + hover_zone_relative[0]
                zone_y = location.top + hover_zone_relative[1]
                zone_width, zone_height = hover_zone_relative[2], hover_zone_relative[3]
                target_x, target_y = gaussian_random_point_in_rect(zone_x, zone_y, zone_width, zone_height)
                print(f"  [ACTION] Hovering '{config_key}' in zone at ({target_x}, {target_y})")
            
            pyautogui.moveTo(target_x, target_y, duration=get_mouse_speed())

        return location
    except Exception as e:
        print(f"  [FATAL] An exception occurred in perform_action_on_template for {config_key}: {e}")
        return None

def type_text(text):
    print(f"[ACTION] Typing: '{text}'")
    pyautogui.typewrite(text, interval=secs_between_keys())

def find_and_click_currency_template(currency_name):
    print(f"[INFO] Searching for currency template '{currency_name}'...")
    template_path = config['currency_name_templates'].get(currency_name)
    if not template_path:
        print(f"  [ERROR] No template path for currency '{currency_name}' in config.")
        return False
    
    search_region = config['navigation']['currency_search_results_region']
    location = pyautogui.locateOnScreen(template_path, region=search_region, confidence=0.9)
    if location:
        center = pyautogui.center(location)
        print(f"  [SUCCESS] Found currency '{currency_name}' at {location}.")
        print(f"  [ACTION] Clicking currency at {center}.")
        pyautogui.click(center)
        return True
    
    print(f"  [ERROR] Could not find template for currency '{currency_name}'.")
    return False
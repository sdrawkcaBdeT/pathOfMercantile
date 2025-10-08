import pyautogui
import pyperclip
import json  # Import the json library
from helper_functions import (
    random_int,
    human_like_delay,
    get_mouse_speed,
    get_typing_interval,
)

# --- Load Configuration ---
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    COORDS = config['navigation']
except FileNotFoundError:
    print("Error: config.json not found. Please create it.")
    exit()

# --- Core Navigation Functions ---

def click_on_screen(coords, description="button"):
    """
    Clicks at a random location within a defined rectangular area.
    The 'coords' argument should be a list: [x1, y1, x2, y2].
    """
    try:
        x1, y1, x2, y2 = coords
        x = random_int(x1, x2)
        y = random_int(y1, y2)
        print(f"Clicking '{description}' at ({x}, {y})")
        pyautogui.moveTo(x, y, duration=get_mouse_speed(), tween=pyautogui.easeOutQuad)
        pyautogui.click()
        human_like_delay(0.3, 0.6)
    except Exception as e:
        print(f"Error clicking {description}: {e}")

def type_text(text):
    """Types the given text with a human-like interval between keystrokes."""
    print(f"Typing: '{text}'")
    pyperclip.copy(text)
    pyautogui.hotkey('ctrl', 'v')
    human_like_delay(0.2, 0.5)

# --- Application-Specific Workflow ---

def navigate_to_trader():
    """Navigates from the main menu/lobby to the trader interface."""
    print("Navigating to the trader...")
    click_on_screen(COORDS['trader_button'], description="Trader Button")
    human_like_delay()

def search_for_currency(currency_name):
    """Searches for a specific currency in the trader's search box."""
    print(f"Searching for currency: {currency_name}")
    click_on_screen(COORDS['search_box'], description="Search Text Box")
    type_text(currency_name)
    click_on_screen(COORDS['first_search_result'], description="First Search Result")
    human_like_delay()

def select_trading_pair(currency_have, currency_want):
    """Full sequence to select the desired trading pair."""
    print(f"Attempting to select trading pair: {currency_want}/{currency_have}")
    navigate_to_trader()
    # Add other steps as needed
    print("Navigation to the target trading screen is complete.")
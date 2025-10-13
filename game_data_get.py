import sys
import json
import time
import game_gui_navigator as nav
from game_helper_functions import ActionFailedException

# --- Config and State Management ---
STATE_FILE = 'run_state.json'
CONFIG_FILE = 'trade_config.json'

def load_or_initialize_scan_id():
    """Reads the last scan_id from the state file, or creates it if it doesn't exist."""
    try:
        with open(STATE_FILE, 'r') as f:
            state_data = json.load(f)
            return state_data.get('last_scan_id', -1)
    except FileNotFoundError:
        print(f"[INFO] '{STATE_FILE}' not found. Initializing with scan_id -1.")
        return -1

def save_scan_id(new_id):
    """Saves the new last_scan_id to the state file."""
    state_data = {'last_scan_id': new_id}
    with open(STATE_FILE, 'w') as f:
        json.dump(state_data, f, indent=4)


if __name__ == '__main__':
    # --- Load all configuration from the JSON file ---
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        TRADE_SESSIONS = config['trade_sessions']
        CYCLE_WAIT_SECONDS = config['cycle_wait_seconds']
        NUMBER_OF_CYCLES = config['number_of_cycles']
    except FileNotFoundError:
        print(f"[FATAL] The configuration file '{CONFIG_FILE}' was not found. Aborting.")
        sys.exit(1)
    except KeyError as e:
        print(f"[FATAL] The configuration file is missing a required key: {e}. Aborting.")
        sys.exit(1)

    # --- Main Loop ---
    for cycle_num in range(NUMBER_OF_CYCLES):
        last_id = load_or_initialize_scan_id()
        current_scan_id = last_id + 1
        print(f"\n{'='*60}\n--- STARTING CYCLE {cycle_num + 1}/{NUMBER_OF_CYCLES} | SCAN ID: {current_scan_id} ---\n{'='*60}")
        save_scan_id(current_scan_id)

        # --- Phase 1: Open Trade Window (Once per cycle) ---
        try:
            print("\n[PHASE 1/2] Performing initial setup...")
            nav.open_trade_window()
            print("\n[SUCCESS] Trade window is open for this cycle.")
        except ActionFailedException as e:
            print(f"\n[FATAL] A critical error occurred during setup: {e}")
            print(f"[FATAL] Aborting this cycle. Retrying in {CYCLE_WAIT_SECONDS} seconds.")
            nav.close_trade_window()
            if cycle_num < NUMBER_OF_CYCLES - 1:
                time.sleep(CYCLE_WAIT_SECONDS)
            continue

        # --- Phase 2: Loop Through Trade Sessions ---
        print("\n[PHASE 2/2] Starting data collection sessions...")
        for session in TRADE_SESSIONS:
            base_currency = session["base_currency"]
            target_currencies = session["target_currencies"]

            print(f"\n--- Starting Trade Session: Base Currency = {base_currency} ---")

            try:
                # --- NEW LOGIC: Just select the base currency, don't re-open the window ---
                nav.select_currency(base_currency, "currency_have_window")
                print(f"[SUCCESS] Base currency '{base_currency}' selected.")
            except ActionFailedException as e:
                print(f"\n[ERROR] Failed to set base currency to '{base_currency}': {e}")
                print("[ERROR] Aborting this session.")
                continue # Skip to the next session

            # --- Data Collection for the current session ---
            for target_currency in target_currencies:
                print(f"\n--- Processing Pair: {target_currency} vs. {base_currency} ---")
                try:
                    nav.select_currency(target_currency, "currency_want_window")
                    nav.human_like_delay(0.35, 0.50)
                    nav.capture_market_data(
                        scan_id=current_scan_id,
                        currency_want=target_currency,
                        currency_have=base_currency
                    )
                    print(f"[SUCCESS] Successfully captured data for {target_currency}.")
                except ActionFailedException as e:
                    print(f"\n[ERROR] Failed to process '{target_currency}'. Reason: {e}")
                    print("[ERROR] Skipping to the next currency in this session.")
                    continue

        # --- Close the trade window at the very end of the cycle ---
        print("\n--- All sessions for this cycle are complete. Closing trade window. ---")
        nav.close_trade_window()

        # --- Wait at the end of a full cycle ---
        if cycle_num < NUMBER_OF_CYCLES - 1:
            print(f"\n--- CYCLE {cycle_num + 1} COMPLETE ---")
            print(f"--- WAITING for {CYCLE_WAIT_SECONDS} seconds before next cycle ---")
            time.sleep(CYCLE_WAIT_SECONDS)

    print(f"\n{'='*60}\n--- ALL {NUMBER_OF_CYCLES} CYCLES COMPLETE. SCRIPT FINISHED. ---\n{'='*60}")
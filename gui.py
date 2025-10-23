import tkinter as tk
from tkinter import font as tkFont, messagebox, simpledialog
import json
import time
import csv
import subprocess
import sys # Added sys
import pandas as pd # Added pandas
from dateutil import parser as dateParser # Added dateutil.parser
from pathlib import Path
from datetime import datetime
import win32api
import keyboard

# --- Configuration & Style Constants ---
# Shared files (ensure paths match arbitrage_opportunity.py)
BASE_SHARED_DIR = Path('P:\\') # Assuming P: drive is the base
ARBITRAGE_ALERT_FILE = BASE_SHARED_DIR / 'arbitrage_alert.json'
TRADE_CONFIG_FILE = BASE_SHARED_DIR / 'trade_config.json'

# Local files (in the same directory as this script)
MY_CURRENCY_FILE = Path('my_currency.json')
EXECUTED_TRADES_FILE = Path('executed_trades.csv')
GAME_SCANNER_SCRIPT = Path('game_data_get.py') # Adjust if it's elsewhere

# --- [ NEW ] ---
# Log files to read
WEALTH_LOG_FILE = Path('wealth_log.csv')
ROBUST_RATES_LOG_FILE = Path('robust_rates_log.csv')
# --- [ END NEW ] ---


POLL_INTERVAL_MS = 1000      # Check for updates every 1 second
WEALTH_POLL_INTERVAL_MS = 10000 # Check for wealth updates every 10 seconds

TEXT_COLOR = "#ffff00"        # Yellow text
BACKGROUND_COLOR = "black"    # Black background
WINDOW_OPACITY = 0.90         # Window opacity
FONT_FAMILY = "Consolas"
FONT_SIZE = 11
LINE_SPACING = 18

# Main overlay window dimensions
WINDOW_WIDTH = 650
WINDOW_HEIGHT = 250

# --- [ NEW ] ---
# Wealth tracker window dimensions
WEALTH_WINDOW_WIDTH = 250
WEALTH_WINDOW_HEIGHT = 220
# --- [ END NEW ] ---


# --- Helper Function for CSV Logging (Unchanged) ---
def append_to_csv(filepath, header, data_row):
    """Appends a row to a CSV file, creating it with header if needed."""
    file_exists = filepath.exists()
    try:
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists or filepath.stat().st_size == 0:
                writer.writerow(header)
            writer.writerow(data_row)
        return True
    except IOError as e:
        print(f"Error writing to {filepath}: {e}")
        return False

# --- The Main Overlay Class (Unchanged) ---
class ArbitrageOverlay(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master = master # Keep reference to root

        self.last_alert_timestamp = None
        self.dismissed_timestamp = None
        self.current_alert_data = None

        # --- Window Configuration ---
        self.overrideredirect(False)
        self.attributes("-topmost", True)
        self.attributes("-alpha", WINDOW_OPACITY)
        self.configure(bg=BACKGROUND_COLOR)
        self.title("Arbitrage Alert")

        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        x_position = int(round(screen_width * 0.005, 0))
        y_position = int(round(screen_height * 0.075, 0))
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x_position}+{y_position}")

        # --- Widgets ---
        main_frame = tk.Frame(self, bg=BACKGROUND_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(
            main_frame, bg=BACKGROUND_COLOR, highlightthickness=0,
            width=WINDOW_WIDTH - 10, height=WINDOW_HEIGHT - 45
        )
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.display_font = tkFont.Font(family=FONT_FAMILY, size=FONT_SIZE)

        button_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))

        self.log_trade_button = tk.Button(
            button_frame, text="Log Trade", state=tk.DISABLED, width=15,
            command=self.on_log_trade # Assign command
        )
        self.log_trade_button.pack(side=tk.LEFT, padx=10)

        self.dismiss_button = tk.Button(
            button_frame, text="Dismiss", state=tk.DISABLED, width=15,
            command=self.on_dismiss
        )
        self.dismiss_button.pack(side=tk.RIGHT, padx=10)

        # --- Start Polling ---
        self.update_loop()

    # --- Polling and Display Logic (Unchanged)---
    def update_loop(self):
        self.read_alert_file_and_update()
        self.after(POLL_INTERVAL_MS, self.update_loop)

    def read_alert_file_and_update(self):
        try:
            if not ARBITRAGE_ALERT_FILE.exists() or ARBITRAGE_ALERT_FILE.stat().st_size == 0:
                 if self.current_alert_data is not None or self.last_alert_timestamp is not None:
                     self.current_alert_data = None
                     self.last_alert_timestamp = None
                     self.update_display()
                 return

            with open(ARBITRAGE_ALERT_FILE, 'r') as f:
                alert_data = json.load(f)

            alert_ts = alert_data.get("timestamp")
            is_profitable = alert_data.get("profitable", False)
            loop_data = alert_data.get("best_loop")

            if alert_ts == self.dismissed_timestamp: return
            if alert_ts == self.last_alert_timestamp: return

            print(f"New alert data detected (Timestamp: {alert_ts})")
            self.last_alert_timestamp = alert_ts
            self.dismissed_timestamp = None

            if is_profitable and loop_data:
                self.current_alert_data = loop_data
                self.dismiss_button.config(state=tk.NORMAL)
                self.log_trade_button.config(state=tk.NORMAL)
            else:
                self.current_alert_data = None
                self.dismiss_button.config(state=tk.DISABLED)
                self.log_trade_button.config(state=tk.DISABLED)

            self.update_display()

        except FileNotFoundError:
             if self.current_alert_data is not None or self.last_alert_timestamp is not None:
                self.current_alert_data = None
                self.last_alert_timestamp = None
                self.update_display()
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {ARBITRAGE_ALERT_FILE}.")
        except Exception as e:
            print(f"Error reading alert file: {e}")

    def update_display(self):
        self.canvas.delete("all")
        display_text = "Monitoring..."
        scan_id_text = "" # To show current scan status

        # Try to read scan_id even if not profitable
        try:
             if ARBITRAGE_ALERT_FILE.exists() and ARBITRAGE_ALERT_FILE.stat().st_size > 0:
                  with open(ARBITRAGE_ALERT_FILE, 'r') as f:
                       alert_data = json.load(f)
                       scan_id_text = f" (Scan {alert_data.get('scan_id', 'N/A')})"
        except Exception:
             pass # Ignore errors here, just for display

        if self.current_alert_data:
            # --- [ MODIFIED ] ---
            # Profit is now calculated in benchmark, need to show differently
            profit_div = self.current_alert_data.get('profit_benchmark', 0)
            invest_div = self.current_alert_data.get('investment_benchmark', 0)
            path = self.current_alert_data.get('path_string', 'N/A')
            steps = self.current_alert_data.get('steps', [])
            efficiency = self.current_alert_data.get('efficiency', 0)

            summary = f"PROFIT FOUND!{scan_id_text}: +{profit_div:,.2f} DIV (Eff: {efficiency:,.2f})\n"
            summary += f"Path: {path}\n"
            summary += "-" * (WINDOW_WIDTH // 8) # Dynamic separator width
            # --- [ END MODIFIED ] ---
            
            display_text = summary + "\n" + "\n".join(steps)

        elif self.last_alert_timestamp: # If we've seen a file, but it wasn't profitable
             display_text = f"No Profit Found{scan_id_text}."

        else: # Default before any file is read
             display_text = f"Monitoring...{scan_id_text}"


        self.draw_text(display_text)

    def draw_text(self, text):
        """Draws multi-line text onto the canvas."""
        lines = text.strip().split("\n")
        y_offset = 5
        for line in lines:
            # Shorten long lines if they exceed canvas width (simple truncate)
            max_chars = int((self.canvas.winfo_width() - 10) / (self.display_font.measure("W") * 0.8)) # Estimate char width
            display_line = (line[:max_chars-3] + '...') if len(line) > max_chars else line

            self.canvas.create_text(
                5, y_offset, text=display_line, fill=TEXT_COLOR,
                anchor="nw", font=self.display_font
            )
            y_offset += LINE_SPACING

    # --- Button Commands (MODIFIED for new data structure) ---
    def on_dismiss(self):
        """Handles the Dismiss button click."""
        print("Alert dismissed.")
        self.dismissed_timestamp = self.last_alert_timestamp
        self.current_alert_data = None
        self.dismiss_button.config(state=tk.DISABLED)
        self.log_trade_button.config(state=tk.DISABLED)
        self.update_display()

    def on_log_trade(self):
        """Logs the currently displayed trade and dismisses it."""
        if not self.current_alert_data:
            messagebox.showwarning("Log Error", "No active profitable loop data to log.")
            return

        print("Logging executed trade...")
        scan_id = "N/A"
        # Try to get scan_id from the source file for logging context
        try:
             if ARBITRAGE_ALERT_FILE.exists() and ARBITRAGE_ALERT_FILE.stat().st_size > 0:
                  with open(ARBITRAGE_ALERT_FILE, 'r') as f:
                       alert_data = json.load(f)
                       scan_id = alert_data.get('scan_id', 'N/A')
        except Exception:
             pass

        # --- [ MODIFIED ] ---
        # Log the benchmark profit and investment
        header = ["Timestamp", "ScanID", "Path", "StartCurrency", "InvestmentRaw", "InvestmentBenchmark", "ProfitBenchmark", "GoldCost", "Efficiency"]
        data_row = [
            datetime.now().isoformat(),
            scan_id,
            self.current_alert_data.get('path_string', 'N/A'),
            self.current_alert_data.get('start_currency', 'N/A'),
            self.current_alert_data.get('investment', 0),
            self.current_alert_data.get('investment_benchmark', 0),
            self.current_alert_data.get('profit_benchmark', 0),
            self.current_alert_data.get('gold_cost', 0),
            self.current_alert_data.get('efficiency', 0)
        ]
        # --- [ END MODIFIED ] ---

        if append_to_csv(EXECUTED_TRADES_FILE, header, data_row):
            print("Trade logged successfully.")
            messagebox.showinfo("Log Trade", "Trade logged successfully.")
            self.on_dismiss() # Dismiss after successful logging
        else:
            messagebox.showerror("Log Error", f"Failed to write to {EXECUTED_TRADES_FILE}.")


# --- [ NEW ] ---
# --- Wealth Tracker Window Class ---
class WealthTrackerWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.visible = True
        
        self.title("Wealth Tracker")
        self.overrideredirect(False)
        self.attributes("-topmost", True)
        self.attributes("-alpha", WINDOW_OPACITY)
        self.configure(bg=BACKGROUND_COLOR)
        
        # Position it relative to the main window
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        main_x = int(round(screen_width * 0.005, 0))
        main_y = int(round(screen_height * 0.075, 0))
        
        # Place it to the right of the main window
        x_position = main_x + WINDOW_WIDTH + 10 
        y_position = main_y
        self.geometry(f"{WEALTH_WINDOW_WIDTH}x{WEALTH_WINDOW_HEIGHT}+{x_position}+{y_position}")

        self.canvas = tk.Canvas(
            self, bg=BACKGROUND_COLOR, highlightthickness=0,
            width=WEALTH_WINDOW_WIDTH - 10, height=WEALTH_WINDOW_HEIGHT - 10
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.display_font = tkFont.Font(family=FONT_FAMILY, size=FONT_SIZE)
        
        self.protocol("WM_DELETE_WINDOW", self.toggle_visibility) # Hide on 'X'
        
        self.update_loop()

    def toggle_visibility(self):
        """Toggles the window's visibility."""
        if self.visible:
            self.withdraw()
            self.visible = False
        else:
            self.deiconify()
            self.visible = True

    def update_loop(self):
        """The main refresh loop for this window."""
        self.update_wealth_display()
        self.after(WEALTH_POLL_INTERVAL_MS, self.update_loop)

    def draw_text_list(self, lines):
        """Draws a list of strings to the canvas."""
        self.canvas.delete("all")
        y_offset = 5
        self.canvas.create_text(
            5, y_offset, text="Recent Wealth (in DIV)", fill=TEXT_COLOR,
            anchor="nw", font=tkFont.Font(family=FONT_FAMILY, size=FONT_SIZE, weight="bold")
        )
        y_offset += LINE_SPACING + 2
        
        for line in lines:
            self.canvas.create_text(
                5, y_offset, text=line, fill=TEXT_COLOR,
                anchor="nw", font=self.display_font
            )
            y_offset += LINE_SPACING

    def update_wealth_display(self):
        """Reads logs, calculates wealth, and updates the canvas."""
        display_lines = ["Loading..."]
        
        try:
            # 1. Read most recent robust rates
            if not ROBUST_RATES_LOG_FILE.exists():
                self.draw_text_list(["Rates log not found."])
                return
            
            rates_df = pd.read_csv(ROBUST_RATES_LOG_FILE)
            if rates_df.empty:
                self.draw_text_list(["Rates log is empty."])
                return
                
            # Find the most recent timestamp and filter for it
            most_recent_timestamp = rates_df['timestamp'].max()
            latest_rates_df = rates_df[rates_df['timestamp'] == most_recent_timestamp]
            
            # Create a currency:rate dictionary
            rates_map = pd.Series(
                latest_rates_df.value_in_benchmark.values, 
                index=latest_rates_df.currency
            ).to_dict()

            # 2. Read last 10 wealth log entries
            if not WEALTH_LOG_FILE.exists():
                self.draw_text_list(["Wealth log not found."])
                return
                
            wealth_df = pd.read_csv(WEALTH_LOG_FILE)
            if wealth_df.empty:
                self.draw_text_list(["Wealth log is empty."])
                return
            
            last_10_rows = wealth_df.tail(70)
            
            # Get currency columns (all columns except 'Timestamp')
            currency_columns = [col for col in last_10_rows.columns if col != 'Timestamp']
            
            display_lines = []
            
            # 3. Calculate and format
            for _, row in last_10_rows.iterrows():
                total_wealth_in_div = 0.0
                for currency in currency_columns:
                    amount = row.get(currency, 0)
                    rate = rates_map.get(currency, 0.0)
                    total_wealth_in_div += amount * rate
                
                # Format timestamp
                try:
                    ts = dateParser.parse(row['Timestamp'])
                    formatted_ts = ts.strftime('%m/%d %H:%M')
                except Exception:
                    formatted_ts = "??/?? ??:??"
                
                display_lines.append(f"{formatted_ts} | {total_wealth_in_div:,.2f}")

        except pd.errors.EmptyDataError:
            display_lines = ["Logs are empty."]
        except FileNotFoundError as e:
            display_lines = [f"Error: File not found.", f"{e.filename}"]
        except Exception as e:
            print(f"Error updating wealth: {e}")
            display_lines = ["Error updating.", f"{type(e).__name__}"]
            
        self.draw_text_list(display_lines)
# --- [ END NEW ] ---


# --- Functions for Hotkeys (Unchanged) ---

def open_edit_investments_window(root):
    """Opens a window to edit my_currency.json."""
    try:
        with open(MY_CURRENCY_FILE, 'r') as f:
            current_investments = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        current_investments = {"Divine Orb": 0, "Chaos Orb": 0, "Exalted Orb": 0} # Default structure
        messagebox.showwarning("File Error", f"{MY_CURRENCY_FILE} not found or invalid. Using defaults.")

    edit_win = tk.Toplevel(root)
    edit_win.title("Edit Currency Amounts")
    edit_win.geometry("300x250") # Adjust size as needed
    edit_win.attributes("-topmost", True)

    entries = {}
    row_num = 0
    for currency, amount in current_investments.items():
        label = tk.Label(edit_win, text=f"{currency}:")
        label.grid(row=row_num, column=0, padx=5, pady=5, sticky="w")
        entry = tk.Entry(edit_win, width=15)
        entry.insert(0, str(amount))
        entry.grid(row=row_num, column=1, padx=5, pady=5)
        entries[currency] = entry
        row_num += 1

    def save_investments():
        new_investments = {}
        try:
            for currency, entry in entries.items():
                new_investments[currency] = int(entry.get()) # Basic validation

            with open(MY_CURRENCY_FILE, 'w') as f:
                json.dump(new_investments, f, indent=4)
            print(f"Saved new amounts to {MY_CURRENCY_FILE}")

            # Log wealth after saving
            log_wealth(new_investments)

            edit_win.destroy()
            messagebox.showinfo("Save Success", "Currency amounts updated.")
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid integer amounts.")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save file: {e}")

    save_button = tk.Button(edit_win, text="Save", command=save_investments)
    save_button.grid(row=row_num, column=0, columnspan=2, pady=10)

def log_wealth(currency_data):
    """Appends current currency amounts to the wealth log CSV."""
    print("Logging wealth...")
    # Ensure all expected currencies are present for consistent columns
    
    # --- [ MODIFIED ] ---
    # Try to read existing header to maintain column order
    try:
        if WEALTH_LOG_FILE.exists():
            with open(WEALTH_LOG_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)
                # Remove timestamp from header columns
                header.pop(0)
        else:
             # Fallback to keys if file doesn't exist
             header = sorted(currency_data.keys())
    except Exception:
         header = sorted(currency_data.keys()) # Fallback on any read error
    
    # --- [ END MODIFIED ] ---
    
    data_row = [datetime.now().isoformat()] + [currency_data.get(h, 0) for h in header] # Get values in header order
    full_header = ["Timestamp"] + header

    if append_to_csv(WEALTH_LOG_FILE, full_header, data_row):
        print("Wealth logged successfully.")
    else:
        print(f"Failed to log wealth to {WEALTH_LOG_FILE}.")


def open_config_in_notepad():
    """Opens the shared trade_config.json in Notepad."""
    try:
        print(f"Opening {TRADE_CONFIG_FILE} in Notepad...")
        subprocess.Popen(['notepad.exe', str(TRADE_CONFIG_FILE)])
    except FileNotFoundError:
         messagebox.showerror("Error", f"Could not find Notepad. Is it in your system's PATH?")
    except Exception as e:
        messagebox.showerror("Error", f"Could not open config file: {e}")

def trigger_scan():
    """Triggers the game_data_get.py script after confirmation."""
    if messagebox.askyesno("Confirm Scan", "Make sure the game is focused and ready.\n\nStart a new market scan?"):
        try:
            print("Triggering game data scan...")
            subprocess.Popen([sys.executable, str(GAME_SCANNER_SCRIPT)]) # Use sys.executable
            print("Scan script launched.")
        except FileNotFoundError:
             messagebox.showerror("Error", f"Scan script not found at {GAME_SCANNER_SCRIPT}. Please check the path.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch scan script: {e}")

# --- [ MODIFIED ] ---
def on_closing(overlay, wealth_window, root):
    """Handles closing of the application."""
    print("Closing application...")
    try:
        # Unregister all hotkeys
        keyboard.unhook_all()
    except Exception as e:
        print(f"Warning: Could not unhook all hotkeys: {e}")

    if overlay:
        overlay.destroy()
    if wealth_window:
        wealth_window.destroy()
    if root:
        root.quit()

# --- [ END MODIFIED ] ---


# --- Main Execution & Hotkey Setup ---
if __name__ == "__main__":
    # Need to add pandas to requirements
    try:
        import pandas as pd
        import dateutil.parser
    except ImportError:
        print("Error: 'pandas' or 'python-dateutil' is not installed.")
        print("Please run: pip install pandas python-dateutil")
        sys.exit(1)
        
    root = tk.Tk()
    root.withdraw()

    overlay = ArbitrageOverlay(root)
    # --- [ NEW ] ---
    wealth_window = WealthTrackerWindow(root)
    
    def toggle_wealth_window():
        wealth_window.toggle_visibility()
    # --- [ END NEW ] ---


    # --- Setup Hotkeys ---
    keyboard.add_hotkey("ctrl+e", lambda: open_edit_investments_window(root))
    keyboard.add_hotkey("ctrl+t", open_config_in_notepad)
    keyboard.add_hotkey("ctrl+1", trigger_scan)
    # --- [ NEW ] ---
    keyboard.add_hotkey("ctrl+w", toggle_wealth_window)
    keyboard.add_hotkey("ctrl+q", lambda: on_closing(overlay, wealth_window, root))
    # --- [ END NEW ] ---

    print("--- Arbitrage Overlay GUI Started ---")
    print("Hotkeys:")
    print("  Ctrl+E: Edit Currency Amounts")
    print("  Ctrl+T: Edit Trade Config (Notepad)")
    print("  Ctrl+1: Start Game Scan (Confirm First!)")
    print("  Ctrl+W: Toggle Wealth Tracker")
    print("  Ctrl+Q: Quit Overlay")
    print("------------------------------------")

    # --- [ MODIFIED ] ---
    overlay.protocol("WM_DELETE_WINDOW", lambda: on_closing(overlay, wealth_window, root))
    # --- [ END MODIFIED ] ---

    try:
        root.mainloop()
    except KeyboardInterrupt:
        on_closing(overlay, wealth_window, root)
    finally:
         # Final attempt to unhook hotkeys on exit
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        print("--- Overlay Shutdown Complete ---")
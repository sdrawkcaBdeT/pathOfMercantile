import os
import shutil
import time
import json
import csv
from datetime import datetime
from pathlib import Path
import threading
from collections import defaultdict

from docstrange import DocumentExtractor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- 1. Define the directory structure ---
BASE_SCREENSHOT_DIR = Path("D:\\mercantile_processing") # Your laptop's path
PENDING_DIR = BASE_SCREENSHOT_DIR / "pending"
COMPLETED_DIR = BASE_SCREENSHOT_DIR / "completed"
FAILED_DIR = BASE_SCREENSHOT_DIR / "failed"

# --- 2. Define global constants ---
MASTER_CSV_FILE = BASE_SCREENSHOT_DIR / "market_data.csv"
TRADE_CONFIG_FILE = BASE_SCREENSHOT_DIR / "trade_config.json"
OCR_COMPLETE_FILE = BASE_SCREENSHOT_DIR / "ocr_complete.json"

# --- 3. All Helper Functions (Unchanged) ---
def wait_for_file_stable(file_path, stability_delay_sec=0.5, max_wait_sec=5.0):
    """Waits for a file to stop growing."""
    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        try:
            last_size = os.path.getsize(file_path)
            time.sleep(stability_delay_sec)
            current_size = os.path.getsize(file_path)

            if last_size == current_size and current_size > 0:
                print(f"   [INFO] File '{os.path.basename(file_path)}' is stable at {current_size} bytes.")
                return True
            elif current_size == 0:
                print(f"   [INFO] Waiting for '{os.path.basename(file_path)}' to be written (size 0)...")
            else:
                print(f"   [INFO] File '{os.path.basename(file_path)}' is still writing...")

        except FileNotFoundError:
            print(f"   [INFO] Waiting for '{os.path.basename(file_path)}' to appear...")
            time.sleep(stability_delay_sec)
        except Exception as e:
            print(f"   [WARN] Error checking file stability for {os.path.basename(file_path)}: {e}")
            return False

    print(f"   [ERROR] File '{os.path.basename(file_path)}' did not stabilize after {max_wait_sec}s.")
    return False

def robust_move(src_path, dst_path, retries=5, delay=0.5):
    """Tries to move a file, retrying on locks."""
    for i in range(retries):
        try:
            shutil.move(src_path, dst_path)
            return True
        except (PermissionError, OSError) as e:
            if "being used by another process" in str(e) and i < retries - 1:
                print(f"   [RETRY] File '{os.path.basename(src_path)}' is locked. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"   [FATAL MOVE ERROR] Could not move '{os.path.basename(src_path)}'. Error: {e}")
                raise e
    return False

def setup_local_extractor():
    """Initializes the DocumentExtractor."""
    print("Initializing the document extractor in local GPU mode...")
    try:
        extractor = DocumentExtractor(
            gpu=True,
            preserve_layout=True,
            ocr_enabled=True
        )
        print("Extractor initialized successfully.")
        return extractor
    except RuntimeError as e:
        print(f"CRITICAL ERROR: Could not initialize in GPU mode.")
        print(f"   Reason: {e}")
        return None

def parse_ratio(ratio_str):
    """Parses a ratio string."""
    if not ratio_str: return 0.0
    try:
        clean_text = ratio_str.strip().replace('<', '').replace('>', '').replace(' ', '').replace(',', '')
        parts = clean_text.split(':')
        want_val = float(parts[0])
        have_val = float(parts[1]) if len(parts) > 1 else 1.0
        if have_val == 0:
            return 0.0
        return want_val / have_val
    except (ValueError, IndexError, AttributeError) as e:
        print(f"   Warning: Could not parse ratio '{ratio_str}'. Error: {e}. Defaulting to 0.0")
        return 0.0

def transform_and_save_data(ocr_data, screenshot_filename, scan_metadata, output_csv_path):
    """Transforms and saves data to CSV."""
    scan_id = scan_metadata.get("scan_id", 0)
    lot_id = scan_metadata.get("lot_id", os.path.splitext(screenshot_filename)[0])
    timestamp_utc = scan_metadata.get("timestamp_utc")
    currency_want = scan_metadata.get("currency_want", "Unknown")
    currency_have = scan_metadata.get("currency_have", "Unknown")

    rows_to_write = []
    trade_types = {
        "available_trades": "available_trades",
        "competing_trades": "competing_trades"
    }

    for trade_key, trade_type_name in trade_types.items():
        if trade_key in ocr_data:
            for i, trade in enumerate(ocr_data[trade_key]):
                if isinstance(trade, dict) and "ratio" in trade and "stock" in trade:
                    ratio_val = parse_ratio(trade['ratio'])
                    stock_val = trade['stock']
                    row = [
                        scan_id, lot_id, timestamp_utc,
                        currency_want, currency_have, trade_type_name,
                        i + 1, ratio_val, stock_val
                    ]
                    rows_to_write.append(row)
                else:
                    print(f"   Warning: Skipping malformed trade data in '{screenshot_filename}': {trade}")
    if not rows_to_write:
        print(f"   Info: No valid trade data was transformed for '{screenshot_filename}'.")
        return
    try:
        file_exists = os.path.isfile(output_csv_path)
        file_is_empty = os.path.getsize(output_csv_path) == 0 if file_exists else True
        with open(output_csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists or file_is_empty:
                writer.writerow([
                    "scan_id", "lot_id", "timestamp_utc", "currency_want",
                    "currency_have", "trade_type", "row_num", "ratio", "stock"
                ])
            writer.writerows(rows_to_write)
    except IOError as e:
        print(f"   Error: Could not write to '{output_csv_path}': {e}")


# --- MODIFIED: process_screenshot_job ---
def process_screenshot_job(png_path, extractor):
    """
    Core job. Returns scan_metadata on success, None on failure.
    """
    base_filename = os.path.basename(png_path)
    filename_no_ext = os.path.splitext(base_filename)[0]
    json_path = PENDING_DIR / f"{filename_no_ext}.json" # Use Pathlib

    completed_png_path = COMPLETED_DIR / base_filename
    completed_json_path = COMPLETED_DIR / f"{filename_no_ext}.json"
    failed_png_path = FAILED_DIR / base_filename
    failed_json_path = FAILED_DIR / f"{filename_no_ext}.json"

    scan_metadata = None
    try:
        if not wait_for_file_stable(png_path):
            raise Exception(f"PNG file {base_filename} never stabilized.")

        if not wait_for_file_stable(json_path):
            raise Exception(f"JSON file {json_path.name} never stabilized.")

        with open(json_path, 'r', encoding='utf-8') as f:
            scan_metadata = json.load(f)

        print(f"   Processing image: {base_filename}...")
        result_text = extractor.extract(str(png_path)).extract_text().strip() # Need str() for extractor

        if not result_text:
            raise ValueError("OCR extraction returned no text.")

        try:
            ocr_data = json.loads(result_text)
        except json.JSONDecodeError:
            print(f"   Error: OCR output for '{base_filename}' was not valid JSON.")
            print(f"   --- OCR Raw Output ---\n{result_text}\n   --------------------")
            raise

        transform_and_save_data(ocr_data, base_filename, scan_metadata, MASTER_CSV_FILE)
        print(f"   Success! Data for '{base_filename}' appended to CSV.")

        robust_move(png_path, completed_png_path)
        robust_move(json_path, completed_json_path)

        return scan_metadata

    except Exception as e:
        print(f"\n[ERROR] Failed to process {base_filename}: {e}")
        try:
            if os.path.exists(png_path):
                robust_move(png_path, failed_png_path)
            if os.path.exists(json_path):
                robust_move(json_path, failed_json_path)
            print(f"   Moved {base_filename} and metadata to {FAILED_DIR}")
        except Exception as move_e:
            print(f"   CRITICAL: Failed to move {base_filename} to 'failed' dir after error. Error: {move_e}")

        return None

# --- NEW: Stateful Watchdog Handler with Timeout ---
class ScreenshotEventHandler(FileSystemEventHandler):
    """
    Watches PENDING_DIR, manages scan state, and includes a timeout.
    """
    def __init__(self, extractor):
        self.extractor = extractor
        self.config_path = TRADE_CONFIG_FILE
        self.config_checksum = None
        self.expected_pairs = set()
        self.scan_progress = defaultdict(set)
        self.lock = threading.Lock()

        # --- Variables for Timeout ---
        self.last_file_time = time.time() # Track time of last processed file
        self.latest_scan_id_processed = -1 # Highest scan_id seen so far
        self.last_signaled_scan_id = -1 # Highest scan_id we wrote a signal for
        # --- End Timeout Variables ---

        self.load_config()
        print("Event handler initialized (Stateful Mode with Timeout).")
        if not self.expected_pairs:
            print(f"[WARN] No trade pairs loaded from config. Check {self.config_path}.")
        else:
            print(f"Monitoring for {len(self.expected_pairs)} unique market pairs.")


    def load_config(self):
        """Checks if the trade config has changed and reloads if necessary."""
        try:
            mtime = os.path.getmtime(self.config_path)
            if mtime != self.config_checksum:
                print(f"[CONFIG] {self.config_path} has changed. Reloading...")
                with open(self.config_path, 'r') as f:
                    config = json.load(f)

                self.expected_pairs = self.build_expected_pairs(config)
                self.config_checksum = mtime
                # Keep scan_progress, config change might add/remove pairs for *future* scans
                # self.scan_progress.clear()
                print(f"[CONFIG] Now monitoring {len(self.expected_pairs)} pairs.")

        except FileNotFoundError:
            if self.expected_pairs:
                print(f"[ERROR] Could not find {self.config_path}. Using old config.")
        except Exception as e:
            print(f"[ERROR] Failed to reload {self.config_path}: {e}")

    def build_expected_pairs(self, config):
        """Builds the 'checklist' of pairs from the config."""
        pairs = set()
        try:
            for session in config['trade_sessions']:
                base = session['base_currency']
                for target in session['target_currencies']:
                    pair_key = tuple(sorted((base, target)))
                    pairs.add(pair_key)
            return pairs
        except Exception as e:
            print(f"[ERROR] Failed to parse trade_config: {e}")
            return set()

    def on_created(self, event):
        """Handles new file events."""
        if event.is_directory or not event.src_path.lower().endswith('.png'):
            return

        with self.lock:
            if not os.path.exists(event.src_path):
                return

            print(f"\n[WATCHDOG] New file detected: {os.path.basename(event.src_path)}")
            self.load_config()
            processed_metadata = process_screenshot_job(event.src_path, self.extractor)

            if processed_metadata:
                try:
                    scan_id = int(processed_metadata['scan_id'])
                    # --- Update latest scan and time ---
                    self.last_file_time = time.time()
                    self.latest_scan_id_processed = max(self.latest_scan_id_processed, scan_id)
                    # --- End Update ---

                    have = processed_metadata['currency_have']
                    want = processed_metadata['currency_want']
                    pair_key = tuple(sorted((have, want)))

                    if pair_key not in self.expected_pairs:
                        print(f"   [INFO] Processed pair ({have}, {want}) not in trade_config. Ignoring.")
                        return

                    self.scan_progress[scan_id].add(pair_key)
                    print(f"   [STATE] Scan {scan_id} progress: {len(self.scan_progress[scan_id])}/{len(self.expected_pairs)} pairs.")

                    self.check_if_scan_is_complete(scan_id)

                except (KeyError, ValueError, TypeError) as e:
                    print(f"   [ERROR] Invalid metadata for {os.path.basename(event.src_path)}: {e}")

    def check_if_scan_is_complete(self, scan_id):
        """Checks if the scan has all expected pairs."""
        if not self.expected_pairs:
            print("   [WARN] Cannot check scan completeness: no expected pairs loaded.")
            return

        current_pairs_for_scan = self.scan_progress.get(scan_id, set()) # Use get for safety

        if self.expected_pairs.issubset(current_pairs_for_scan):
            print(f"[SUCCESS] Scan {scan_id} is now complete! All {len(self.expected_pairs)} pairs processed.")
            # --- Check if we already signaled this one due to timeout ---
            if scan_id > self.last_signaled_scan_id:
                self.write_complete_signal(scan_id)
            else:
                 print(f"   [INFO] Scan {scan_id} already signaled due to timeout. No new signal sent.")

            # Clean up progress tracker (now safe to do outside lock, but keep here for atomicity)
            scans_to_delete = [s for s in self.scan_progress if s <= scan_id]
            for s in scans_to_delete:
                if s in self.scan_progress: # Check again
                    del self.scan_progress[s]
            print(f"   [STATE] Cleaned up progress for scan {scan_id} and older scans.")


    def write_complete_signal(self, scan_id):
        """Writes the 'go' signal file and updates state."""
        signal_data = {'latest_complete_scan': scan_id}
        try:
            with open(OCR_COMPLETE_FILE, 'w') as f:
                json.dump(signal_data, f, indent=4)
            print(f"   [SIGNAL] Wrote {OCR_COMPLETE_FILE} for scan {scan_id}.")
            # --- Remember we signaled for this ID ---
            self.last_signaled_scan_id = scan_id
        except Exception as e:
            print(f"   [CRITICAL] Failed to write {OCR_COMPLETE_FILE}: {e}")

    # --- NEW: Timeout Check Method ---
    def check_timeout(self, timeout_seconds=25):
        """
        Checks for timeout and signals completion for the latest *partially*
        processed scan if necessary.
        """
        time_since_last_file = time.time() - self.last_file_time
        current_max_scan = self.latest_scan_id_processed

        # Trigger if timeout exceeded AND we have processed *some* scan
        # AND we haven't already signaled completion for this specific scan or a newer one.
        if time_since_last_file > timeout_seconds and \
           current_max_scan > -1 and \
           current_max_scan > self.last_signaled_scan_id:

            print(f"[TIMEOUT] No new files for {timeout_seconds:.1f}s. Signaling completion for latest processed scan: {current_max_scan}.")

            # Write the signal file (this updates self.last_signaled_scan_id)
            self.write_complete_signal(current_max_scan)

            # Clean up scan progress for the signaled scan and older ones
            # Needs lock to modify scan_progress safely if watchdog thread might access it
            with self.lock:
                scans_to_delete = [s for s in self.scan_progress if s <= current_max_scan]
                cleaned_count = 0
                for s in scans_to_delete:
                    if s in self.scan_progress: # Check again inside lock
                        del self.scan_progress[s]
                        cleaned_count +=1
                if cleaned_count > 0:
                     print(f"   [STATE] Cleaned up progress (due to timeout) for scan {current_max_scan} and {cleaned_count -1} older scans.")

            # Reset timer *after* signaling to prevent spamming signals until a new file arrives.
            self.last_file_time = time.time()


# --- Main execution ---
if __name__ == "__main__":
    """Main execution with timeout check."""
    print(f"--- Starting OCR Watchdog Service (Stateful Mode w/ Timeout, v5) ---")

    for dir_path in [PENDING_DIR, COMPLETED_DIR, FAILED_DIR]:
        os.makedirs(dir_path, exist_ok=True)

    if not os.path.exists(TRADE_CONFIG_FILE):
        print(f"[FATAL] {TRADE_CONFIG_FILE} not found!")
        exit(1)

    print(f"Monitoring:    {PENDING_DIR}")
    print(f"Master CSV:    {MASTER_CSV_FILE}")
    print(f"Config File:   {TRADE_CONFIG_FILE}")
    print(f"Signal File:   {OCR_COMPLETE_FILE}")

    local_extractor = setup_local_extractor()
    if not local_extractor:
        print("[FATAL] Could not initialize DocumentExtractor. Aborting.")
        exit(1)

    event_handler = ScreenshotEventHandler(local_extractor)

    observer = Observer()
    observer.schedule(event_handler, PENDING_DIR, recursive=False)
    observer.start()

    print(f"\n{'='*40}\n--- SERVICE RUNNING (Stateful Mode w/ Timeout) ---")
    print(f"--- Press CTRL+C to stop. ---\n{'='*40}")

    try:
        # --- MODIFIED LOOP ---
        while True:
            # Check for timeout every second
            event_handler.check_timeout(timeout_seconds=25)
            time.sleep(1)
        # --- END MODIFIED LOOP ---
    except KeyboardInterrupt:
        print("\n--- Shutdown signal received. Waiting for observer to stop... ---")
        observer.stop()

    observer.join()
    print("--- Observer stopped. Service shut down. ---")
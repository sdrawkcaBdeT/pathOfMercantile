import os
import csv
import hashlib
import json
from datetime import datetime
from docstrange import DocumentExtractor

def setup_local_extractor():
    """
    Initializes the DocumentExtractor with all recommended settings for local GPU processing.
    """
    print("Initializing the document extractor in local GPU mode...")
    try:
        # Initialize with all the settings you requested:
        # - gpu=True: Forces 100% local processing on your GPU.
        # - preserve_layout=True: Helps the model understand the structure of the text on screen.
        # - ocr_enabled=True: Ensures the OCR engine is active for image files.
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
    """
    Parses a ratio string (e.g., '1 : 17.60' or '65 : 1') and calculates
    the value based on the want:have format. This is the corrected logic based
    on your original, battle-tested function.
    """
    if not ratio_str: return 0.0
    try:
        # The ratio in the game UI is displayed as "want : have"
        # The calculation 'want / have' gives us the value of 1 'have' unit in terms of 'want' units.

        # 1. Clean the string: remove comparison operators, spaces, and commas.
        clean_text = ratio_str.strip().replace('<', '').replace('>', '').replace(' ', '').replace(',', '')
        
        # 2. Split into 'want' and 'have' parts.
        parts = clean_text.split(':')
        
        # 3. Convert to float and calculate.
        want_val = float(parts[0])
        have_val = float(parts[1]) if len(parts) > 1 else 1.0

        if have_val == 0:
            return 0.0
        
        return want_val / have_val

    except (ValueError, IndexError, AttributeError) as e:
        print(f"   Warning: Could not parse ratio '{ratio_str}'. Error: {e}. Defaulting to 0.0")
        return 0.0

def transform_and_save_data(ocr_data, screenshot_filename, scan_metadata, output_csv_path):
    """
    Transforms the structured OCR data into final CSV rows and appends to the CSV file.
    This function now uses metadata from the associated JSON file.
    """
    # Extract metadata from the loaded JSON data
    scan_id = scan_metadata.get("scan_id", 0)
    lot_id = scan_metadata.get("lot_id", os.path.splitext(screenshot_filename)[0])
    timestamp_utc = scan_metadata.get("timestamp_utc", datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
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

    file_exists = os.path.isfile(output_csv_path)
    
    try:
        with open(output_csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists or os.path.getsize(output_csv_path) == 0:
                writer.writerow([
                    "scan_id", "lot_id", "timestamp_utc", "currency_want",
                    "currency_have", "trade_type", "row_num", "ratio", "stock"
                ])
            writer.writerows(rows_to_write)
    except IOError as e:
        print(f"   Error: Could not write to '{output_csv_path}': {e}")


def process_all_pngs_in_folder(extractor, input_folder, output_csv_path):
    """
    Processes all .png files, finds their matching .json metadata, performs OCR,
    transforms the data, and appends it to a master CSV file.
    """
    if not os.path.isdir(input_folder):
        print(f"Error: The input folder '{input_folder}' was not found.")
        return

    all_files = os.listdir(input_folder)
    png_files = [f for f in all_files if f.lower().endswith('.png')]
    json_files = {os.path.splitext(f)[0]: f for f in all_files if f.lower().endswith('.json')}


    if not png_files:
        print(f"No .png files were found in '{input_folder}'.")
        return

    print(f"Found {len(png_files)} PNG files to process...")
    
    processed_hashes = {}

    for i, filename in enumerate(png_files):
        print(f"\n({i+1}/{len(png_files)}) Analyzing '{filename}'...")
        
        # --- Find matching JSON metadata file ---
        base_filename = os.path.splitext(filename)[0]
        if base_filename not in json_files:
            print(f"   Warning: No matching .json file found for '{filename}'. Skipping.")
            continue
        
        json_path = os.path.join(input_folder, json_files[base_filename])
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                scan_metadata = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"   Error: Could not read or parse metadata from '{json_files[base_filename]}': {e}. Skipping.")
            continue

        input_image_path = os.path.join(input_folder, filename)

        # --- Duplicate Detection ---
        try:
            with open(input_image_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            print(f"   Could not read file to calculate hash: {e}")
            continue

        if file_hash in processed_hashes:
            print(f"   Duplicate image detected. Using cached OCR data.")
            ocr_data = processed_hashes[file_hash]
            transform_and_save_data(ocr_data, filename, scan_metadata, output_csv_path)
            continue

        # --- Process Unique Image ---
        print(f"   Unique image detected. Processing with OCR...")
        try:
            result_text = extractor.extract(input_image_path).extract_text().strip()
            
            if result_text:
                try:
                    ocr_data = json.loads(result_text)
                    processed_hashes[file_hash] = ocr_data # Cache the successful result
                    transform_and_save_data(ocr_data, filename, scan_metadata, output_csv_path)
                    print(f"   Success! Data for '{filename}' appended to CSV.")

                except json.JSONDecodeError:
                    print(f"   Error: OCR output for '{filename}' was not valid JSON. Skipping.")
                    print(f"   --- OCR Raw Output ---\n{result_text}\n   --------------------")
            else:
                print(f"   Info: No text found in '{filename}'.")
        
        except Exception as e:
            print(f"   An error occurred during extraction for '{filename}': {e}")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    
    local_extractor = setup_local_extractor()
    
    if local_extractor:
        
        screenshots_folder = "screenshots/pending"
        master_csv_file = "market_data.csv"
        
        process_all_pngs_in_folder(local_extractor, screenshots_folder, master_csv_file)
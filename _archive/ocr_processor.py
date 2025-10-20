import os
import json
import pandas as pd
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys
import multiprocessing
from PIL import Image
import cv2
import numpy as np
import glob

# --- Configuration ---
OCR_CONFIG_FILE = 'ocr_config.json'
SCREENSHOTS_DIR = 'screenshots'
PROCESSED_DIR = os.path.join(SCREENSHOTS_DIR, 'processed')
OUTPUT_CSV = 'market_data.csv'
TEMPLATE_DIR = 'templates/numbers'
CONFIDENCE_THRESHOLD = 0.70

# --- Configuration for saving cropped debug images ---
DEBUG_SAVE_CROPPED_IMAGES = True
DEBUG_DIR = 'cropped_debug'

# --- HELPER FUNCTIONS ---

def parse_ratio(text: str) -> float | None:
    if not text: return None
    try:
        clean_text = text.strip().replace('<', '').replace('>', '').replace(' ', '')
        parts = clean_text.split(':')
        value = float(parts[0].replace(',', ''))
        base = float(parts[1].replace(',', '')) if len(parts) > 1 else 1.0
        return value / base if base != 0 else None
    except (ValueError, IndexError, AttributeError):
        return None

def parse_stock(text: str) -> int | None:
    if not text: return None
    try:
        return int(text.strip().replace(',', ''))
    except (ValueError, AttributeError):
        return None

# --- CUSTOM GLYPH RECOGNITION CORE LOGIC ---

def load_templates(template_dir: str):
    """Loads all character templates from the specified directory."""
    templates = {'ratio': {}, 'stock': {}}
    template_files = glob.glob(os.path.join(template_dir, 'template_*.png'))

    for f in template_files:
        filename = os.path.basename(f)
        parts = filename.replace('template_', '').replace('.png', '').split('_')

        category = parts[0] # 'ratio' or 'stock'
        char_name = parts[1]

        char_map = {
            'colon': ':', 'comma': ',', 'decimal': '.', '0': '0', '1': '1',
            '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7',
            '8': '8', '9': '9'
        }

        character = char_map.get(char_name)
        if character and category in templates:
            template_img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
            if template_img is not None:
                templates[category][character] = template_img
            else:
                print(f"[WARN] Could not load template image: {filename}")

    print(f"Loaded {len(templates['ratio'])} ratio templates and {len(templates['stock'])} stock templates.")
    return templates

def recognize_text_from_templates(cell_image_cv, template_set):
    """
    Finds and reconstructs text in a cell image using template matching.
    """
    cell_gray = cv2.cvtColor(cell_image_cv, cv2.COLOR_BGR2GRAY)

    found_chars = []

    for char, template_img in template_set.items():
        w, h = template_img.shape[::-1]
        # Perform template matching
        res = cv2.matchTemplate(cell_gray, template_img, cv2.TM_CCOEFF_NORMED)
        # Find all locations where the match is above the threshold
        loc = np.where(res >= CONFIDENCE_THRESHOLD)
        for pt in zip(*loc[::-1]): # Switch columns and rows
            found_chars.append({'char': char, 'x': pt[0]})

    if not found_chars:
        return ""

    # Sort found characters by their x-coordinate
    found_chars.sort(key=lambda item: item['x'])

    # Deduplicate characters that are too close together)
    deduped_string = ""
    last_x = -999
    for item in found_chars:
        if item['x'] > last_x + 2:
            deduped_string += item['char']
            last_x = item['x']

    return deduped_string



# --- CORE WORKER FUNCTION ---

def process_single_screenshot(screenshot_path: str, ocr_config: dict, templates: dict):
    metadata_path = os.path.splitext(screenshot_path)[0] + '.json'
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
    except FileNotFoundError:
        return [], None, None

    print(f"  [INFO] Processing: {os.path.basename(screenshot_path)}")
    image = cv2.imread(screenshot_path)

    extracted_rows = []

    for table_name, table_config in ocr_config.items():
        if table_name in ["tesseract_options", "columns"]:
            continue

        for i, row_coords in enumerate(table_config['rows']):
            y1, y2 = row_coords['y_start'], row_coords['y_end']

            # --- Ratio Processing ---
            ratio_col = ocr_config['columns']['ratio']
            rx1, rx2 = ratio_col['x_start'], ratio_col['x_end']
            ratio_crop_cv = image[y1:y2, rx1:rx2]

            # --- Stock Processing ---
            stock_col = ocr_config['columns']['stock']
            sx1, sx2 = stock_col['x_start'], stock_col['x_end']
            stock_crop_cv = image[y1:y2, sx1:sx2]
            
            # --- Save cropped images if debug mode is on ---
            if DEBUG_SAVE_CROPPED_IMAGES:
                # Convert from OpenCV format back to Pillow for saving
                ratio_img_pil = Image.fromarray(cv2.cvtColor(ratio_crop_cv, cv2.COLOR_BGR2RGB))
                stock_img_pil = Image.fromarray(cv2.cvtColor(stock_crop_cv, cv2.COLOR_BGR2RGB))
                
                lot_id = metadata.get("lot_id", "unknown_lot")
                ratio_filename = f"{lot_id}_{table_name}_row{i+1}_ratio.png"
                stock_filename = f"{lot_id}_{table_name}_row{i+1}_stock.png"
                ratio_img_pil.save(os.path.join(DEBUG_DIR, ratio_filename))
                stock_img_pil.save(os.path.join(DEBUG_DIR, stock_filename))
            # ---------------------------------------------------------
            
            ratio_text = recognize_text_from_templates(ratio_crop_cv, templates['ratio'])
            stock_text = recognize_text_from_templates(stock_crop_cv, templates['stock'])

            ratio = parse_ratio(ratio_text)
            stock = parse_stock(stock_text)

            if ratio is not None or stock is not None:
                extracted_rows.append({
                    "scan_id": metadata.get("scan_id"), "lot_id": metadata.get("lot_id"),
                    "timestamp_utc": metadata.get("timestamp_utc"), "currency_want": metadata.get("currency_want"),
                    "currency_have": metadata.get("currency_have"), "trade_type": table_name,
                    "row_num": i + 1, "ratio": ratio, "stock": stock
                })

    return extracted_rows, screenshot_path, metadata_path

# --- MAIN ORCHESTRATOR ---

def main():
    print("--- Starting Template Matching Processing ---")
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    # --- Create debug directory if needed ---
    if DEBUG_SAVE_CROPPED_IMAGES:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        print(f"DEBUG mode is ON. Cropped images will be saved to '{DEBUG_DIR}'")

    try:
        with open(OCR_CONFIG_FILE, 'r') as f:
            ocr_config = json.load(f)
    except FileNotFoundError:
        print(f"[FATAL] OCR configuration file '{OCR_CONFIG_FILE}' not found. Aborting.")
        sys.exit(1)

    templates = load_templates(TEMPLATE_DIR)
    if not templates['ratio'] or not templates['stock']:
        print("[FATAL] No templates were loaded. Check the 'templates/numbers' directory. Aborting.")
        sys.exit(1)

    unprocessed_screenshots = [os.path.join(SCREENSHOTS_DIR, f) for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]

    if not unprocessed_screenshots:
        print("No new screenshots found to process.")
        return

    print(f"Found {len(unprocessed_screenshots)} screenshots to process.")

    all_processed_data = []
    files_to_move = []

    num_cores = multiprocessing.cpu_count()
    num_workers = max(1, num_cores - 2)
    print(f"Using {num_workers} worker processes (out of {num_cores} available cores).")

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_single_screenshot, path, ocr_config, templates): path for path in unprocessed_screenshots}

        for future in as_completed(futures):
            try:
                extracted_rows, screenshot_path, metadata_path = future.result()
                if extracted_rows:
                    all_processed_data.extend(extracted_rows)
                    files_to_move.append(screenshot_path)
                    files_to_move.append(metadata_path)
            except Exception as e:
                print(f"[ERROR] An unexpected error occurred while processing {futures[future]}: {e}")

    if not all_processed_data:
        print("Processing complete, but no data was successfully extracted.")
        return

    df = pd.DataFrame(all_processed_data)

    if os.path.exists(OUTPUT_CSV):
        df.to_csv(OUTPUT_CSV, mode='a', header=False, index=False)
        print(f"Appended {len(df)} new rows to '{OUTPUT_CSV}'")
    else:
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"Created '{OUTPUT_CSV}' with {len(df)} rows.")

    try:
        print("\n--- Sorting master CSV file ---")
        master_df = pd.read_csv(OUTPUT_CSV)
        master_df['timestamp_utc'] = pd.to_datetime(master_df['timestamp_utc'], errors='coerce')
        sort_order = ['scan_id', 'timestamp_utc', 'trade_type', 'row_num']
        master_df = master_df.sort_values(by=sort_order, ascending=True)
        master_df['timestamp_utc'] = master_df['timestamp_utc'].dt.strftime('%Y-%m-%d %H:%M:%S')
        master_df.to_csv(OUTPUT_CSV, index=False)
        print(f"Successfully sorted '{OUTPUT_CSV}'.")
    except Exception as e:
        print(f"[ERROR] Could not sort the master CSV file. Reason: {e}")

    for path in files_to_move:
        try:
            shutil.move(path, os.path.join(PROCESSED_DIR, os.path.basename(path)))
        except (FileNotFoundError, Exception) as e:
            print(f"[WARN] Could not move file {os.path.basename(path)}: {e}")

    print(f"Successfully processed and moved {len(files_to_move) // 2} pairs of files.")
    print("\n--- OCR Processing Finished ---")

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    main()
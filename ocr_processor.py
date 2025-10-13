import os
import json
import pytesseract
import pandas as pd
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys
import multiprocessing
from PIL import Image, ImageEnhance
import cv2
import numpy as np

# --- Configuration ---
OCR_CONFIG_FILE = 'ocr_config.json'
SCREENSHOTS_DIR = 'screenshots'
PROCESSED_DIR = os.path.join(SCREENSHOTS_DIR, 'processed')
OUTPUT_CSV = 'market_data.csv'
DEBUG_SAVE_CROPPED_IMAGES = True
DEBUG_DIR = 'cropped_debug'
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(pil_image: Image.Image) -> Image.Image:
    """
    This function now acts as a passthrough, returning the original
    cropped image without any pre-processing to test baseline OCR accuracy.
    """
    return pil_image


# # Is this better? making it bigger? compare? Does the bigger image give better results on different rows? Can we use both approaches somehow? No preprocessing is pretyt good - this could be an alternative path.
# def preprocess_image(pil_image: Image.Image) -> Image.Image:
#     """
#     This function now only resizes the image, making it larger to improve
#     Tesseract's accuracy on small, stylized text. No other filtering is applied.
#     """
#     # 1. Convert Pillow image to OpenCV format to use its superior resizing
#     image_cv = np.array(pil_image.convert('RGB'))
    
#     # 2. Resize the image to be 3x larger using a high-quality interpolation method
#     width = int(image_cv.shape[1] * 3)
#     height = int(image_cv.shape[0] * 3)
#     resized_image = cv2.resize(image_cv, (width, height), interpolation=cv2.INTER_CUBIC)

#     # 3. Convert back to Pillow image format for Tesseract
#     return Image.fromarray(resized_image)

def parse_ratio(text: str) -> float | None:
    """Safely parses a ratio string into a float."""
    if not text: return None
    try:
        parts = text.strip().split(':')
        value = float(parts[0].replace(',', ''))
        base = float(parts[1].replace(',', '')) if len(parts) > 1 else 1.0
        return value / base if base != 0 else None
    except (ValueError, IndexError, AttributeError):
        return None

def parse_stock(text: str) -> int | None:
    """Safely parses a stock string into an integer."""
    if not text: return None
    try:
        return int(text.strip().replace(',', ''))
    except (ValueError, AttributeError):
        return None

# --- CORE WORKER FUNCTION ---

def process_single_screenshot(screenshot_path: str, ocr_config: dict):
    """Processes one screenshot file, extracting data based on the OCR config."""
    metadata_path = os.path.splitext(screenshot_path)[0] + '.json'
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
    except FileNotFoundError:
        return [], None, None

    print(f"  [INFO] Processing: {os.path.basename(screenshot_path)}")
    image = Image.open(screenshot_path)
    
    tesseract_config = f"--psm {ocr_config['tesseract_options']['psm']} -c tessedit_char_whitelist='{ocr_config['tesseract_options']['char_whitelist']}'"
    
    extracted_rows = []
    
    for table_name, table_config in ocr_config.items():
        if table_name in ["tesseract_options", "columns"]:
            continue

        for i, row_coords in enumerate(table_config['rows']):
            y1, y2 = row_coords['y_start'], row_coords['y_end']
            
            # Crop ratio and stock from the original image
            ratio_col = ocr_config['columns']['ratio']
            rx1, rx2 = ratio_col['x_start'], ratio_col['x_end']
            ratio_crop = image.crop((rx1, y1, rx2, y2))
            
            stock_col = ocr_config['columns']['stock']
            sx1, sx2 = stock_col['x_start'], stock_col['x_end']
            stock_crop = image.crop((sx1, y1, sx2, y2))

            # --- MODIFICATION: Pre-process first ---
            preprocessed_ratio = preprocess_image(ratio_crop)
            preprocessed_stock = preprocess_image(stock_crop)

            # --- Save the POST-processed images ---
            if DEBUG_SAVE_CROPPED_IMAGES:
                lot_id = metadata.get("lot_id", "unknown_lot")
                ratio_filename = f"{lot_id}_{table_name}_row{i+1}_ratio.png"
                stock_filename = f"{lot_id}_{table_name}_row{i+1}_stock.png"
                # Save the black-and-white versions
                preprocessed_ratio.save(os.path.join(DEBUG_DIR, ratio_filename))
                preprocessed_stock.save(os.path.join(DEBUG_DIR, stock_filename))
            # ---------------------------------------------------------

            # Run OCR on the pre-processed images
            ratio_text = pytesseract.image_to_string(preprocessed_ratio, config=tesseract_config)
            stock_text = pytesseract.image_to_string(preprocessed_stock, config=tesseract_config)

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
    print("--- Starting OCR Processing (Parallel Mode) ---")
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    if DEBUG_SAVE_CROPPED_IMAGES:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        print(f"DEBUG mode is ON. Cropped images will be saved to '{DEBUG_DIR}'")

    try:
        with open(OCR_CONFIG_FILE, 'r') as f:
            ocr_config = json.load(f)
    except FileNotFoundError:
        print(f"[FATAL] OCR configuration file '{OCR_CONFIG_FILE}' not found. Aborting.")
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
        futures = {executor.submit(process_single_screenshot, path, ocr_config): path for path in unprocessed_screenshots}
        
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
        # Convert timestamp to datetime for correct sorting, handling potential errors
        master_df['timestamp_utc'] = pd.to_datetime(master_df['timestamp_utc'], errors='coerce')
        
        sort_order = ['scan_id', 'timestamp_utc', 'trade_type', 'row_num']
        master_df = master_df.sort_values(by=sort_order, ascending=True)
        
        # Convert timestamp back to string format for saving
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
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    from multiprocessing import freeze_support
    freeze_support()
    main()
import cv2
import pyautogui
import numpy as np
from PIL import Image, ImageEnhance
import pytesseract
import pandas as pd
import re
from datetime import datetime
import os
import json # Import the json library
import gui_navigator
from datetime import datetime, timezone

# --- Load Configuration ---
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    SCRAPE_CONFIG = config['scraping']
    pytesseract.pytesseract.tesseract_cmd = config['tesseract_path']
except FileNotFoundError:
    print("Error: config.json not found. Please create it.")
    exit()

# ... (rest of the functions: find_template_on_screen, crop_region, etc. remain the same) ...

def find_template_on_screen(template_paths, threshold=0.8):
    """
    Searches the screen for a list of template images and returns the location
    and the path of the first one found.
    """
    screenshot = pyautogui.screenshot()
    screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    for template_path in template_paths:
        if os.path.exists(template_path):
            template = cv2.imread(template_path)
            result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= threshold:
                print(f"Found template '{template_path}' with confidence {max_val:.2f}")
                return max_loc, screenshot
    return None, None

def crop_region(screenshot, template_loc, relative_coords):
    """Crops a single region based on relative coordinates."""
    top_left_x, top_left_y = template_loc
    
    left = top_left_x + relative_coords[0]
    top = top_left_y + relative_coords[1]
    right = top_left_x + relative_coords[2]
    bottom = top_left_y + relative_coords[3]
    
    return screenshot.crop((left, top, right, bottom))

def preprocess_and_ocr(image, mode='numeric'):
    """Preprocesses an image and uses Tesseract to extract text."""
    # ... (image preprocessing steps remain the same) ...
    image = image.convert('L')
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.5)
    image = image.point(lambda p: p > 120 and 255)
    image = image.resize([2 * s for s in image.size], Image.Resampling.LANCZOS)
    
    if mode == 'numeric':
        # UPDATED: Whitelist now includes numbers, colon, period, AND comma
        config = '--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789:.,'
    else: # 'text' mode
        config = '--psm 7 --oem 3'
        
    text = pytesseract.image_to_string(image, config=config).strip()
    return text

def clean_and_structure_data(ratio_text, stock_text, timestamp, currency_i_want, currency_i_have):
    """
    Cleans the OCR text and structures it into a dictionary.
    Handles commas, decimals, and ratio parsing.
    """
    price = None
    stock = None

    # --- Clean and Calculate Ratio ---
    try:
        # First, remove any commas OCR might have picked up
        cleaned_ratio_text = ratio_text.replace(',', '')
        
        match = re.search(r'([\d\.]+):([\d\.]+)', cleaned_ratio_text)
        if match:
            val_have = float(match.group(1))
            val_want = float(match.group(2))
            if val_want > 0:
                price = val_have / val_want
        else:
             price_match = re.search(r'[\d\.]+', cleaned_ratio_text)
             if price_match:
                 price = float(price_match.group(0))
    except (ValueError, ZeroDivisionError, AttributeError):
        price = None

    # --- Clean Stock ---
    try:
        # UPDATED: Remove commas first, then find the number.
        # This correctly handles "1,000" and "10.50".
        cleaned_stock_text = stock_text.replace(',', '')
        stock_match = re.search(r'[\d\.]+', cleaned_stock_text)
        if stock_match:
            # We assume stock is an integer, so we convert to float first, then int.
            # This correctly handles cases like "25.0"
            stock = int(float(stock_match.group(0)))
    except (ValueError, AttributeError):
        stock = None
        
    return {
        "timestamp": timestamp,
        "currency_i_want": currency_i_want,
        "currency_i_have": currency_i_have,
        "price": price,
        "stock": stock
    }
# --- Main Execution ---
def main():
    # 1. GUI Navigation (if needed)
    # gui_navigator.select_trading_pair("Silver", "Gold")

    # 2. Load coordinates and paths from the config object
    template_paths = SCRAPE_CONFIG['template_paths']
    currency_coords = SCRAPE_CONFIG['currency_coords']
    # The list of dicts for rows is loaded directly
    row_relative_coords = SCRAPE_CONFIG['row_relative_coords']

    # 3. Find a valid template anchor on the screen
    template_loc, screenshot = find_template_on_screen(template_paths)
    
    if not template_loc:
        print("No valid template found on screen. Exiting.")
        return
        
    # ... The rest of the main function continues exactly as before ...
    print(f"Template found at: {template_loc}")
    all_data = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 4. OCR the currency names dynamically
    currency_i_want_img = crop_region(screenshot, template_loc, currency_coords["want"])
    currency_i_have_img = crop_region(screenshot, template_loc, currency_coords["have"])
    
    currency_i_want = preprocess_and_ocr(currency_i_want_img, mode='text')
    currency_i_have = preprocess_and_ocr(currency_i_have_img, mode='text')
    
    print(f"Detected Trading Pair -> Want: '{currency_i_want}', Have: '{currency_i_have}'")
    
    # 5. Loop through each row to extract Ratio and Stock data
    for i, row_coords in enumerate(row_relative_coords):
        # We access the dicts from the list loaded from JSON
        ratio_img = crop_region(screenshot, template_loc, row_coords["ratio"])
        stock_img = crop_region(screenshot, template_loc, row_coords["stock"])
        
        ratio_text = preprocess_and_ocr(ratio_img, mode='numeric')
        stock_text = preprocess_and_ocr(stock_img, mode='numeric')
        
        print(f"Row {i+1}: Raw Ratio OCR: '{ratio_text}', Raw Stock OCR: '{stock_text}'")

        if not ratio_text and not stock_text:
            print(f"Row {i+1}: Skipping empty row.")
            continue

        data = clean_and_structure_data(ratio_text, stock_text, timestamp, currency_i_want, currency_i_have)
        all_data.append(data)

    if not all_data:
        print("No data was scraped. Check OCR results and coordinates.")
        return
        
    # 6. Create a DataFrame and save to CSV
    df = pd.DataFrame(all_data)
    print("\n--- Scraped Data ---")
    print(df)
    
    output_path = "market_data.csv"
    df.to_csv(output_path, mode='a', header=not os.path.exists(output_path), index=False)
    print(f"\nData appended to {output_path}")

if __name__ == "__main__":
    main()
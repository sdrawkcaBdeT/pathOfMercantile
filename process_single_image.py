import os
import csv
import hashlib
import shutil
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

def process_all_pngs_in_folder(extractor, input_folder, output_folder):
    """
    Processes all .png files in an input folder. It detects duplicate images
    to avoid re-processing and saves the extracted text into .txt files.
    """
    # --- 1. Setup Input and Output Directories ---
    if not os.path.isdir(input_folder):
        print(f"Error: The input folder '{input_folder}' was not found.")
        return

    os.makedirs(output_folder, exist_ok=True)
    print(f"Output will be saved to: '{output_folder}'")

    # --- 2. Find all PNG files to process ---
    png_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.png')]

    if not png_files:
        print(f"No .png files were found in '{input_folder}'.")
        return

    print(f"Found {len(png_files)} PNG files to process...")
    
    # Dictionary to track processed image hashes and their output files
    processed_hashes = {}

    # --- 3. Loop Through and Process Each File ---
    for i, filename in enumerate(png_files):
        input_image_path = os.path.join(input_folder, filename)
        print(f"\n({i+1}/{len(png_files)}) Analyzing '{filename}'...")

        # --- Duplicate Detection ---
        try:
            with open(input_image_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            print(f"   Could not read file to calculate hash: {e}")
            continue

        if file_hash in processed_hashes:
            original_output_path = processed_hashes[file_hash]
            new_output_path = os.path.join(output_folder, os.path.basename(original_output_path))
            
            try:
                # We just need to create the new filename with the .txt extension
                new_filename_base = os.path.splitext(filename)[0]
                new_output_filename = new_filename_base + ".txt"
                new_output_path = os.path.join(output_folder, new_output_filename)

                shutil.copy2(original_output_path, new_output_path)
                print(f"   Duplicate of '{os.path.basename(original_output_path)}' found. Copied result to '{new_output_path}'")
            except Exception as e:
                print(f"   Error copying duplicate result for '{filename}': {e}")
            continue # Skip to the next file

        # --- Process Unique Image ---
        print(f"   Unique image detected. Processing with OCR...")
        try:
            result = extractor.extract(input_image_path)
            
            # Use .extract_text() for direct text output
            extracted_text = result.extract_text().strip()
            
            if extracted_text:
                text_filename = os.path.splitext(filename)[0] + '.txt'
                output_path = os.path.join(output_folder, text_filename)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(extracted_text)
                print(f"   Success! Saved text output to '{output_path}'")
                # Store the hash and the path to the file we just created
                processed_hashes[file_hash] = output_path
            else:
                print(f"   Info: No text found in '{filename}'.")
        
        except Exception as e:
            print(f"   An error occurred during extraction for '{filename}': {e}")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    
    local_extractor = setup_local_extractor()
    
    if local_extractor:
        
        screenshots_folder = "screenshots/"
        output_directory = "data/raw/"
        
        process_all_pngs_in_folder(local_extractor, screenshots_folder, output_directory)
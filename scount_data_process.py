import os
import json
import csv
from datetime import datetime

def create_item_id_to_name_map(csv_path):
    """Reads the target_item_ids.csv file and creates a mapping from ItemID to Name."""
    id_to_name_map = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                item_id = int(row['itemID'])
                item_name = row['name']
                id_to_name_map[item_id] = item_name
        return id_to_name_map
    except FileNotFoundError:
        print(f"Error: The ID lookup file '{csv_path}' was not found.")
        return None
    except Exception as e:
        print(f"An error occurred reading '{csv_path}': {e}")
        return None

def process_pair_history_files(input_dir, output_csv, id_map):
    """
    Processes all JSON files in a directory and compiles them into a single CSV,
    including the names of the items.
    """
    if not os.path.isdir(input_dir):
        print(f"Error: Directory '{input_dir}' not found.")
        return

    all_history_rows = []
    json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]

    if not json_files:
        print(f"No .json files found in '{input_dir}'.")
        return

    print(f"Found {len(json_files)} JSON files to process...")

    for filename in json_files:
        file_path = os.path.join(input_dir, filename)
        print(f"Processing '{filename}'...")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            history = data.get("History", [])
            for record in history:
                epoch_time = record.get("Epoch")
                if epoch_time is None:
                    continue

                timestamp_utc = datetime.utcfromtimestamp(epoch_time).isoformat()
                c1_data = record.get("Data", {}).get("CurrencyOneData", {})
                c2_data = record.get("Data", {}).get("CurrencyTwoData", {})
                c1_item_id = c1_data.get("CurrencyItemId")
                c2_item_id = c2_data.get("CurrencyItemId")
                c1_name = id_map.get(c1_item_id, "Unknown")
                c2_name = id_map.get(c2_item_id, "Unknown")

                row = {
                    "timestamp_utc": timestamp_utc,
                    "c1_item_id": c1_item_id,
                    "c1_name": c1_name,
                    "c1_relative_price": c1_data.get("RelativePrice"),
                    "c1_volume_traded": c1_data.get("VolumeTraded"),
                    "c2_item_id": c2_item_id,
                    "c2_name": c2_name,
                    "c2_relative_price": c2_data.get("RelativePrice"),
                    "c2_volume_traded": c2_data.get("VolumeTraded"),
                }
                all_history_rows.append(row)

        except Exception as e:
            print(f"  An error occurred with '{filename}': {e}")

    if not all_history_rows:
        print("No valid history data was processed.")
        return

    try:
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            headers = [
                "timestamp_utc", "c1_item_id", "c1_name", "c1_relative_price", "c1_volume_traded",
                "c2_item_id", "c2_name", "c2_relative_price", "c2_volume_traded"
            ]
            # Corrected from DictReader to DictWriter
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(all_history_rows)
        
        print(f"\nSuccess! All data has been processed into '{output_csv}'")

    except IOError:
        print(f"Error: Could not write to the file '{output_csv}'.")


if __name__ == "__main__":
    # --- Configuration ---
    INPUT_DIRECTORY = "currencyPairHistory"
    OUTPUT_CSV_FILE = "scout_macro_data.csv"
    ITEM_ID_LOOKUP_FILE = "target_item_ids.csv"

    item_id_map = create_item_id_to_name_map(ITEM_ID_LOOKUP_FILE)

    if item_id_map:
        process_pair_history_files(INPUT_DIRECTORY, OUTPUT_CSV_FILE, item_id_map)
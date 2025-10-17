import os
import csv
import time
import json
import requests
from datetime import datetime

def get_target_items(id_lookup_file):
    """Reads the CSV file to get the list of target items."""
    target_items = []
    try:
        with open(id_lookup_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('is_target') == '1':
                    target_items.append({
                        "name": row['name'],
                        "id": int(row['itemID'])
                    })
        return target_items
    except FileNotFoundError:
        print(f"Error: The ID lookup file '{id_lookup_file}' was not found.")
        return []

def fetch_all_pair_histories(target_items, base_currencies, output_dir):
    """
    Loops through all currency pairs, intelligently queries the API,
    handles rate limits, and saves the JSON responses.
    """
    if not os.path.isdir(output_dir):
        print(f"Creating directory: '{output_dir}'")
        os.makedirs(output_dir)

    base_url = "https://poe2scout.com/api/currencyExchange/PairHistory"
    league_name = "Rise of the Abyssal"
    
    headers = {
        'accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    for base_currency in base_currencies:
        base_name = base_currency["name"]
        base_id = base_currency["id"]
        print(f"\n--- Starting queries against base currency: {base_name} ---")

        for target_item in target_items:
            target_name = target_item["name"]
            target_id = target_item["id"]

            if target_id == base_id:
                continue

            params = {
                'league': league_name,
                'currencyOneItemId': target_id,
                'currencyTwoItemId': base_id,
                'limit': 10000 
            }

            print(f"Fetching data for: {target_name} vs. {base_name}...")

            try:
                response = requests.get(base_url, params=params, headers=headers)

                # --- INTELLIGENT RATE LIMIT HANDLING ---
                if response.status_code == 429:
                    retry_after = int(response.headers.get('retry-after', 60))
                    print(f"  > Rate limited! Waiting for {retry_after} seconds...")
                    time.sleep(retry_after)
                    # Retry the request once after waiting
                    response = requests.get(base_url, params=params, headers=headers)
                
                response.raise_for_status()
                
                # --- Save the JSON Response ---
                safe_target_name = target_name.replace(" ", "_").replace("'", "")
                safe_base_name = base_name.replace(" ", "_").replace("'", "")
                file_name = f"{safe_target_name}_vs_{safe_base_name}.json"
                file_path = os.path.join(output_dir, file_name)

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(response.json(), f, indent=2)
                
                print(f"  > Success! Saved to {file_path}")

            except requests.exceptions.RequestException as e:
                print(f"  > FAILED to get data for {target_name} vs. {base_name}. Error: {e}")

            # --- Standard polite delay ---
            time.sleep(1)

if __name__ == "__main__":
    ID_LOOKUP_FILE = "target_item_ids.csv"
    OUTPUT_DIRECTORY = "currencyPairHistory"
    
    BASE_CURRENCIES = [
        {"name": "Exalted Orb", "id": 290},
        {"name": "Chaos Orb", "id": 287},
        {"name": "Divine Orb", "id": 291}
    ]

    target_items_list = get_target_items(ID_LOOKUP_FILE)

    if target_items_list:
        fetch_all_pair_histories(target_items_list, BASE_CURRENCIES, OUTPUT_DIRECTORY)
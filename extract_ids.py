import json
import csv

def create_target_item_csv(json_file_path, target_categories, priority_list, csv_output_path):
    """
    Loads item data, filters for multiple categories, adds an 'is_target' column,
    sorts by target status, and saves the result to a CSV file.

    Args:
        json_file_path (str): Path to the JSON file with item data.
        target_categories (list): A list of categoryApiIds to include.
        priority_list (list): A list of item names to mark as targets.
        csv_output_path (str): Path to save the output CSV file.
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            all_items = json.load(f)
    except FileNotFoundError:
        print(f"Error: The file '{json_file_path}' was not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: The file '{json_file_path}' is not a valid JSON file.")
        return

    filtered_items = []
    category_set = set(target_categories)
    priority_set = set(priority_list)

    for item in all_items:
        if item.get("categoryApiId") in category_set:
            item_name = item.get("text") or item.get("name")
            item_id = item.get("itemId")
            api_id = item.get("apiId", "N/A")
            category = item.get("categoryApiId")

            if item_name and item_id is not None:
                # Determine if the item is in the priority list
                is_target_flag = 1 if item_name in priority_set else 0
                
                filtered_items.append({
                    "is_target": is_target_flag,
                    "Name": item_name,
                    "ItemID": item_id,
                    "ApiID": api_id,
                    "Category": category
                })

    if not filtered_items:
        print("No items were found matching the specified categories.")
        return
        
    # Sort the list: 'is_target' items (1) come first, then sort alphabetically by name.
    filtered_items.sort(key=lambda x: (-x["is_target"], x["Name"]))

    # Write the sorted data to the CSV file
    try:
        with open(csv_output_path, 'w', newline='', encoding='utf-8') as output_file:
            # Add 'is_target' as the first column header
            headers = ["is_target", "Name", "ItemID", "ApiID", "Category"]
            writer = csv.DictWriter(output_file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(filtered_items)
        print(f"Successfully created CSV with 'is_target' column: '{csv_output_path}'")
    except IOError:
        print(f"Error: Could not write to the file '{csv_output_path}'.")

if __name__ == "__main__":
    # Your list of important items to mark as targets
    priority_items = [
        "Divine Orb", "Exalted Orb", "Orb of Annulment", "Chaos Orb", 
        "Omen of Light", "Omen of Whittling", "Hinekora's Lock", "Rakiata's Flow",
        "Perfect Exalted Orb", "Talisman of Sirrius", "Ancient Jawbone", 
        "Essence of Horror", "Farrul's Rune of the Chase", "Dialla's Desire", 
        "Omen of Sinistral Annulment", "Atalui's Bloodletting", "Simulacrum Splinter",
        "Perfect Chaos Orb", "Ancient Collarbone", "Runic Splinter", "Ancient Rib", 
        "Omen of Homogenising Exaltation"
    ]

    # The categories you want to include in the filter
    categories_to_include = [
        "currency",
        "ritual",
        "fragments",
        "talismans",
        "abyss",
        "essences",
        "runes",
        "lineagesupportgems",
    ]
    
    # --- Configuration ---
    JSON_INPUT_FILE = "item_data.json"
    CSV_OUTPUT_FILE = "target_item_ids.csv"

    create_target_item_csv(JSON_INPUT_FILE, categories_to_include, priority_items, CSV_OUTPUT_FILE)
import asyncio
import aiohttp
import csv
import os
from datetime import datetime

# The name of the league to fetch data for.
LEAGUE_NAME = "Standard"
# The CSV file to save the data to.
CSV_FILENAME = "currency_exchange_history.csv"

# New, clearer headers for the CSV file.
CSV_HEADERS = [
    "snapshot_epoch",
    "league",
    "pair_name",
    "currency_to_buy",
    "currency_to_sell",
    "rate",
    "inventory_sell",
    "inventory_buy"
]

def get_canonical_pair_name(currency_a, currency_b):
    """Creates a consistent, alphabetically sorted pair name."""
    parts = sorted([currency_a, currency_b])
    return f"{parts[0]}-{parts[1]}"

async def fetch_currency_data(session, league):
    """
    Fetches the currency exchange data from the Path of Exile API.
    """
    url = f"https://www.pathofexile.com/api/trade/exchange/{league}"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        print(f"Error fetching data from Poe API: {e}")
        return None

def transform_data(raw_data, league):
    """
    Transforms the raw API data into a list of dictionaries with clear,
    consistent naming.
    """
    if not raw_data or 'result' not in raw_data:
        return []

    transformed_data = []
    snapshot_epoch = int(datetime.now().timestamp())

    for listing_id, listing_data in raw_data['result'].items():
        if 'listing' not in listing_data.get('result', {}):
            continue

        result = listing_data['result']
        listing_details = result['listing']
        
        # Explicitly define what currency is being sold and what is being bought
        currency_to_sell = result['trade']['have'][0]
        currency_to_buy = result['trade']['want'][0]

        # Get the amounts from the listing
        # 'amount' is the stock the seller has of their currency
        # 'price.amount' is the amount of the other currency they want for it
        sell_inventory = listing_details.get('amount', 0)
        buy_inventory = listing_details['price'].get('amount', 0)
        
        # The exchange rate is how much of the 'buy' currency you get for one 'sell' currency
        rate = result.get('rate', 0.0)

        transformed_data.append({
            "snapshot_epoch": snapshot_epoch,
            "league": league,
            "pair_name": get_canonical_pair_name(currency_to_buy, currency_to_sell),
            "currency_to_buy": currency_to_buy,
            "currency_to_sell": currency_to_sell,
            "rate": rate,
            "inventory_sell": sell_inventory,
            "inventory_buy": buy_inventory,
        })

    return transformed_data

async def main():
    """
    The main function that orchestrates the fetching, transforming, and saving of data.
    """
    output_path = os.path.join(os.path.dirname(__file__), CSV_FILENAME)
    
    # Create the CSV file with headers if it doesn't exist.
    file_exists = os.path.exists(output_path)
    
    async with aiohttp.ClientSession() as session:
        raw_data = await fetch_currency_data(session, LEAGUE_NAME)
        if raw_data:
            transformed_data = transform_data(raw_data, LEAGUE_NAME)
            
            # Use 'w' for new file to write headers, 'a' to append to existing file
            with open(output_path, 'a' if file_exists else 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(transformed_data)
            
            print(f"Successfully saved {len(transformed_data)} new currency listing records.")

if __name__ == "__main__":
    asyncio.run(main())
import asyncio
import aiohttp
import json
import os

# --- Configuration ---
# These filenames are our temporary, flat-file database.
LEAGUE_FILE = "active_league.txt"
CURRENCY_FILE = "currencies.json"

# The User-Agent is crucial to avoid being blocked by the API.
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

async def get_active_poe2_league(session):
    """
    Fetches the list of all leagues and identifies the active PoE2 challenge league.
    If no challenge league is found, it defaults to the main permanent league for PoE2.
    """
    print("Fetching league data...")
    # The key is to use the `realm=poe2` parameter to filter for PoE2 leagues.
    url = "https://www.pathofexile.com/api/leagues?realm=poe2"
    try:
        async with session.get(url, headers=HEADERS) as response:
            response.raise_for_status()
            leagues = await response.json()

            # First, try to find a temporary challenge league.
            # We identify these because they are not permanent.
            for league in leagues:
                if not league.get('permanent', False):
                    print(f"Found active PoE2 challenge league: {league['id']}")
                    return league['id']
            
            # If no temporary league is found, fall back to the main permanent league.
            # This is likely to be the default or "Standard" league for PoE2.
            for league in leagues:
                if league.get('permanent', True): # Default to permanent if key is missing
                    print(f"No challenge league found. Defaulting to permanent PoE2 league: {league['id']}")
                    return league['id']

            return None
    except aiohttp.ClientError as e:
        print(f"Error fetching league data: {e}")
        return None

async def get_poe2_currencies(session):
    """
    Fetches the master list of all items and extracts only the currencies.
    """
    print("Fetching all item and currency data...")
    # The 404 error proved that `/poe2` does not belong in this URL path.
    # This is a universal endpoint.
    url = "https://www.pathofexile.com/api/trade/data/items"
    try:
        async with session.get(url, headers=HEADERS) as response:
            response.raise_for_status()
            data = await response.json()
            
            currencies = []
            # The item data is structured in categories. We loop through to find 'Currency'.
            for category in data.get('result', []):
                if category.get('label', '').lower() == 'currency':
                    for item in category.get('entries', []):
                        # We only need the 'id' of the currency for the trade API query.
                        if 'id' in item:
                            currencies.append(item['id'])
            
            print(f"Found {len(currencies)} currency types.")
            return currencies
    except aiohttp.ClientError as e:
        print(f"Error fetching item data: {e}")
        return []

async def main():
    """
    Main function to run the sync process and save the data to flat files.
    """
    async with aiohttp.ClientSession() as session:
        # Step 1: Get the active league name.
        active_league = await get_active_poe2_league(session)
        if not active_league:
            print("Could not determine an active PoE2 league. Halting.")
            return

        # Step 2: Get the full list of currencies.
        currency_list = await get_poe2_currencies(session)
        if not currency_list:
            print("Could not retrieve currency list. Halting.")
            return

        # Step 3: Save the retrieved data to our flat-file "database".
        # dataGet.py will read these files.
        with open(LEAGUE_FILE, 'w') as f:
            f.write(active_league)
        print(f"Active league '{active_league}' saved to {LEAGUE_FILE}")

        with open(CURRENCY_FILE, 'w') as f:
            json.dump(currency_list, f)
        print(f"Currency list saved to {CURRENCY_FILE}")

if __name__ == "__main__":
    asyncio.run(main())

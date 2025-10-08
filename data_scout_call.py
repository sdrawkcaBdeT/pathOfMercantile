import requests
import csv
from datetime import datetime

def get_leagues():
    """
    Fetches the list of available leagues from the API.
    """
    url = "https://poe2scout.com/api/leagues"
    try:
        response = requests.get(url)
        response.raise_for_status()
        leagues = response.json()
        print("Available leagues:")
        for league in leagues:
            print(f"- {league.get('name')}")
        return leagues
    except requests.exceptions.RequestException as e:
        print(f"Error fetching leagues: {e}")
        return None

def get_currency_history(league_name, start_date_str):
    """
    Fetches historical currency data for a given league and saves it to a CSV file.
    
    Args:
        league_name (str): The name of the league (e.g., "Rise of the Abyssal").
        start_date_str (str): The start date of the league in "YYYY-MM-DD" format.
    """
    # First, let's get the list of leagues to make sure the name is correct.
    leagues = get_leagues()
    if not leagues or not any(l.get('name') == league_name for l in leagues):
        print(f"League '{league_name}' not found in the list of available leagues.")
        return

    # --- Method 1: Using league_start_day with a date string (as per source code) ---
    print("\nAttempting to fetch data using league_start_day...")
    params = {
        "league": league_name,
        "league_start_day": start_date_str
    }
    url = "https://poe2scout.com/api/currencyExchange/SnapshotHistory"
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            print("No data returned from the API.")
            return

        csv_file = f"{league_name.replace(' ', '_')}_currency_history.csv"
        headers = data[0].keys()

        with open(csv_file, 'w', newline='', encoding='utf-8') as output_file:
            dict_writer = csv.DictWriter(output_file, headers)
            dict_writer.writeheader()
            dict_writer.writerows(data)

        print(f"Data successfully saved to {csv_file}")

    except requests.exceptions.HTTPError as e:
        print(f"An HTTP error occurred with league_start_day: {e}")
        print("This might be due to an incorrect start date or an API change.")
        
        # --- Method 2: Alternative using epoch timestamp ---
        print("\nNow attempting to fetch data using an epoch timestamp...")
        try:
            # Convert the start date to an epoch timestamp (in seconds)
            start_date_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
            epoch_timestamp = int(start_date_dt.timestamp())
            
            alt_params = {
                "league": league_name,
                "timestamp": epoch_timestamp 
            }
            # Note: We are still calling the same endpoint, just with a different parameter.
            # This might not be the correct endpoint for a timestamp-based query.
            alt_response = requests.get(url, params=alt_params)
            alt_response.raise_for_status()
            alt_data = alt_response.json()

            if not alt_data:
                print("No data returned using the timestamp method.")
                return

            csv_file = f"{league_name.replace(' ', '_')}_currency_history_epoch.csv"
            headers = alt_data[0].keys()

            with open(csv_file, 'w', newline='', encoding='utf-8') as output_file:
                dict_writer = csv.DictWriter(output_file, headers)
                dict_writer.writeheader()
                dict_writer.writerows(alt_data)
            
            print(f"Success with timestamp! Data saved to {csv_file}")

        except requests.exceptions.RequestException as alt_e:
            print(f"The alternative method using a timestamp also failed: {alt_e}")
            print("Please double-check the league start date and the API documentation if available.")
            
    except requests.exceptions.RequestException as e:
        print(f"A network error occurred: {e}")


if __name__ == "__main__":
    # --- Configuration ---
    LEAGUE_NAME = "Rise of the Abyssal"
    # This is the start date found from web search. You may need to adjust it.
    LEAGUE_START_DATE = "2025-08-29" 
    
    get_currency_history(LEAGUE_NAME, LEAGUE_START_DATE)
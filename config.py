import os
from dotenv import load_dotenv

# Load environment variables from the .env file in the current directory
load_dotenv()

# --- API Configuration ---
# Load the REALM, with a default of 'poe2' if not specified
REALM = os.getenv("REALM", "poe2")

# Load the API URLs from the environment file
LEAGUE_API_URL = os.getenv("LEAGUE_API_URL")
STATIC_DATA_URL = os.getenv("STATIC_DATA_URL")
EXCHANGE_API_URL = os.getenv("EXCHANGE_API_URL")

# --- Polite Header ---
# This identifies our script to the API administrators, which is good practice.
# You can change the contact email to your own.
HEADERS = {
    'User-Agent': 'Path_of_Mercantile_Bot (contact: sdrawkcabdet@gmail.com)',
    'Content-Type': 'application/json'
}

# --- Local File "Database" ---
# Defines the names of the files our scripts will use to store and read data.
LEAGUE_FILE = "active_league.txt"
CURRENCY_FILE = "currencies.json"
CSV_FILENAME = "currency_exchange_history.csv"
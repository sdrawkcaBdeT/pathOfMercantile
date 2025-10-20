import pandas as pd
import itertools
import sys
from collections import defaultdict

# --- Configuration ---
DATA_FILE = 'P:\\market_data.csv' 
PROFIT_THRESHOLD = 1.0 # 1.0 = breakeven (loses 3 Gold)

# --- Data Loading ---
try:
    df = pd.read_csv(DATA_FILE)
except FileNotFoundError:
    print(f"FATAL ERROR: The file '{DATA_FILE}' was not found.")
    print("Please check the DATA_FILE variable in the script.")
    sys.exit(1)
except Exception as e:
    print(f"An error occurred while reading the CSV: {e}")
    sys.exit(1)

# --- Main Arbitrage Logic ---

def find_arbitrage(full_df, profit_threshold):
    """
    Analyzes the latest scan_id for triangular arbitrage, using both
    'available_trades' (ASK) and 'competing_trades' (BID) for a
    two-sided market view.
    """
    
    # 1. Isolate the latest scan data
    try:
        latest_scan_id = full_df['scan_id'].max()
    except ValueError:
        print("Dataframe is empty. No data to process.")
        return
        
    print(f"--- Analyzing latest data: scan_id {latest_scan_id} ---")

    # 2. Filter for only the best prices (row_num == 1)
    df_latest = full_df[
        (full_df['scan_id'] == latest_scan_id) &
        (full_df['row_num'] == 1)
    ].copy()

    # 3. Create a two-sided rate lookup dictionary
    #    Key: (currency_have, currency_want)
    #    Value: {'ask': ratio_available, 'bid': ratio_competing, ...}
    rates = defaultdict(dict)
    
    for _, row in df_latest.iterrows():
        if pd.isna(row['ratio']):
            continue
        
        key = (row['currency_have'], row['currency_want'])
        
        if row['trade_type'] == 'available_trades':
            rates[key]['ask_ratio'] = row['ratio']
            rates[key]['ask_stock'] = row['stock']
        elif row['trade_type'] == 'competing_trades':
            rates[key]['bid_ratio'] = row['ratio']
            rates[key]['bid_stock'] = row['stock']

    if not rates:
        print("No valid rate data found for the latest scan.")
        return

    # 4. Get a list of all unique currencies and find arbitrage loops
    all_currencies = pd.unique(df_latest[['currency_have', 'currency_want']].values.ravel('K'))
    profitable_loops = []

    # Iterate over every 3-currency permutation (A, B, C)
    for p in itertools.permutations(all_currencies, 3):
        A, B, C = p
        
        # We are checking the loop: A -> B -> C -> A
        
        # Leg 1: Buy B using A. (Scan: have=A, want=B)
        pair_AB = rates.get((A, B))
        
        # Leg 2: Buy C using B. (Scan: have=B, want=C)
        pair_BC = rates.get((B, C))
        
        # Leg 3: Sell C, get A. (Scan: have=A, want=C)
        pair_AC = rates.get((A, C)) # Note the pair!

        # Check if all 3 pairs have full data (ask and bid)
        if (pair_AB and 'ask_ratio' in pair_AB and
            pair_BC and 'ask_ratio' in pair_BC and
            pair_AC and 'bid_ratio' in pair_AC):
            
            # 5. Calculate Profitability using the new formula
            
            rate_A_to_B_BUY = pair_AB['ask_ratio'] # B per A
            rate_B_to_C_BUY = pair_BC['ask_ratio'] # C per B
            rate_A_to_C_SELL = pair_AC['bid_ratio'] # C per A (from competing)

            # Prevent division by zero if a bid ratio is 0
            if rate_A_to_C_SELL == 0:
                continue

            profit_factor = (rate_A_to_B_BUY * rate_B_to_C_BUY) / rate_A_to_C_SELL
            
            if profit_factor > profit_threshold:
                
                # 6. Calculate Max Trade Size (based on stock)
                # This is a bit more complex, but we can approximate it
                
                # Stock for leg 1 (A->B) is stock of B
                stock_B_available = pair_AB['ask_stock']
                
                # Stock for leg 2 (B->C) is stock of C
                stock_C_available_leg2 = pair_BC['ask_stock']
                
                # Stock for leg 3 (A->C) is stock of C people will buy
                stock_C_available_leg3 = pair_AC['bid_stock']

                # The amount of C we can trade is limited by leg 2 and 3
                max_C_tradeable = min(stock_C_available_leg2, stock_C_available_leg3)

                # How much B is needed for that much C?
                max_B_needed = max_C_tradeable / rate_B_to_C_BUY
                
                # The amount of B we can trade is limited by leg 1 and this
                max_B_tradeable = min(stock_B_available, max_B_needed)
                
                # How much A is needed for that much B?
                max_A_tradeable = max_B_tradeable / rate_A_to_B_BUY
                
                profitable_loops.append({
                    "loop": f"{A} -> {B} -> {C} -> {A}",
                    "profit_factor": profit_factor,
                    "max_trade_A": max_A_tradeable
                })

    # 7. Report the results
    if profitable_loops:
        print("\n--- Profitable Arbitrage Loops Found! ---")
        for loop in profitable_loops:
            print(f"  Loop: {loop['loop']}")
            print(f"    Profit Factor: {loop['profit_factor']:.6f} (Target: > {profit_threshold})")
            print(f"    Max Trade (in {loop['loop'].split(' ')[0]}): {loop['max_trade_A']:.4f}\n")
    else:
        print("\nNo profitable (A->B->C->A) loops found in the latest scan.")


# --- Run the analysis ---
if __name__ == "__main__":
    find_arbitrage(df, PROFIT_THRESHOLD)
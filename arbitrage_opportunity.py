import pandas as pd
import math
import collections
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone # For timestamping alerts

# --- Configuration Files ---
DATA_FILE = Path('P:\\market_data.csv')
OCR_COMPLETE_FILE = Path('P:\\ocr_complete.json')
# NEW: Alert file for the GUI
ARBITRAGE_ALERT_FILE = Path('P:\\arbitrage_alert.json')
# NEW: File storing your currency amounts
MY_CURRENCY_FILE = Path('my_currency.json')
# This script's private state file
LAST_PROCESSED_FILE = Path('last_processed.json')

POLL_INTERVAL_SECONDS = 3 # How often to check for the flag file

# --- State Management Functions (Unchanged) ---

def get_last_processed_scan():
    """Reads the last scan ID we successfully processed."""
    try:
        with open(LAST_PROCESSED_FILE, 'r') as f:
            return json.load(f).get('last_processed_id', -1)
    except (FileNotFoundError, json.JSONDecodeError):
        return -1

def set_last_processed_scan(scan_id):
    """Writes the new last processed scan ID to our state file."""
    try:
        with open(LAST_PROCESSED_FILE, 'w') as f:
            json.dump({'last_processed_id': scan_id}, f, indent=4)
    except IOError as e:
        print(f"CRITICAL ERROR: Could not write to {LAST_PROCESSED_FILE}: {e}")

def get_latest_complete_scan():
    """Reads the OCR_COMPLETE_FILE to see the latest finished scan."""
    try:
        with open(OCR_COMPLETE_FILE, 'r') as f:
            # Add check for empty file which can happen during write
            content = f.read()
            if not content:
                print(f"Warning: {OCR_COMPLETE_FILE} is empty, treating as no new scan.")
                return -1
            return json.loads(content).get('latest_complete_scan', -1)
    except FileNotFoundError:
        return -1
    except json.JSONDecodeError:
         print(f"Warning: Error decoding JSON from {OCR_COMPLETE_FILE}. Retrying.")
         return -1
    except IOError as e:
        print(f"File read error on {OCR_COMPLETE_FILE}, retrying... ({e})")
        return -1
    except Exception as e:
        print(f"Unexpected error reading {OCR_COMPLETE_FILE}: {e}")
        return -1


# --- Data Loading and Market Building (Unchanged) ---

def load_and_filter_data(filepath, scan_id):
    """Loads and filters data for the specified scan_id."""
    try:
        full_df = pd.read_csv(filepath)
    except FileNotFoundError:
        print(f"Error: Data file not found at {filepath}", file=sys.stderr)
        return None
    except pd.errors.EmptyDataError:
        print(f"Warning: Data file {filepath} is empty.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error loading data: {e}", file=sys.stderr)
        return None

    if full_df.empty:
        print("Error: Data file is empty.")
        return None

    df = full_df[full_df['scan_id'] == scan_id].copy()

    if df.empty:
        # This is expected if the scan ID isn't in the file yet
        print(f"Info: No data found for scan_id {scan_id} in {filepath}")
        return None

    return df

def build_market_and_graph(df):
    """Builds market books and L1 graph from filtered dataframe."""
    market_books = collections.defaultdict(lambda: collections.defaultdict(dict))
    graph = collections.defaultdict(dict)
    all_currencies = set(df['currency_have']) | set(df['currency_want'])
    grouped = df.groupby(['currency_have', 'currency_want'])

    for (have_curr, want_curr), group in grouped:
        available = group[group['trade_type'] == 'available_trades'].sort_values('ratio', ascending=False)
        competing = group[group['trade_type'] == 'competing_trades'].sort_values('ratio', ascending=True)

        market_books[have_curr][want_curr]['available_trades'] = [(row['ratio'], row['stock']) for _, row in available.iterrows()]
        market_books[have_curr][want_curr]['competing_trades'] = [(row['ratio'], row['stock']) for _, row in competing.iterrows()]

        if not available.empty:
            best_ask = available.iloc[0]
            if best_ask['ratio'] > 0:
                weight = -math.log(best_ask['ratio'])
                graph[have_curr][want_curr] = {'weight': weight, 'type': 'buy', 'have': have_curr, 'want': want_curr}

        if not competing.empty:
            best_bid = competing.iloc[0]
            if best_bid['ratio'] > 0:
                weight = math.log(best_bid['ratio'])
                graph[want_curr][have_curr] = {'weight': weight, 'type': 'sell', 'have': want_curr, 'want': have_curr}

    return graph, market_books, list(all_currencies)

# --- Core Arbitrage Logic (Unchanged, except for simulation functions) ---

def find_candidate_paths_with_bellman_ford(graph, currencies, start_node):
    """Stage 1: The Finder."""
    distance = {node: float('inf') for node in currencies}
    predecessor = {node: None for node in currencies}
    predecessor_edge_data = {node: None for node in currencies}
    distance[start_node] = 0

    for _ in range(len(currencies) - 1):
        for u in graph:
            for v, data in graph[u].items():
                if distance[u] == float('inf'): continue
                if distance[u] + data['weight'] < distance[v]:
                    distance[v] = distance[u] + data['weight']
                    predecessor[v] = u
                    predecessor_edge_data[v] = data

    negative_cycles = []
    seen_cycles = set()

    for u in graph:
        for v, data in graph[u].items():
            if distance[u] == float('inf'): continue
            if distance[u] + data['weight'] < distance[v]:
                cycle_node = v
                for _ in range(len(currencies)):
                    if cycle_node not in predecessor or predecessor[cycle_node] is None:
                        cycle_node = None; break
                    cycle_node = predecessor[cycle_node]
                if cycle_node is None: continue

                cycle = []
                curr = cycle_node
                while True:
                    if curr not in predecessor_edge_data or predecessor_edge_data[curr] is None: break
                    edge_data = predecessor_edge_data[curr]
                    cycle.append(edge_data)
                    curr = predecessor[curr]
                    if curr == cycle_node: break
                    if not curr or curr not in predecessor: break
                if not cycle or curr != cycle_node: continue

                cycle.reverse()
                cycle_key = tuple(d['have'] + '->' + d['want'] for d in cycle)
                if cycle_key not in seen_cycles:
                    negative_cycles.append(cycle)
                    seen_cycles.add(cycle_key)
    return negative_cycles


def simulate_buy_step(amount_to_spend_have, book):
    """Simulates a 'buy' step (available_trades)"""
    total_bought_want = 0
    total_cost_have = 0
    for ratio, stock_in_want in book:
        if ratio <= 0: continue
        remaining_to_spend_have = amount_to_spend_have - total_cost_have
        if remaining_to_spend_have <= 0: break
        amount_we_can_buy_want = math.floor(remaining_to_spend_have * ratio)
        if amount_we_can_buy_want <= 0: break
        amount_to_buy_want = min(amount_we_can_buy_want, stock_in_want)
        cost_for_this_buy_have = math.ceil(amount_to_buy_want / ratio)
        if cost_for_this_buy_have > remaining_to_spend_have:
            amount_to_buy_want -= 1
            if amount_to_buy_want <= 0: break
            cost_for_this_buy_have = math.ceil(amount_to_buy_want / ratio)
            if cost_for_this_buy_have > remaining_to_spend_have: break
        total_bought_want += amount_to_buy_want
        total_cost_have += cost_for_this_buy_have
    return int(total_bought_want), int(total_cost_have)

def simulate_sell_step(amount_to_sell_want, book):
    """Simulates a 'sell' step (competing_trades)"""
    total_proceeds_have = 0
    amount_sold_want = 0
    for ratio, stock_in_want in book:
        if ratio <= 0: continue
        remaining_to_sell_want = amount_to_sell_want - amount_sold_want
        if remaining_to_sell_want <= 0: break
        sellable_at_this_level_want = min(remaining_to_sell_want, stock_in_want)
        proceeds_for_this_level_have = math.floor(sellable_at_this_level_want / ratio)
        total_proceeds_have += proceeds_for_this_level_have
        amount_sold_want += sellable_at_this_level_want
    return int(total_proceeds_have), int(amount_sold_want)

def simulate_path(path, market_books, initial_investment):
    """Stage 2: The Calculator."""
    if not path: return 0, ["Empty path provided."]
    start_currency = path[0]['have']
    current_currency = start_currency
    current_amount = initial_investment
    log = []
    path_str = ' -> '.join(d['have'] for d in path) + ' -> ' + path[0]['have']
    log.append(f"--- Simulating Path: {path_str} ---")
    log.append(f"Start: {current_amount} {current_currency}")

    for i, step in enumerate(path):
        if step['have'] != current_currency:
            log.append(f"Error: Path mismatch. Have {current_currency}, but step needs {step['have']}")
            return 0, log
        if current_amount <= 0:
            log.append(f"Step {i+1} (FAIL): Amount is zero or negative. Stopping.")
            current_amount = 0; break

        if step['type'] == 'buy':
            try:
                book = market_books[step['have']][step['want']]['available_trades']
                if not book: raise KeyError
            except KeyError:
                log.append(f"Step {i+1} (FAIL): No 'available_trades' (Ask) book for {step['have']}->{step['want']}")
                current_amount = 0; break
            amount_bought, cost = simulate_buy_step(current_amount, book)
            log.append(f"Step {i+1} (BUY): Spent {cost} {step['have']} to buy {amount_bought} {step['want']}")
            current_amount = amount_bought; current_currency = step['want']
        elif step['type'] == 'sell':
            try:
                book = market_books[step['want']][step['have']]['competing_trades']
                if not book: raise KeyError
            except KeyError:
                log.append(f"Step {i+1} (FAIL): No 'competing_trades' (Bid) book for {step['want']}<-{step['have']}")
                current_amount = 0; break
            proceeds, amount_sold = simulate_sell_step(current_amount, book)
            log.append(f"Step {i+1} (SELL): Sold {amount_sold} {step['have']} to get {proceeds} {step['want']}")
            current_amount = proceeds; current_currency = step['want']

    log.append(f"End: {current_amount} {current_currency}")
    profit = 0
    if current_currency == start_currency:
        profit = current_amount - initial_investment
        log.append(f"Result: {profit} {start_currency} profit.")
    else:
        log.append(f"Result: Failed to return to start currency. Ended with {current_amount} {current_currency}")
    return profit, log


# --- MODIFIED: run_analysis function ---
def run_analysis(scan_id):
    """
    Loads data, runs finder and calculator, and WRITES results to alert file.
    """
    print(f"\n--- Analyzing latest data: scan_id {scan_id} ---")

    df = load_and_filter_data(DATA_FILE, scan_id)
    if df is None:
        print(f"Failed to load data for scan {scan_id}. Aborting analysis.")
        # Write a "no data" alert? Or just do nothing? Let's do nothing for now.
        # write_alert_file(scan_id, False, None) # Optional
        return

    graph, market_books, currencies = build_market_and_graph(df)
    if not graph:
        print("Market graph could not be built. Skipping analysis.")
        # write_alert_file(scan_id, False, None) # Optional
        return

    edge_count = sum(len(inner_dict) for inner_dict in graph.values())
    print(f"Loaded {len(currencies)} currencies and {edge_count} L1 trade edges.")
    print("\n" + "="*50 + "\n")

    print("Stage 1: Finding candidate arbitrage paths with Bellman-Ford...")
    super_source = "SUPER_SOURCE_NODE"
    currencies_with_source = currencies + [super_source]
    bf_graph = collections.defaultdict(dict, graph)
    for node in currencies:
        bf_graph[super_source][node] = {'weight': 0, 'type': 'start', 'have': super_source, 'want': node}
    all_candidate_paths = find_candidate_paths_with_bellman_ford(bf_graph, currencies_with_source, super_source)
    print(f"Found {len(all_candidate_paths)} unique potential arbitrage cycles.")
    print("\n" + "="*50 + "\n")

    print("Stage 2: Simulating paths with full market depth...")

    # --- Read Starting Investments ---
    try:
        with open(MY_CURRENCY_FILE, 'r') as f:
            starting_investments = json.load(f)
        print(f"Loaded starting investments from {MY_CURRENCY_FILE}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load {MY_CURRENCY_FILE}. Using default investment. Error: {e}")
        starting_investments = {} # Fallback to default
    DEFAULT_INVESTMENT = 1000 # Keep a fallback

    profitable_loops_details = [] # Store details for the alert file

    if not all_candidate_paths:
        print("No candidate paths to simulate.")
    else:
        for i, path in enumerate(all_candidate_paths):
            start_currency = path[0]['have']
            # Get specific investment or use default
            initial_investment = starting_investments.get(start_currency, DEFAULT_INVESTMENT)

            profit, log = simulate_path(path, market_books, initial_investment)
            print("\n".join(log)) # Keep printing detailed log to console
            print("-" * 20)

            if profit > 0:
                profitable_loops_details.append({
                    'path': path, # Store the raw path data if needed later
                    'path_string': ' -> '.join(d['have'] for d in path) + ' -> ' + path[0]['have'],
                    'start_currency': start_currency,
                    'investment': initial_investment,
                    'profit': profit,
                    'steps': log # Store the full log for the GUI
                })

    print("\n" + "="*50 + "\n")
    print("Arbitrage Scan Complete.")
    print(f"Found {len(profitable_loops_details)} verified profitable loops.")
    print("\n" + "="*50 + "\n")

    # --- Write Alert File ---
    best_loop_data = None
    if profitable_loops_details:
        # Simple approach: just take the first one found
        best_loop_data = profitable_loops_details[0]
        # Optional: Add logic here to select the *best* loop if multiple found
        # e.g., best_loop_data = max(profitable_loops_details, key=lambda x: x['profit'] / x['investment'])

        # Print summary of the best loop to console
        print("--- Best Loop Found ---")
        print(f"  Path: {best_loop_data['path_string']}")
        print(f"  Investment: {best_loop_data['investment']} {best_loop_data['start_currency']}")
        print(f"  Profit: {best_loop_data['profit']} {best_loop_data['start_currency']}")
        print("-" * 25)

    # Prepare data for JSON file
    alert_data = {
        "scan_id": scan_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profitable": bool(best_loop_data), # True if best_loop_data is not None
        "best_loop": best_loop_data # Will be None if no profit found
    }

    try:
        with open(ARBITRAGE_ALERT_FILE, 'w') as f:
            json.dump(alert_data, f, indent=4)
        print(f"Successfully wrote alert data to {ARBITRAGE_ALERT_FILE}")
    except IOError as e:
        print(f"CRITICAL ERROR: Failed to write alert data to {ARBITRAGE_ALERT_FILE}: {e}")
    except Exception as e:
         print(f"CRITICAL ERROR: Unexpected error writing alert data: {e}")

# --- Main Watcher Loop (Unchanged) ---

def main():
    """Main watcher loop."""
    print("Watcher started.")
    print(f"Monitoring {OCR_COMPLETE_FILE} for new completed scans...")
    print(f"Checking every {POLL_INTERVAL_SECONDS} seconds.")

    while True:
        try:
            my_last_scan = get_last_processed_scan()
            latest_complete_scan = get_latest_complete_scan()

            if latest_complete_scan > my_last_scan:
                print(f"\nNew complete scan detected: {latest_complete_scan}.")
                run_analysis(latest_complete_scan)
                set_last_processed_scan(latest_complete_scan)
                print(f"\nAnalysis complete. Waiting for next scan (>{latest_complete_scan})...")

            time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nWatcher stopped by user.")
            break
        except Exception as e:
            print(f"An unexpected error occurred in the watcher loop: {e}")
            print(f"Error Type: {type(e)}")
            import traceback
            traceback.print_exc() # Print detailed traceback
            print("Restarting watcher in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    main()
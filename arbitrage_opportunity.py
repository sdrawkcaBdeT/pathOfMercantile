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
ARBITRAGE_ALERT_FILE = Path('P:\\arbitrage_alert.json')
MY_CURRENCY_FILE = Path('my_currency.json')
LAST_PROCESSED_FILE = Path('last_processed.json')
# NEW: Gold cost and benchmark configuration
CURRENCY_GOLD_LOOKUP_FILE = Path('currency_gold_lookup.json')
BENCHMARK_CURRENCY = "Divine Orb"


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

# --- NEW: Data Loading for Gold and Benchmarks ---

def load_gold_costs(filepath):
    """Loads the currency-to-gold-cost lookup file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"WARNING: Could not load {filepath}. Gold costs will be 0. Error: {e}")
        return {}

def build_benchmark_rates(graph, currencies, benchmark_currency):
    """
    Builds a simple L1 conversion rate table to the benchmark currency.
    Uses the graph which already stores L1 rates.
    """
    print(f"Building benchmark rate table relative to: {benchmark_currency}")
    rates = {c: 0.0 for c in currencies}
    if benchmark_currency not in rates:
        print(f"CRITICAL: Benchmark currency '{benchmark_currency}' not found in market. Cannot rank.")
        return rates
        
    rates[benchmark_currency] = 1.0

    for curr in currencies:
        if curr == benchmark_currency:
            continue

        # Try to find a direct BUY (have=curr, want=bench)
        # This is an 'available_trades' edge
        buy_edge = graph.get(curr, {}).get(benchmark_currency, {})
        if buy_edge and buy_edge['type'] == 'buy':
            # weight = -log(ratio), ratio = bench/curr
            value = math.exp(-buy_edge['weight']) # value is bench_per_curr
            rates[curr] = value
            continue

        # Try to find a direct SELL (have=curr, want=bench)
        # This is a 'competing_trades' edge
        sell_edge = graph.get(curr, {}).get(benchmark_currency, {})
        if sell_edge and sell_edge['type'] == 'sell':
            # This edge was created from a (have=bench, want=curr) lookup
            # ratio = curr/bench, weight = log(ratio)
            ratio = math.exp(sell_edge['weight']) # ratio is curr_per_bench
            if ratio > 0:
                value = 1.0 / ratio # value is bench_per_curr
                rates[curr] = value
            continue
            
    # Report any currencies that couldn't be valued
    unvalued = [c for c, r in rates.items() if r == 0.0 and c != benchmark_currency]
    if unvalued:
        print(f"Warning: Could not find direct L1 conversion to {benchmark_currency} for: {', '.join(unvalued)}")
        
    return rates

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

# --- Core Arbitrage Logic (Bellman-Ford Unchanged) ---

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

# --- Simulation Functions (MODIFIED for Gold Cost) ---

def simulate_buy_step(amount_to_spend_have, book):
    """
    Simulates a 'buy' step (available_trades).
    Returns: (total_bought_want, total_cost_have)
    """
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
    """
    Simulates a 'sell' step (competing_trades).
    Returns: (total_proceeds_have, amount_sold_want)
    """
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

def simulate_path(path, market_books, initial_investment, gold_cost_lookup):
    """
    Stage 2: The Calculator.
    MODIFIED: Now accepts gold_cost_lookup and returns (profit, total_gold_cost, log).
    """
    if not path: return 0, 0, ["Empty path provided."]
    
    start_currency = path[0]['have']
    current_currency = start_currency
    current_amount = initial_investment
    
    total_gold_cost = 0
    log = []
    path_str = ' -> '.join(d['have'] for d in path) + ' -> ' + path[0]['have']
    log.append(f"--- Simulating Path: {path_str} ---")
    log.append(f"Start: {current_amount} {current_currency}")

    for i, step in enumerate(path):
        if step['have'] != current_currency:
            log.append(f"Error: Path mismatch. Have {current_currency}, but step needs {step['have']}")
            return 0, total_gold_cost, log
        if current_amount <= 0:
            log.append(f"Step {i+1} (FAIL): Amount is zero or negative. Stopping.")
            current_amount = 0; break

        step_gold_cost = 0
        received_currency = step['want']
        # Handle nulls from JSON by defaulting to 0
        gold_per_unit = gold_cost_lookup.get(received_currency, 0) or 0

        if step['type'] == 'buy':
            try:
                book = market_books[step['have']][step['want']]['available_trades']
                if not book: raise KeyError
            except KeyError:
                log.append(f"Step {i+1} (FAIL): No 'available_trades' (Ask) book for {step['have']}->{step['want']}")
                current_amount = 0; break
                
            amount_bought, cost = simulate_buy_step(current_amount, book)
            step_gold_cost = gold_per_unit * amount_bought
            log.append(f"Step {i+1} (BUY): Spent {cost} {step['have']} to buy {amount_bought} {step['want']} (Gold: {step_gold_cost})")
            current_amount = amount_bought
            current_currency = step['want']
            
        elif step['type'] == 'sell':
            try:
                book = market_books[step['want']][step['have']]['competing_trades']
                if not book: raise KeyError
            except KeyError:
                log.append(f"Step {i+1} (FAIL): No 'competing_trades' (Bid) book for {step['want']}<-{step['have']}")
                current_amount = 0; break
                
            proceeds, amount_sold = simulate_sell_step(current_amount, book)
            step_gold_cost = gold_per_unit * proceeds
            log.append(f"Step {i+1} (SELL): Sold {amount_sold} {step['have']} to get {proceeds} {step['want']} (Gold: {step_gold_cost})")
            current_amount = proceeds
            current_currency = step['want']

        total_gold_cost += step_gold_cost

    log.append(f"End: {current_amount} {current_currency}")
    profit = 0
    if current_currency == start_currency:
        profit = current_amount - initial_investment
        log.append(f"Result: {profit} {start_currency} profit (Total Gold Cost: {total_gold_cost}).")
    else:
        log.append(f"Result: Failed to return to start currency. Ended with {current_amount} {current_currency}")
        
    return profit, total_gold_cost, log


# --- MODIFIED: run_analysis function (Path 1 Implementation) ---
def run_analysis(scan_id):
    """
    Loads data, runs finder and calculator, ranks all loops,
    and WRITES the BEST result to alert file.
    """
    print(f"\n--- Analyzing latest data: scan_id {scan_id} ---")

    df = load_and_filter_data(DATA_FILE, scan_id)
    if df is None:
        print(f"Failed to load data for scan {scan_id}. Aborting analysis.")
        return

    graph, market_books, currencies = build_market_and_graph(df)
    if not graph:
        print("Market graph could not be built. Skipping analysis.")
        return

    edge_count = sum(len(inner_dict) for inner_dict in graph.values())
    print(f"Loaded {len(currencies)} currencies and {edge_count} L1 trade edges.")

    # --- Load Gold Costs and Benchmark Rates ---
    gold_cost_lookup = load_gold_costs(CURRENCY_GOLD_LOOKUP_FILE)
    benchmark_rates = build_benchmark_rates(graph, currencies, BENCHMARK_CURRENCY)
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

    print(f"Stage 2: Simulating all paths with full market depth (Benchmark: {BENCHMARK_CURRENCY})...")

    # --- Read Starting Investments ---
    # This will be used to calculate a dynamic, wealth-based investment size.
    try:
        with open(MY_CURRENCY_FILE, 'r') as f:
            starting_investments = json.load(f)
        print(f"Loaded starting investments from {MY_CURRENCY_FILE}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load {MY_CURRENCY_FILE}. Using 0 for all balances. Error: {e}")
        starting_investments = {} # Fallback to empty
    
    # Get the amount of benchmark currency (Divine Orbs) to use for conversions
    divine_stock = starting_investments.get(BENCHMARK_CURRENCY, 0)
    divines_to_convert = math.floor(divine_stock * 1.00)
    print(f"Using {divines_to_convert} {BENCHMARK_CURRENCY} (10% of {divine_stock}) as base for non-benchmark loops.")

    ranked_loops = [] # Store all profitable loops for ranking

    if not all_candidate_paths:
        print("No candidate paths to simulate.")
    else:
        for i, path in enumerate(all_candidate_paths):
            start_currency = path[0]['have']
            
            # --- Calculate Dynamic Investment based on user's logic ---
            existing_start_currency_stock = starting_investments.get(start_currency, 0)
            
            if start_currency == BENCHMARK_CURRENCY:
                # If the loop starts with Divine Orbs, just use our existing stock
                initial_investment = existing_start_currency_stock
            else:
                # If it starts with something else (e.g., Exalts):
                # 1. Get its value relative to Divines
                value_per_unit = benchmark_rates.get(start_currency, 0.0)
                if value_per_unit <= 0.0:
                    print(f"Skipping path for {start_currency}: No benchmark conversion rate found.")
                    continue # Can't calculate investment, so skip
                
                # 2. Convert our "divines_to_convert" into that currency
                # e.g., (62 Divine) / (0.01 Divine/Exalt) = 6200 Exalt
                converted_amount = math.floor(divines_to_convert / value_per_unit)
                
                # 3. Add our existing stock of that currency
                # e.g., 6200 + 13 = 6213
                initial_investment = converted_amount + existing_start_currency_stock

            if initial_investment <= 0:
                print(f"Skipping path for {start_currency}: Calculated investment is 0.")
                continue # Investment is too small to simulate

            # --- Run new simulation ---
            profit, total_gold_cost, log = simulate_path(path, market_books, initial_investment, gold_cost_lookup)
            
            print("\n".join(log)) # Keep printing detailed log to console
            print("-" * 20)

            if profit > 0:
                # --- Rank the loop ---
                value_per_unit = benchmark_rates.get(start_currency, 0.0)
                if value_per_unit == 0.0:
                    print(f"Warning: Cannot rank loop for {start_currency}. No benchmark conversion rate found.")
                    continue
                
                profit_in_benchmark = profit * value_per_unit
                
                if total_gold_cost > 0:
                    efficiency = profit_in_benchmark / total_gold_cost
                    efficiency_per_mil = efficiency * 1_000_000
                    efficiency_str = f"{efficiency_per_mil:.2f}"
                else:
                    # Positive profit for 0 gold cost is infinitely efficient
                    efficiency = float('inf') 
                    efficiency_str = "inf"

                # --- MODIFICATION: Update the last log line ---
                if log: # Make sure log is not empty
                    log.pop() # Remove the old "Result:" line
                    new_log_line = f"Result: {profit} {start_currency} profit (Total Gold Cost: {total_gold_cost}, {efficiency_str} DIV/1M gold)"
                    log.append(new_log_line)
                # --- END MODIFICATION ---

                path_string = ' -> '.join(d['have'] for d in path) + ' -> ' + path[0]['have']
                
                ranked_loops.append({
                    'path': path, # Store the raw path data if needed later
                    'path_string': path_string,
                    'start_currency': start_currency,
                    'investment': initial_investment,
                    'profit': profit,
                    'profit_benchmark': profit_in_benchmark,
                    'gold_cost': total_gold_cost,
                    'efficiency': efficiency,
                    'steps': log # Store the full log for the GUI
                })

    print("\n" + "="*50 + "\n")
    print("Arbitrage Scan Complete.")
    print(f"Found {len(ranked_loops)} verified profitable loops.")
    print("\n" + "="*50 + "\n")

    # --- Write Alert File ---
    best_loop_data = None
    if ranked_loops:
        # Sort by efficiency, highest first
        ranked_loops.sort(key=lambda x: x['efficiency'], reverse=True)
        best_loop_data = ranked_loops[0] # Select the BEST loop

        # Print summary of the best loop to console
        print("--- Best Loop Found (Ranked by Efficiency) ---")
        print(f"  Path: {best_loop_data['path_string']}")
        print(f"  Investment: {best_loop_data['investment']} {best_loop_data['start_currency']}")
        print(f"  Profit: {best_loop_data['profit']} {best_loop_data['start_currency']}")
        print(f"  Profit (Benchmark): {best_loop_data['profit_benchmark']:.4f} {BENCHMARK_CURRENCY}")
        print(f"  Gold Cost: {best_loop_data['gold_cost']}")
        print(f"  Efficiency (Profit/Gold): {best_loop_data['efficiency']:.4f}")
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
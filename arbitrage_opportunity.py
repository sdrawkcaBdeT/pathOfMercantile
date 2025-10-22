import pandas as pd
import math
import collections
import sys
import json
import time
import csv # Import csv for logging
from pathlib import Path
from datetime import datetime, timezone # For timestamping alerts

# --- Configuration Files ---
DATA_FILE = Path('P:\\market_data.csv')
OCR_COMPLETE_FILE = Path('P:\\ocr_complete.json')
ARBITRAGE_ALERT_FILE = Path('P:\\arbitrage_alert.json')
MY_CURRENCY_FILE = Path('my_currency.json')
LAST_PROCESSED_FILE = Path('last_processed.json')
CURRENCY_GOLD_LOOKUP_FILE = Path('currency_gold_lookup.json')

# --- [ NEW LOGGING FILES ] ---
# New log for the best opportunity found in each scan
OPPORTUNITY_LOG_FILE = Path('opportunity_log.csv')
# New log for the calculated VWAP benchmark rates for each scan
ROBUST_RATES_LOG_FILE = Path('robust_rates_log.csv')

BENCHMARK_CURRENCY = "Divine Orb"
POLL_INTERVAL_SECONDS = 3 # How often to check for the flag file

# --- [ NEW HELPER FUNCTION ] ---
def append_to_csv(filepath, header, data_row):
    """Appends a row to a CSV file, creating it with header if needed."""
    file_exists = filepath.exists()
    try:
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists or filepath.stat().st_size == 0:
                writer.writerow(header)
            writer.writerow(data_row)
        return True
    except IOError as e:
        print(f"CRITICAL ERROR: Could not write to {filepath}: {e}")
        return False

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

# --- Data Loading and Rate Building (Unchanged) ---

def load_gold_costs(filepath):
    """Loads the currency-to-gold-cost lookup file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"WARNING: Could not load {filepath}. Gold costs will be 0. Error: {e}")
        return {}

def build_robust_benchmark_rates(market_books, currencies, benchmark_currency):
    """
    Builds a robust, depth-weighted numéraire rate table using the
    full "known" market depth (VWAP of rows 1-5).
    """
    print(f" [INFO] Building robust benchmark rate table relative to: {benchmark_currency}")
    rates = {c: 0.0 for c in currencies}
    if benchmark_currency not in market_books:
        print(f" [CRITICAL] Benchmark currency '{benchmark_currency}' not found in market. Cannot rank.")
        return rates
        
    rates[benchmark_currency] = 1.0

    for curr in currencies:
        if curr == benchmark_currency:
            continue
        
        try:
            book = market_books[benchmark_currency][curr]['competing_trades']
            if not book:
                continue
        except KeyError:
            continue

        total_stock = 0.0
        total_value = 0.0
        
        for ratio, stock in book:
            if ratio <= 0:
                continue
            value_in_benchmark = 1.0 / ratio
            total_stock += stock
            total_value += stock * value_in_benchmark

        if total_stock > 0:
            robust_rate = total_value / total_stock
            rates[curr] = robust_rate

    unvalued = [c for c, r in rates.items() if r == 0.0 and c != benchmark_currency]
    if unvalued:
        print(f" [WARN] Could not find robust conversion for: {', '.join(unvalued)}")
        
    return rates

def load_and_filter_data(filepath, scan_id):
    """Loads and filters data for the specified scan_id."""
    try:
        full_df = pd.read_csv(filepath)
    except FileNotFoundError:
        print(f" [ERROR] Data file not found at {filepath}", file=sys.stderr)
        return None
    except pd.errors.EmptyDataError:
        print(f" [WARN] Data file {filepath} is empty.", file=sys.stderr)
        return None
    except Exception as e:
        print(f" [ERROR] Error loading data: {e}", file=sys.stderr)
        return None

    if full_df.empty:
        print(" [ERROR] Data file is empty.")
        return None

    df = full_df[full_df['scan_id'] == scan_id].copy()

    if df.empty:
        print(f" [INFO] No data found for scan_id {scan_id} in {filepath}")
        return None

    return df

def build_market_and_graph(df):
    """Builds market books and L1 graph from filtered dataframe."""
    market_books = collections.defaultdict(lambda: collections.defaultdict(dict))
    graph = collections.defaultdict(dict)
    all_currencies = set(df['currency_have']) | set(df['currency_want'])
    grouped = df.groupby(['currency_have', 'currency_want'])

    for (have_curr, want_curr), group in grouped:
        
        known_rows = group[group['row_num'] <= 5]
        
        available = known_rows[known_rows['trade_type'] == 'available_trades'].sort_values('ratio', ascending=False)
        competing = known_rows[known_rows['trade_type'] == 'competing_trades'].sort_values('ratio', ascending=True)

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

# --- Simulation Functions ---

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
    
    total_gold_cost = 0.0 # Use float for gold
    log = []
    path_str = ' -> '.join(d['have'] for d in path) + ' -> ' + path[0]['have']
    log.append(f"PATH | {path_str}")
    log.append(f"  Start: {current_amount:,} {current_currency}")

    for i, step in enumerate(path):
        if step['have'] != current_currency:
            log.append(f"  [ERROR] Path mismatch. Have {current_currency}, but step needs {step['have']}")
            return 0, total_gold_cost, log
        if current_amount <= 0:
            log.append(f"  Step {i+1} (FAIL): Amount is zero or negative. Stopping.")
            current_amount = 0; break

        step_gold_cost = 0.0
        received_currency = step['want']
        gold_per_unit = gold_cost_lookup.get(received_currency, 0) or 0

        if step['type'] == 'buy':
            try:
                book = market_books[step['have']][step['want']]['available_trades']
                if not book: raise KeyError
            except KeyError:
                log.append(f"  Step {i+1} (FAIL): No 'available_trades' (Ask) book for {step['have']}->{step['want']}")
                current_amount = 0; break
                
            amount_bought, cost = simulate_buy_step(current_amount, book)
            step_gold_cost = gold_per_unit * amount_bought
            log.append(f"  Step {i+1} (BUY): Spent {cost:,} {step['have']} → {amount_bought:,} {step['want']} ({step_gold_cost:,.0f}g)")
            current_amount = amount_bought
            current_currency = step['want']
            
        elif step['type'] == 'sell':
            try:
                book = market_books[step['want']][step['have']]['competing_trades']
                if not book: raise KeyError
            except KeyError:
                log.append(f"  Step {i+1} (FAIL): No 'competing_trades' (Bid) book for {step['want']}<-{step['have']}")
                current_amount = 0; break
                
            proceeds, amount_sold = simulate_sell_step(current_amount, book)
            step_gold_cost = gold_per_unit * proceeds
            log.append(f"  Step {i+1} (SELL): Sold {amount_sold:,} {step['have']} → {proceeds:,} {step['want']} ({step_gold_cost:,.0f}g)")
            current_amount = proceeds
            current_currency = step['want']

        total_gold_cost += step_gold_cost

    log.append(f"  End: {current_amount:,} {current_currency}")
    profit = 0
    if current_currency == start_currency:
        profit = current_amount - initial_investment
        log.append(f"  Result: {profit:+,} {start_currency} profit ({total_gold_cost:,.0f}g).")
    else:
        log.append(f"  Result: Failed to return to start currency. Ended with {current_amount:,} {current_currency}")
        
    return profit, total_gold_cost, log


# --- MODIFIED: run_analysis function (Path 1.75 + Logging + Pretty Print) ---
def run_analysis(scan_id):
    """
    Loads data, runs finder and calculator, ranks all loops,
    and WRITES the BEST result to alert file.
    """
    print("\n" + "="*80)
    print(f"--- STARTING ANALYSIS FOR SCAN ID: {scan_id} ---")
    print(f"--- {datetime.now(timezone.utc).isoformat()} ---")
    print("="*80)

    # --- 1. Load Data ---
    print("\n[PHASE 1: LOAD & PREPARE DATA]")
    df = load_and_filter_data(DATA_FILE, scan_id)
    if df is None:
        print(" [STOP] Failed to load data. Aborting analysis.")
        return

    graph, market_books, currencies = build_market_and_graph(df)
    if not graph:
        print(" [STOP] Market graph could not be built. Aborting analysis.")
        return

    edge_count = sum(len(inner_dict) for inner_dict in graph.values())
    print(f" [INFO] Loaded {len(currencies)} currencies and {edge_count} L1 trade edges (from {len(market_books)} books).")

    gold_cost_lookup = load_gold_costs(CURRENCY_GOLD_LOOKUP_FILE)
    print(f" [INFO] Loaded {len(gold_cost_lookup)} gold cost entries.")

    # --- 2. Build Rates & Log Them ---
    robust_rates = build_robust_benchmark_rates(market_books, currencies, BENCHMARK_CURRENCY)
    
    # --- [ NEW LOGGING ] ---
    print(f" [INFO] Logging {len(robust_rates)} robust rates to {ROBUST_RATES_LOG_FILE}...")
    ts = datetime.now(timezone.utc).isoformat()
    rates_header = ["timestamp", "scan_id", "currency", "value_in_benchmark", "benchmark_currency"]
    for currency, rate in robust_rates.items():
        if rate > 0: # Only log currencies we could value
            row = [ts, scan_id, currency, rate, BENCHMARK_CURRENCY]
            append_to_csv(ROBUST_RATES_LOG_FILE, rates_header, row)
    # --- [ END NEW LOGGING ] ---

    # --- 3. Find Candidate Paths ---
    print("\n[PHASE 2: FIND CANDIDATE LOOPS (Bellman-Ford)]")
    super_source = "SUPER_SOURCE_NODE"
    currencies_with_source = currencies + [super_source]
    bf_graph = collections.defaultdict(dict, graph)
    for node in currencies:
        bf_graph[super_source][node] = {'weight': 0, 'type': 'start', 'have': super_source, 'want': node}
    all_candidate_paths = find_candidate_paths_with_bellman_ford(bf_graph, currencies_with_source, super_source)
    print(f" [INFO] Found {len(all_candidate_paths)} unique potential arbitrage cycles.")

    # --- 4. Simulate All Paths ---
    print("\n[PHASE 3: SIMULATE & RANK ALL LOOPS]")
    try:
        with open(MY_CURRENCY_FILE, 'r') as f:
            starting_investments = json.load(f)
        print(f" [INFO] Loaded starting investments from {MY_CURRENCY_FILE}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f" [WARN] Could not load {MY_CURRENCY_FILE}. Using 0 for all balances. Error: {e}")
        starting_investments = {} # Fallback to empty
    
    divine_stock = starting_investments.get(BENCHMARK_CURRENCY, 0)
    divines_to_convert = math.floor(divine_stock * .75)
    print(f" [INFO] Using {divines_to_convert:,} {BENCHMARK_CURRENCY} (75% of {divine_stock:,}) as base for pre-trades.")

    ranked_loops = [] # Store all profitable loops for ranking

    if not all_candidate_paths:
        print(" [INFO] No candidate paths to simulate.")
    else:
        for i, path in enumerate(all_candidate_paths):
            start_currency = path[0]['have']
            print("\n" + "-"*60)
            print(f"Simulating Path {i+1}/{len(all_candidate_paths)}: {' -> '.join(d['have'] for d in path)} -> {start_currency}")
            
            existing_start_currency_stock = starting_investments.get(start_currency, 0)
            
            if start_currency == BENCHMARK_CURRENCY:
                initial_investment = existing_start_currency_stock
                print(f" [CALC] Loop starts with benchmark. Using existing stock: {initial_investment:,} {start_currency}")
            else:
                converted_amount = 0
                try:
                    buy_book = market_books[BENCHMARK_CURRENCY][start_currency]['available_trades']
                    if not buy_book:
                        print(f" [SKIP] No 'available_trades' book for {BENCHMARK_CURRENCY}->{start_currency}")
                        continue
                    
                    converted_amount, cost = simulate_buy_step(divines_to_convert, buy_book)
                    print(f" [CALC] Pre-trade sim: {cost:,} {BENCHMARK_CURRENCY} -> {converted_amount:,} {start_currency}")

                except KeyError:
                    print(f" [SKIP] No market book for {BENCHMARK_CURRENCY}->{start_currency}")
                    continue
                
                initial_investment = converted_amount + existing_start_currency_stock
                print(f" [CALC] Total Investment: {converted_amount:,} (converted) + {existing_start_currency_stock:,} (existing) = {initial_investment:,} {start_currency}")

            if initial_investment <= 0:
                print(" [SKIP] Calculated investment is 0.")
                continue

            profit, total_gold_cost, log = simulate_path(path, market_books, initial_investment, gold_cost_lookup)
            
            # Print the detailed log from the simulation
            print("\n".join(log))

            if profit > 0:
                value_per_unit = robust_rates.get(start_currency, 0.0)
                if value_per_unit == 0.0:
                    print(" [WARN] Cannot rank loop. No robust benchmark rate found.")
                    continue
                
                profit_in_benchmark = profit * value_per_unit
                
                if total_gold_cost > 0:
                    efficiency = profit_in_benchmark / total_gold_cost
                    efficiency_per_mil = efficiency * 1_000_000
                    efficiency_str = f"{efficiency_per_mil:,.2f}"
                else:
                    efficiency = float('inf') 
                    efficiency_str = "inf"

                if log: # Update the last log line with efficiency
                    log.pop()
                    new_log_line = f"  Result: {profit:+,} {start_currency} profit (Gold: {total_gold_cost:,.0f}, {efficiency_str} DIV/1M gold)"
                    log.append(new_log_line)
                    print(new_log_line) # Print the updated final line
                
                path_string = ' -> '.join(d['have'] for d in path) + ' -> ' + path[0]['have']
                
                ranked_loops.append({
                    'path': path,
                    'path_string': path_string,
                    'start_currency': start_currency,
                    'investment': initial_investment,
                    'profit': profit,
                    'profit_benchmark': profit_in_benchmark,
                    'gold_cost': total_gold_cost,
                    'efficiency': efficiency_per_mil,
                    'steps': log
                })
        print("-" * 60)

    # --- 5. Report & Save Results ---
    print("\n" + "="*80)
    print("[PHASE 4: FINAL RESULTS & REPORTING]")
    print(f" [INFO] Arbitrage Scan Complete. Found {len(ranked_loops)} verified profitable loops.")
    
    best_loop_data = None
    if ranked_loops:
        ranked_loops.sort(key=lambda x: x['efficiency'], reverse=True)
        best_loop_data = ranked_loops[0]

        print("\n" + "!"*30 + " BEST LOOP FOUND " + "!"*30)
        print(f"  Path:         {best_loop_data['path_string']}")
        print(f"  Investment:   {best_loop_data['investment']:,} {best_loop_data['start_currency']}")
        print(f"  Raw Profit:   {best_loop_data['profit']:+,} {best_loop_data['start_currency']}")
        print(f"  Gold Cost:    {best_loop_data['gold_cost']:,.0f}")
        print(f"  Profit (DIV): {best_loop_data['profit_benchmark']:,.4f} {BENCHMARK_CURRENCY}")
        print(f"  Efficiency:   {best_loop_data['efficiency']:,.2f} (Div/M)")
        print("!"*80 + "\n")

        # --- [ NEW LOGGING ] ---
        print(f" [INFO] Logging best loop to {OPPORTUNITY_LOG_FILE}...")
        log_header = [
            "timestamp", "scan_id", "path_string", "start_currency", 
            "investment", "profit", "profit_benchmark", "gold_cost", "efficiency"
        ]
        log_row = [
            ts, scan_id, best_loop_data['path_string'], best_loop_data['start_currency'],
            best_loop_data['investment'], best_loop_data['profit'],
            best_loop_data['profit_benchmark'], best_loop_data['gold_cost'],
            best_loop_data['efficiency']
        ]
        append_to_csv(OPPORTUNITY_LOG_FILE, log_header, log_row)
        # --- [ END NEW LOGGING ] ---

    else:
        print("\n" + "-"*30 + " NO PROFITABLE LOOPS FOUND " + "-"*30 + "\n")

    alert_data = {
        "scan_id": scan_id,
        "timestamp": ts,
        "profitable": bool(best_loop_data),
        "best_loop": best_loop_data
    }

    try:
        with open(ARBITRAGE_ALERT_FILE, 'w') as f:
            json.dump(alert_data, f, indent=4)
        print(f" [INFO] Successfully wrote alert data to {ARBITRAGE_ALERT_FILE}")
    except IOError as e:
        print(f" [CRITICAL] Failed to write alert data to {ARBITRAGE_ALERT_FILE}: {e}")
    except Exception as e:
         print(f" [CRITICAL] Unexpected error writing alert data: {e}")
    
    print("\n" + "="*80)
    print(f"--- ANALYSIS COMPLETE FOR SCAN ID: {scan_id} ---")
    print("="*80 + "\n")


# --- Main Watcher Loop ---
def main():
    """Main watcher loop."""
    print("="*80)
    print("--- Arbitrage Watcher Service STARTED ---")
    print(f"--- {datetime.now().isoformat()} ---")
    print(f"Monitoring {OCR_COMPLETE_FILE} for new completed scans...")
    print(f"Checking every {POLL_INTERVAL_SECONDS} seconds. Press CTRL+C to stop.")
    print("="*80)

    while True:
        try:
            my_last_scan = get_last_processed_scan()
            latest_complete_scan = get_latest_complete_scan()

            if latest_complete_scan > my_last_scan:
                print(f"\n[WATCHER] New complete scan detected: {latest_complete_scan} (last processed: {my_last_scan})")
                run_analysis(latest_complete_scan)
                set_last_processed_scan(latest_complete_scan)
                print(f"[WATCHER] Analysis complete. Waiting for next scan (>{latest_complete_scan})...")

            time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n[WATCHER] Shutdown signal received. Stopping service...")
            break
        except Exception as e:
            print(f"\n" + "!"*80)
            print(f" [FATAL ERROR] An unexpected error occurred in the watcher loop: {e}")
            print(f" Error Type: {type(e)}")
            import traceback
            traceback.print_exc()
            print("!"*80)
            print("[WATCHER] Restarting watcher in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    main()
import subprocess
import sys
import time
import os

# Define your scripts with a clear name-to-file mapping
# We can add more tasks here in the future.
SCRIPTS = {
    "fetch_currency": os.path.join("currency_fetcher", "dataGet.py"),
}

def run_script(script_path):
    """Runs a single python script using subprocess."""
    if os.path.exists(script_path):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Running {script_path}...")
        try:
            subprocess.run(['python', script_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running {script_path}: {e}")
        except FileNotFoundError:
            print(f"Error: 'python' command not found. Make sure Python is installed and in your PATH.")
    else:
        print(f"Script '{script_path}' not found.")

def main_loop(tasks_to_run, sleep_interval=300):
    """Main loop to run specified tasks periodically."""
    while True:
        for task_key in tasks_to_run:
            script_file = SCRIPTS.get(task_key)
            if script_file:
                run_script(script_file)
            else:
                print(f"Task key '{task_key}' not recognized in SCRIPTS dictionary.")
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] All tasks complete. Sleeping for {sleep_interval} seconds...")
        time.sleep(sleep_interval)


if __name__ == "__main__":
    # By default, we will run the 'fetch_currency' task.
    # You can specify other tasks as command-line arguments in the future.
    tasks = sys.argv[1:] if len(sys.argv) > 1 else ["fetch_currency"]
    
    # Define sleep time in seconds (e.g., 60 seconds * 5 minutes)
    interval = 60 * 5 

    try:
        main_loop(tasks, sleep_interval=interval)
    except KeyboardInterrupt:
        print("\nScheduler stopped by user.")
        sys.exit(0)
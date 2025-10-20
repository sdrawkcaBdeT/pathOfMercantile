import subprocess
import time
import sys
import os
from datetime import datetime

# --- Configuration ---
# Map simple keywords to the scripts they should run.
# This now includes your 'syncMeta.py' script.
SCRIPTS = {
    "sync": ["syncMeta.py"],
    "fetch": ["dataGet.py"],
    # This 'pipeline' command runs the whole process in the correct order.
    "pipeline": ["syncMeta.py", "dataGet.py"],
}

def run_scripts(script_paths):
    """Executes a list of scripts in sequence."""
    for script_path in script_paths:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running {os.path.basename(script_path)}...")
        try:
            # We use sys.executable to ensure we're using the Python from the active virtual environment.
            # check=True ensures that if a script fails, the whole process stops.
            subprocess.run([sys.executable, script_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running {script_path}. Halting this cycle.")
            print(e)
            return False
    return True

if __name__ == "__main__":
    # The first command line argument determines which task to run.
    # It defaults to 'pipeline' if no argument is given.
    task = sys.argv[1] if len(sys.argv) > 1 else "pipeline"
    
    if task not in SCRIPTS:
        print(f"Error: Task '{task}' not recognized.")
        print(f"Available tasks are: {', '.join(SCRIPTS.keys())}")
        sys.exit(1)

    # --- Main Loop ---
    # This loop will now run the chosen task sequence every 5 minutes.
    while True:
        print("-" * 50)
        print(f"Starting task sequence: '{task}'")
        
        success = run_scripts(SCRIPTS[task])
        
        if success:
            print(f"Task sequence '{task}' completed. Sleeping for 300 seconds...")
        else:
            print("Task sequence failed. Will retry in 300 seconds...")
            
        time.sleep(300)
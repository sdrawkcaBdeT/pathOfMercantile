import random
import time

def random_float(start, end):
    """Generates a random float within a given range."""
    return random.uniform(start, end)

def random_int(start, end):
    """Generates a random integer within a given range."""
    return random.randint(start, end)

def human_like_delay(min_seconds=0.5, max_seconds=1.5):
    """Pauses execution for a random duration to mimic human behavior."""
    time.sleep(random_float(min_seconds, max_seconds))

def get_mouse_speed():
    """Returns a random duration for mouse movements."""
    return random_float(0.15, 0.4)

def get_typing_interval():
    """Returns a random interval for typing."""
    return random_float(0.02, 0.08)
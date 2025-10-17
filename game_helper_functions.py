import random
import time
import numpy as np

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
    return random_float(0.03, 0.09)

def gaussian_random_point_in_rect(rect_x, rect_y, rect_width, rect_height):
    """Generates a human-like random point within a rectangle."""
    center_x = rect_x + rect_width / 2
    center_y = rect_y + rect_height / 2
    std_dev_x = rect_width / 6
    std_dev_y = rect_height / 6
    rand_x = np.random.normal(loc=center_x, scale=std_dev_x)
    rand_y = np.random.normal(loc=center_y, scale=std_dev_y)
    final_x = int(np.clip(rand_x, rect_x, rect_x + rect_width - 1))
    final_y = int(np.clip(rand_y, rect_y, rect_y + rect_height - 1))
    return final_x, final_y

def secs_between_keys():
    """Generates a faster, more specific typing interval."""
    return random_float(0.0127, 0.0627)

class ActionFailedException(Exception):
    """Custom exception to signal a non-recoverable failure in a GUI action."""
    pass

def retry_action(func, retries=3, delay=0.5, **kwargs):
    """
    Attempts to execute a function multiple times, raising an exception on failure.

    Args:
        func (callable): The function to execute.
        retries (int): The maximum number of attempts.
        delay (float): The time in seconds to wait between retries.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the successful function call.

    Raises:
        ActionFailedException: If the function fails after all retries.
    """
    for attempt in range(retries):
        try:
            result = func(**kwargs)
            if result: # Assumes the function returns a non-False/non-None value on success
                return result
            print(f"  [WARN] Attempt {attempt + 1}/{retries} failed for '{func.__name__}'. Retrying...")
        except Exception as e:
            print(f"  [WARN] Attempt {attempt + 1}/{retries} for '{func.__name__}' raised an exception: {e}. Retrying...")

        time.sleep(delay)

    raise ActionFailedException(f"Action '{func.__name__}' failed after {retries} attempts.")
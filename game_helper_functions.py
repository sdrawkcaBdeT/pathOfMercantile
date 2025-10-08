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
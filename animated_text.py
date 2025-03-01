#!/usr/bin/env python3
import time
import random
import os

def clear_terminal():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def animated_text(text, animation_chars=None, speed=0.1):
    """Displays text with a character animation effect."""
    if animation_chars is None:
        animation_chars = ['-', '\\', '|', '/']  # Default animation characters

    while True:
        for char in animation_chars:
            clear_terminal()
            print(f"{text} {char}")
            time.sleep(speed)

if __name__ == "__main__":
    try:
        animated_text("Loading...", animation_chars=['.', 'o', 'O', '@', '*'], speed=0.2) #Example Usage
    except KeyboardInterrupt:
        print("\nAnimation stopped.")

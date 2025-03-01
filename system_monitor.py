#!/usr/bin/env python3

import psutil
import time
import datetime

# Configuration
LOG_FILE = "/var/log/system_monitor.log"
MONITOR_INTERVAL = 60  # seconds

def get_system_stats():
    """Collects system statistics."""
    cpu_percent = psutil.cpu_percent(interval=1)  # Get CPU usage over 1 second
    memory_usage = psutil.virtual_memory()
    disk_usage = psutil.disk_usage("/") # Get disk usage for the root partition

    stats = {
        "timestamp": datetime.datetime.now().isoformat(),
        "cpu_percent": cpu_percent,
        "memory_percent": memory_usage.percent,
        "disk_percent": disk_usage.percent,
        "disk_free": disk_usage.free, # in bytes
        "disk_total": disk_usage.total, # in bytes
    }
    return stats

def log_stats(stats):
    """Logs the system statistics to a file."""
    try:
        with open(LOG_FILE, "a") as f:
            log_entry = f"{stats['timestamp']} - CPU: {stats['cpu_percent']}%, Memory: {stats['memory_percent']}%, Disk: {stats['disk_percent']}% (Free: {stats['disk_free']} bytes, Total: {stats['disk_total']} bytes)\n"
            f.write(log_entry)
    except Exception as e:
        print(f"Error logging data: {e}")

def main():
    """Main function to continuously monitor and log system stats."""
    print(f"Monitoring system resources and logging to {LOG_FILE}. Press Ctrl+C to stop.")
    try:
        while True:
            stats = get_system_stats()
            log_stats(stats)
            time.sleep(MONITOR_INTERVAL)
    except KeyboardInterrupt:
        print("Monitoring stopped.")

if __name__ == "__main__":
    main()

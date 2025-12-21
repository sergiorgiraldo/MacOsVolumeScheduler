#!/usr/bin/env python3
"""
macOS Volume Scheduler
A background app that automatically adjusts system volume based on day and hour
"""

import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
import time
import signal
import sys
import logging

# Configuration file path
CONFIG_DIR = Path.home() / ".volume_scheduler"
CONFIG_FILE = CONFIG_DIR / "schedule.json"
PID_FILE = CONFIG_DIR / "scheduler.pid"
LOG_FILE = CONFIG_DIR / "scheduler.log"

def setup_logging():
    """Setup logging to file"""
    CONFIG_DIR.mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()
class VolumeScheduler:
    def __init__(self):
        self.schedule = self.load_schedule()
        self.running = True
        self.last_hour = None
        
        # Setup signal handlers for clean shutdown
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
    
    def handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal")
        self.running = False
        
    def load_schedule(self):
        """Load schedule from config file"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        else:
            # Create default schedule
            schedule = {}
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            for day in days:
                schedule[day] = {}
                for hour in range(24):
                    # Default: 30% volume at night (22-6), 70% during day
                    if hour >= 22 or hour < 6:
                        schedule[day][str(hour)] = 30
                    else:
                        schedule[day][str(hour)] = 70
            self.save_schedule(schedule)
            return schedule
    
    def save_schedule(self, schedule):
        """Save schedule to config file"""
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(schedule, f, indent=2)
    
    def set_volume(self, level):
        """Set macOS system volume (0-100)"""
        try:
            # AppleScript command to set volume
            script = f"set volume output volume {level}"
            subprocess.run(["osascript", "-e", script], check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    def get_current_schedule(self):
        """Get the volume level for current day and hour"""
        now = datetime.now()
        day_name = now.strftime("%A")
        hour = str(now.hour)
        
        if day_name in self.schedule and hour in self.schedule[day_name]:
            return self.schedule[day_name][hour]
        return None
    
    def check_and_update_volume(self):
        """Check if volume needs to be updated"""
        now = datetime.now()
        current_hour = now.hour
        
        # Only update at the start of a new hour
        if current_hour != self.last_hour:
            volume = self.get_current_schedule()
            if volume is not None:
                if self.set_volume(volume):
                    # Only log volume changes, not every check
                    self.last_hour = current_hour
    
    def run(self):
        """Main loop - runs in background"""
        logger.info("Volume Scheduler started")
        
        # Write PID file
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
        
        try:
            # Set initial volume
            self.check_and_update_volume()
            
            while self.running:
                self.check_and_update_volume()
                time.sleep(300)  # Check every 5 minutes
                
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            logger.info("Volume Scheduler stopped")
            # Clean up PID file
            try:
                if PID_FILE.exists():
                    PID_FILE.unlink()
            except Exception:
                pass
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False


def edit_schedule():
    """Interactive schedule editor"""
    scheduler = VolumeScheduler()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    print("\n=== Volume Scheduler Configuration ===\n")
    print("Choose an option:")
    print("1. View current schedule")
    print("2. Edit schedule for a specific day")
    print("3. Set all hours for a day")
    print("4. Copy schedule from one day to another")
    print("5. Reset to defaults")
    print("6. Exit")
    
    choice = input("\nEnter choice (1-6): ").strip()
    
    if choice == "1":
        # View schedule
        for day in days:
            print(f"\n{day}:")
            for hour in range(24):
                vol = scheduler.schedule[day][str(hour)]
                print(f"  {hour:02d}:00 - {vol}%", end="")
                if (hour + 1) % 4 == 0:
                    print()
            print()
    
    elif choice == "2":
        # Edit specific day
        print("\nDays:")
        for i, day in enumerate(days, 1):
            print(f"{i}. {day}")
        day_choice = int(input("Select day (1-7): ")) - 1
        day = days[day_choice]
        
        print(f"\nEditing {day}:")
        hour = int(input("Enter hour (0-23): "))
        volume = int(input("Enter volume level (0-100): "))
        
        scheduler.schedule[day][str(hour)] = volume
        scheduler.save_schedule(scheduler.schedule)
        print(f"Set {day} at {hour}:00 to {volume}%")
    
    elif choice == "3":
        # Set all hours
        print("\nDays:")
        for i, day in enumerate(days, 1):
            print(f"{i}. {day}")
        day_choice = int(input("Select day (1-7): ")) - 1
        day = days[day_choice]
        volume = int(input("Enter volume level for all hours (0-100): "))
        
        for hour in range(24):
            scheduler.schedule[day][str(hour)] = volume
        scheduler.save_schedule(scheduler.schedule)
        print(f"Set all hours for {day} to {volume}%")
    
    elif choice == "4":
        # Copy day
        print("\nCopy from:")
        for i, day in enumerate(days, 1):
            print(f"{i}. {day}")
        from_day = days[int(input("Select source day (1-7): ")) - 1]
        to_day = days[int(input("Select destination day (1-7): ")) - 1]
        
        scheduler.schedule[to_day] = scheduler.schedule[from_day].copy()
        scheduler.save_schedule(scheduler.schedule)
        print(f"Copied schedule from {from_day} to {to_day}")
    
    elif choice == "5":
        # Reset
        if input("Reset to defaults? (yes/no): ").lower() == "yes":
            CONFIG_FILE.unlink(missing_ok=True)
            print("Schedule reset to defaults")


def stop_scheduler():
    """Stop running scheduler"""
    if PID_FILE.exists():
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait for process to clean up
            for _ in range(10):
                time.sleep(0.2)
                try:
                    os.kill(pid, 0)  # Check if process still exists
                except ProcessLookupError:
                    break
            
            # Force remove PID file if it still exists
            if PID_FILE.exists():
                PID_FILE.unlink()
            
            logger.info("Scheduler stopped")
        except ProcessLookupError:
            logger.error("Scheduler not running")
            if PID_FILE.exists():
                PID_FILE.unlink()
    else:
        logger.error("Scheduler not running")

def daemonize():
    """Run the process as a daemon in the background"""
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process, exit
            sys.exit(0)
    except OSError as e:
        print(f"Fork failed: {e}")
        sys.exit(1)
    
    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)
    
    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logger.error(f"Fork failed: {e}")
        sys.exit(1)
    
def is_process_running(pid):
    """Check if a process with given PID is running."""
    try:
        # Send signal 0 - doesn't actually send a signal, just checks if process exists
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        # Process doesn't exist
        return False
    except PermissionError:
        # Process exists but we don't have permission to signal it
        return True
    except Exception:
        return False
    
def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "start":
            if PID_FILE.exists():
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                if is_process_running(pid):
                    return
            
            logger.info("Starting Volume Scheduler in background...")
            logger.info(f"Logs: {CONFIG_DIR / 'scheduler.log'}")
            
            # Fork to background
            daemonize()
            
            # Now running as daemon
            scheduler = VolumeScheduler()
            scheduler.run()
        
        elif command == "stop":
            stop_scheduler()
        
        elif command == "edit":
            edit_schedule()
        
        elif command == "status":
            if PID_FILE.exists():
                with open(PID_FILE, "r") as f:
                    pid = f.read().strip()
                print(f"Scheduler is running (PID: {pid})")
            else:
                print("Scheduler is not running")
        
        else:
            print("Unknown command")
            print("Usage: volume_scheduler.py [start|stop|edit|status]")
    
    else:
        print("macOS Volume Scheduler")
        print("\nUsage:")
        print("  volume_scheduler.py start   - Start the scheduler")
        print("  volume_scheduler.py stop    - Stop the scheduler")
        print("  volume_scheduler.py edit    - Edit schedule")
        print("  volume_scheduler.py status  - Check if running")


if __name__ == "__main__":
    main()
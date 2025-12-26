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
MENU_PID_FILE = CONFIG_DIR / "menu.pid"
LOG_FILE = CONFIG_DIR / "scheduler.log"
HTML_FILE = Path(__file__).parent / "volume_scheduler_ui.html"
MENU_SCRIPT = Path(__file__).parent / "volume_scheduler_menu.py"

"""
Setup logging to file
"""
def setup_logging():
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

"""
Main class for scheduler
"""
class VolumeScheduler:
    def __init__(self):
        self.schedule = self.load_schedule()
        self.running = True
        self.last_hour = None

        # Setup signal handlers for clean shutdown
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

    """
    Handle shutdown signals
    """
    def handle_signal(self, signum, frame):
        logger.info("Received shutdown signal")
        self.running = False

    """
    Load schedule from config file
    """
    def load_schedule(self):
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        else:
            # Create default schedule
            schedule = {}
            days = ["Monday", "Tuesday", "Wednesday",
                    "Thursday", "Friday", "Saturday", "Sunday"]
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

    """
    Save schedule to config file
    """
    def save_schedule(self, schedule):
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(schedule, f, indent=2)

    """
    Set macOS system volume (0-100)
    """
    def set_volume(self, level):
        try:
            # AppleScript command to set volume
            script = f"set volume output volume {level}"
            subprocess.run(["osascript", "-e", script], check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error setting volume: {e}")
            return False

    """
    Get the volume level for current day and hour
    """
    def get_current_schedule(self):
        now = datetime.now()
        day_name = now.strftime("%A")
        hour = str(now.hour)

        if day_name in self.schedule and hour in self.schedule[day_name]:
            return self.schedule[day_name][hour]
        return None

    """
    Check if volume needs to be updated
    """
    def check_and_update_volume(self):
        now = datetime.now()
        current_hour = now.hour

        # Only update at the start of a new hour
        if current_hour != self.last_hour:
            volume = self.get_current_schedule()
            if volume is not None:
                if self.set_volume(volume):
                    # Only log volume changes, not every check
                    self.last_hour = current_hour

    """
    Main loop - runs in background
    """
    def run(self):
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

    """Stop the scheduler"""
    def stop(self):
        self.running = False


"""
Start the menu bar application
"""
def start_menu_bar_app():
    if not MENU_SCRIPT.exists():
        logger.warning(f"Menu bar script not found at {MENU_SCRIPT}")
        return False

    try:
        # Start the menu bar app as a separate process
        process = subprocess.Popen(
            [sys.executable, str(MENU_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Give it a moment to start
        time.sleep(1)

        # Check if it's still running
        if process.poll() is None:
            # Save the PID
            with open(MENU_PID_FILE, "w") as f:
                f.write(str(process.pid))
            logger.info(f"Menu bar app started (PID: {process.pid})")
            return True
        else:
            logger.error("Menu bar app failed to start")
            return False
    except Exception as e:
        logger.error(f"Error starting menu bar app: {e}")
        return False


"""
Stop the menu bar application
"""
def stop_menu_bar_app():
    if MENU_PID_FILE.exists():
        try:
            with open(MENU_PID_FILE, "r") as f:
                pid = int(f.read().strip())

            os.kill(pid, signal.SIGTERM)
            logger.info("Menu bar app stopped")

            # Wait a bit for it to clean up
            time.sleep(0.5)

            # Clean up PID file
            if MENU_PID_FILE.exists():
                MENU_PID_FILE.unlink()

        except ProcessLookupError:
            logger.warning("Menu bar app not running")
            if MENU_PID_FILE.exists():
                MENU_PID_FILE.unlink()
        except Exception as e:
            logger.error(f"Error stopping menu bar app: {e}")


"""
Interactive schedule editor
"""
def edit_schedule():
    scheduler = VolumeScheduler()
    days = ["Monday", "Tuesday", "Wednesday",
            "Thursday", "Friday", "Saturday", "Sunday"]

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


"""
Stop running scheduler
"""
def stop_scheduler():
    # Stop the menu bar app first
    stop_menu_bar_app()

    # Then stop the scheduler
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


"""
Run the process as a daemon in the background
"""
def daemonize():
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


"""
Check if a process with given PID is running.
"""
def is_process_running(pid):
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


"""
Entry method
"""
def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "start":
            if PID_FILE.exists():
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                if is_process_running(pid):
                    print(f"Scheduler already running (PID: {pid})")
                    return

            logger.info("Starting Volume Scheduler in background...")
            logger.info(f"Logs: {CONFIG_DIR / 'scheduler.log'}")

            # Start the menu bar app first (before daemonizing)
            if MENU_SCRIPT.exists():
                logger.info("Starting menu bar app...")
                start_menu_bar_app()

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
            scheduler_running = False
            menu_running = False

            if PID_FILE.exists():
                with open(PID_FILE, "r") as f:
                    pid = f.read().strip()
                print(f"Scheduler is running (PID: {pid})")
                scheduler_running = True
            else:
                print("Scheduler is not running")

            if MENU_PID_FILE.exists():
                with open(MENU_PID_FILE, "r") as f:
                    pid = f.read().strip()
                print(f"Menu bar app is running (PID: {pid})")
                menu_running = True
            else:
                print("Menu bar app is not running")

            if not scheduler_running and not menu_running:
                print("\nNo components are running")

        else:
            print("Unknown command")
            print("Usage: volume_scheduler.py [start|stop|edit|status]")

    else:
        print("macOS Volume Scheduler")
        print("\nUsage:")
        print("  volume_scheduler.py start   - Start the scheduler and menu bar app")
        print("  volume_scheduler.py stop    - Stop the scheduler and menu bar app")
        print("  volume_scheduler.py edit    - Edit schedule (CLI)")
        print("  volume_scheduler.py status  - Check if running")


if __name__ == "__main__":
    main()

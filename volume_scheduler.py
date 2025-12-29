#!/usr/bin/env python3
"""
macOS Volume Scheduler
A background app that automatically adjusts system volume based on day and hour
Now with multiple profile support
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
MENU_SCRIPT = Path(__file__).parent / "volume_scheduler_menu.py"

"""
Setup logging to file
"""


def SetupLogging():
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


logger = SetupLogging()

"""
Main class for scheduler
"""


class VolumeScheduler:
    def __init__(self):
        self.config = self.LoadConfig()
        self.running = True
        self.last_hour = None

        # Setup signal handlers for clean shutdown
        signal.signal(signal.SIGTERM, self.HandleSignal)
        signal.signal(signal.SIGINT, self.HandleSignal)

    """
    Handle shutdown signals
    """

    def HandleSignal(self, signum, frame):
        logger.info("Received shutdown signal")
        self.running = False

    """
    Create default schedule for a profile
    """

    def CreateDefaultSchedule(self):
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
        return schedule

    """
    Load config with profiles from config file
    """

    def LoadConfig(self):
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                
                # Migrate old format to new format if needed
                if "profiles" not in config:
                    logger.info("Migrating old config format to profiles")
                    old_schedule = config
                    config = {
                        "profiles": {
                            "Default": {
                                "name": "Default",
                                "isActive": True,
                                "schedule": old_schedule
                            }
                        }
                    }
                    self.SaveConfig(config)
                
                return config
        else:
            # Create default config with one profile
            config = {
                "profiles": {
                    "Default": {
                        "name": "Default",
                        "isActive": True,
                        "schedule": self.CreateDefaultSchedule()
                    }
                }
            }
            self.SaveConfig(config)
            return config

    """
    Save config to file
    """

    def SaveConfig(self, config):
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

    """
    Get the active profile
    """

    def GetActiveProfile(self):
        for profile_name, profile_data in self.config["profiles"].items():
            if profile_data.get("isActive", False):
                return profile_name, profile_data
        
        # If no active profile, activate the first one
        first_profile = next(iter(self.config["profiles"].items()))
        first_profile[1]["isActive"] = True
        self.SaveConfig(self.config)
        return first_profile

    """
    Set a profile as active
    """

    def SetActiveProfile(self, profile_name):
        if profile_name not in self.config["profiles"]:
            logger.error(f"Profile '{profile_name}' not found")
            return False
        
        # Deactivate all profiles
        for name, data in self.config["profiles"].items():
            data["isActive"] = False
        
        # Activate the selected profile
        self.config["profiles"][profile_name]["isActive"] = True
        self.SaveConfig(self.config)
        logger.info(f"Switched to profile: {profile_name}")
        return True

    """
    Set macOS system volume (0-100)
    """

    def SetVolume(self, level):
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

    def GetCurrentSchedule(self):
        now = datetime.now()
        day_name = now.strftime("%A")
        hour = str(now.hour)

        profile_name, profile_data = self.GetActiveProfile()
        schedule = profile_data["schedule"]

        if day_name in schedule and hour in schedule[day_name]:
            return schedule[day_name][hour]
        return None

    """
    Check if volume needs to be updated
    """

    def CheckAndUpdateVolume(self):
        now = datetime.now()
        current_hour = now.hour

        # Only update at the start of a new hour
        if current_hour != self.last_hour:
            volume = self.GetCurrentSchedule()
            if volume is not None:
                if self.SetVolume(volume):
                    # Only log volume changes, not every check
                    self.last_hour = current_hour

    """
    Main loop - runs in background
    """

    def Run(self):
        logger.info("Volume Scheduler started")

        # Write PID file
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        try:
            # Set initial volume
            self.CheckAndUpdateVolume()

            while self.running:
                self.CheckAndUpdateVolume()
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

    def Stop(self):
        self.running = False


"""
Start the menu bar application
"""


def StartMenubarApp():
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


def StopMenubarApp():
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


def EditSchedule():
    scheduler = VolumeScheduler()
    days = ["Sunday", "Monday", "Tuesday", "Wednesday",
            "Thursday", "Friday", "Saturday"]

    # Select profile to edit
    print("\n=== Available Profiles ===")
    profiles = list(scheduler.config["profiles"].keys())
    for i, profile_name in enumerate(profiles, 1):
        active = " (ACTIVE)" if scheduler.config["profiles"][profile_name].get("isActive", False) else ""
        print(f"{i}. {profile_name}{active}")
    
    try:
        profile_choice = int(input("\nSelect profile to edit (1-{}): ".format(len(profiles)))) - 1
        if profile_choice < 0 or profile_choice >= len(profiles):
            print("Invalid selection")
            return
        
        selected_profile = profiles[profile_choice]
        profile_data = scheduler.config["profiles"][selected_profile]
        schedule = profile_data["schedule"]
    except (ValueError, IndexError):
        print("Invalid selection")
        return

    print(f"\n=== Editing Profile: {selected_profile} ===\n")
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
                vol = schedule[day][str(hour)]
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

        schedule[day][str(hour)] = volume
        scheduler.SaveConfig(scheduler.config)
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
            schedule[day][str(hour)] = volume
        scheduler.SaveConfig(scheduler.config)
        print(f"Set all hours for {day} to {volume}%")

    elif choice == "4":
        # Copy day
        print("\nCopy from:")
        for i, day in enumerate(days, 1):
            print(f"{i}. {day}")
        from_day = days[int(input("Select source day (1-7): ")) - 1]
        to_day = days[int(input("Select destination day (1-7): ")) - 1]

        schedule[to_day] = schedule[from_day].copy()
        scheduler.SaveConfig(scheduler.config)
        print(f"Copied schedule from {from_day} to {to_day}")

    elif choice == "5":
        # Reset
        if input("Reset to defaults? (yes/no): ").lower() == "yes":
            profile_data["schedule"] = scheduler.CreateDefaultSchedule()
            scheduler.SaveConfig(scheduler.config)
            print("Schedule reset to defaults")


"""
Manage profiles
"""


def ManageProfiles(profile_name=None):
    scheduler = VolumeScheduler()
    
    if profile_name:
        # Switch to specified profile
        if scheduler.SetActiveProfile(profile_name):
            print(f"Switched to profile: {profile_name}")
            
            # Signal the scheduler to reload if it's running
            if PID_FILE.exists():
                try:
                    with open(PID_FILE, "r") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, signal.SIGHUP)
                except:
                    pass
        else:
            print(f"Error: Profile '{profile_name}' not found")
            print("\nAvailable profiles:")
            for name in scheduler.config["profiles"].keys():
                active = " (ACTIVE)" if scheduler.config["profiles"][name].get("isActive", False) else ""
                print(f"  - {name}{active}")
    else:
        # Interactive profile management
        print("\n=== Profile Management ===\n")
        print("1. List all profiles")
        print("2. Switch active profile")
        print("3. Create new profile")
        print("4. Delete profile")
        print("5. Rename profile")
        print("6. Exit")
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == "1":
            # List profiles
            print("\nProfiles:")
            for name, data in scheduler.config["profiles"].items():
                active = " (ACTIVE)" if data.get("isActive", False) else ""
                print(f"  - {name}{active}")
        
        elif choice == "2":
            # Switch profile
            profiles = list(scheduler.config["profiles"].keys())
            print("\nAvailable profiles:")
            for i, name in enumerate(profiles, 1):
                active = " (ACTIVE)" if scheduler.config["profiles"][name].get("isActive", False) else ""
                print(f"{i}. {name}{active}")
            
            try:
                profile_choice = int(input("\nSelect profile (1-{}): ".format(len(profiles)))) - 1
                selected_profile = profiles[profile_choice]
                scheduler.SetActiveProfile(selected_profile)
                print(f"Switched to profile: {selected_profile}")
            except (ValueError, IndexError):
                print("Invalid selection")
        
        elif choice == "3":
            # Create new profile
            new_name = input("\nEnter new profile name: ").strip()
            if new_name in scheduler.config["profiles"]:
                print(f"Profile '{new_name}' already exists")
            elif new_name:
                scheduler.config["profiles"][new_name] = {
                    "name": new_name,
                    "isActive": False,
                    "schedule": scheduler.CreateDefaultSchedule()
                }
                scheduler.SaveConfig(scheduler.config)
                print(f"Created profile: {new_name}")
            else:
                print("Invalid profile name")
        
        elif choice == "4":
            # Delete profile
            if len(scheduler.config["profiles"]) == 1:
                print("Cannot delete the last profile")
                return
            
            profiles = list(scheduler.config["profiles"].keys())
            print("\nProfiles:")
            for i, name in enumerate(profiles, 1):
                active = " (ACTIVE)" if scheduler.config["profiles"][name].get("isActive", False) else ""
                print(f"{i}. {name}{active}")
            
            try:
                profile_choice = int(input("\nSelect profile to delete (1-{}): ".format(len(profiles)))) - 1
                selected_profile = profiles[profile_choice]
                
                if input(f"Delete profile '{selected_profile}'? (yes/no): ").lower() == "yes":
                    was_active = scheduler.config["profiles"][selected_profile].get("isActive", False)
                    del scheduler.config["profiles"][selected_profile]
                    
                    # If we deleted the active profile, activate another one
                    if was_active:
                        first_profile = next(iter(scheduler.config["profiles"].keys()))
                        scheduler.config["profiles"][first_profile]["isActive"] = True
                    
                    scheduler.SaveConfig(scheduler.config)
                    print(f"Deleted profile: {selected_profile}")
            except (ValueError, IndexError):
                print("Invalid selection")
        
        elif choice == "5":
            # Rename profile
            profiles = list(scheduler.config["profiles"].keys())
            print("\nProfiles:")
            for i, name in enumerate(profiles, 1):
                print(f"{i}. {name}")
            
            try:
                profile_choice = int(input("\nSelect profile to rename (1-{}): ".format(len(profiles)))) - 1
                old_name = profiles[profile_choice]
                new_name = input(f"Enter new name for '{old_name}': ").strip()
                
                if new_name and new_name not in scheduler.config["profiles"]:
                    profile_data = scheduler.config["profiles"][old_name]
                    profile_data["name"] = new_name
                    scheduler.config["profiles"][new_name] = profile_data
                    del scheduler.config["profiles"][old_name]
                    scheduler.SaveConfig(scheduler.config)
                    print(f"Renamed profile from '{old_name}' to '{new_name}'")
                else:
                    print("Invalid name or profile already exists")
            except (ValueError, IndexError):
                print("Invalid selection")


"""
Stop running scheduler
"""


def StopScheduler():
    # Stop the menu bar app first
    StopMenubarApp()

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


def Daemonize():
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


def IsProcessRunning(pid):
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
                if IsProcessRunning(pid):
                    print(f"Scheduler already running (PID: {pid})")
                    return

            logger.info("Starting Volume Scheduler in background...")
            logger.info(f"Logs: {CONFIG_DIR / 'scheduler.log'}")

            # Start the menu bar app first (before daemonizing)
            if MENU_SCRIPT.exists():
                logger.info("Starting menu bar app...")
                StartMenubarApp()

            # Fork to background
            Daemonize()

            # Now running as daemon
            scheduler = VolumeScheduler()
            scheduler.Run()

        elif command == "stop":
            StopScheduler()

        elif command == "edit":
            EditSchedule()

        elif command == "profile":
            # Check if profile name was provided
            if len(sys.argv) > 2:
                ManageProfiles(sys.argv[2])
            else:
                ManageProfiles()

        elif command == "status":
            scheduler_running = False
            menu_running = False

            if PID_FILE.exists():
                with open(PID_FILE, "r") as f:
                    pid = f.read().strip()
                print(f"Scheduler is running (PID: {pid})")
                scheduler_running = True
                
                # Show active profile
                try:
                    scheduler = VolumeScheduler()
                    profile_name, _ = scheduler.GetActiveProfile()
                    print(f"Active profile: {profile_name}")
                except:
                    pass
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
            print("Usage: volume_scheduler.py [start|stop|edit|profile|status]")

    else:
        print("macOS Volume Scheduler")
        print("\nUsage:")
        print("  volume_scheduler.py start              - Start the scheduler and menu bar app")
        print("  volume_scheduler.py stop               - Stop the scheduler and menu bar app")
        print("  volume_scheduler.py edit               - Edit schedule (CLI)")
        print("  volume_scheduler.py profile            - Manage profiles (interactive)")
        print("  volume_scheduler.py profile <name>     - Switch to specific profile")
        print("  volume_scheduler.py status             - Check if running")


if __name__ == "__main__":
    main()

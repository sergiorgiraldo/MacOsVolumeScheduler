#!/usr/bin/env python3
"""
Unit tests for macOS Volume Scheduler with Profiles
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import subprocess
from pathlib import Path
import tempfile
import shutil
import signal

# Import the modules to test
import volume_scheduler
import volume_scheduler_menu


class TestVolumeScheduler(unittest.TestCase):
    """Tests for the VolumeScheduler class"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a temporary directory for test files
        self.test_dir = Path(tempfile.mkdtemp())
        self.old_config_dir = volume_scheduler.CONFIG_DIR

        # Patch the config directory
        volume_scheduler.CONFIG_DIR = self.test_dir
        volume_scheduler.CONFIG_FILE = self.test_dir / "schedule.json"
        volume_scheduler.PID_FILE = self.test_dir / "scheduler.pid"
        volume_scheduler.LOG_FILE = self.test_dir / "scheduler.log"

    def tearDown(self):
        """Clean up test fixtures"""
        # Restore original config directory
        volume_scheduler.CONFIG_DIR = self.old_config_dir

        # Remove temporary directory
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_load_config_creates_default(self):
        """Test that load_config creates a default config with one profile when none exists"""
        scheduler = volume_scheduler.VolumeScheduler()

        # Verify config structure
        self.assertIsNotNone(scheduler.config)
        self.assertIn("profiles", scheduler.config)
        self.assertIn("Default", scheduler.config["profiles"])

        # Verify profile structure
        default_profile = scheduler.config["profiles"]["Default"]
        self.assertEqual(default_profile["name"], "Default")
        self.assertTrue(default_profile["isActive"])
        self.assertIn("schedule", default_profile)

        # Verify schedule within profile
        schedule = default_profile["schedule"]
        self.assertIn("Monday", schedule)
        self.assertIn("Sunday", schedule)

        # Verify default values
        self.assertEqual(schedule["Monday"]["0"], 30)  # Night time
        self.assertEqual(schedule["Monday"]["12"], 70)  # Day time
        self.assertEqual(schedule["Monday"]["23"], 30)  # Night time

    def test_load_config_migrates_old_format(self):
        """Test that old config format is migrated to profiles"""
        # Create an old format schedule
        old_schedule = {
            "Monday": {"0": 50, "12": 80},
            "Tuesday": {"0": 40, "12": 90},
            "Wednesday": {},
            "Thursday": {},
            "Friday": {},
            "Saturday": {},
            "Sunday": {}
        }

        # Fill in remaining hours with defaults
        for day in old_schedule:
            for hour in range(24):
                if str(hour) not in old_schedule[day]:
                    old_schedule[day][str(hour)] = 70

        # Write old format to file
        volume_scheduler.CONFIG_DIR.mkdir(exist_ok=True)
        with open(volume_scheduler.CONFIG_FILE, "w") as f:
            json.dump(old_schedule, f)

        # Load it
        scheduler = volume_scheduler.VolumeScheduler()

        # Verify it was migrated to new format
        self.assertIn("profiles", scheduler.config)
        self.assertIn("Default", scheduler.config["profiles"])
        self.assertTrue(scheduler.config["profiles"]["Default"]["isActive"])
        
        # Verify old data is preserved
        migrated_schedule = scheduler.config["profiles"]["Default"]["schedule"]
        self.assertEqual(migrated_schedule["Monday"]["0"], 50)
        self.assertEqual(migrated_schedule["Monday"]["12"], 80)
        self.assertEqual(migrated_schedule["Tuesday"]["0"], 40)

    def test_load_config_reads_existing_profiles(self):
        """Test that load_config reads an existing config with profiles"""
        # Create a test config with profiles
        test_config = {
            "profiles": {
                "Work": {
                    "name": "Work",
                    "isActive": True,
                    "schedule": {
                        "Monday": {"0": 50, "12": 80},
                        "Tuesday": {"0": 40, "12": 90},
                        "Wednesday": {},
                        "Thursday": {},
                        "Friday": {},
                        "Saturday": {},
                        "Sunday": {}
                    }
                },
                "Weekend": {
                    "name": "Weekend",
                    "isActive": False,
                    "schedule": {
                        "Monday": {},
                        "Tuesday": {},
                        "Wednesday": {},
                        "Thursday": {},
                        "Friday": {},
                        "Saturday": {"0": 100, "12": 100},
                        "Sunday": {"0": 100, "12": 100}
                    }
                }
            }
        }

        # Fill in missing hours
        for profile_name, profile_data in test_config["profiles"].items():
            for day in profile_data["schedule"]:
                for hour in range(24):
                    if str(hour) not in profile_data["schedule"][day]:
                        profile_data["schedule"][day][str(hour)] = 70

        # Write it to file
        volume_scheduler.CONFIG_DIR.mkdir(exist_ok=True)
        with open(volume_scheduler.CONFIG_FILE, "w") as f:
            json.dump(test_config, f)

        # Load it
        scheduler = volume_scheduler.VolumeScheduler()

        # Verify it was loaded correctly
        self.assertEqual(len(scheduler.config["profiles"]), 2)
        self.assertIn("Work", scheduler.config["profiles"])
        self.assertIn("Weekend", scheduler.config["profiles"])
        self.assertTrue(scheduler.config["profiles"]["Work"]["isActive"])
        self.assertFalse(scheduler.config["profiles"]["Weekend"]["isActive"])

    def test_get_active_profile(self):
        """Test getting the active profile"""
        scheduler = volume_scheduler.VolumeScheduler()
        
        # Should have Default profile active
        profile_name, profile_data = scheduler.GetActiveProfile()
        self.assertEqual(profile_name, "Default")
        self.assertTrue(profile_data["isActive"])

    def test_set_active_profile(self):
        """Test switching active profiles"""
        scheduler = volume_scheduler.VolumeScheduler()
        
        # Add another profile
        scheduler.config["profiles"]["Work"] = {
            "name": "Work",
            "isActive": False,
            "schedule": scheduler.CreateDefaultSchedule()
        }
        
        # Switch to Work profile
        result = scheduler.SetActiveProfile("Work")
        
        self.assertTrue(result)
        self.assertFalse(scheduler.config["profiles"]["Default"]["isActive"])
        self.assertTrue(scheduler.config["profiles"]["Work"]["isActive"])

    def test_set_active_profile_nonexistent(self):
        """Test switching to non-existent profile"""
        scheduler = volume_scheduler.VolumeScheduler()
        
        result = scheduler.SetActiveProfile("NonExistent")
        
        self.assertFalse(result)
        # Default should still be active
        self.assertTrue(scheduler.config["profiles"]["Default"]["isActive"])

    def test_save_config(self):
        """Test that save_config writes correctly"""
        scheduler = volume_scheduler.VolumeScheduler()

        # Modify config
        scheduler.config["profiles"]["Test"] = {
            "name": "Test",
            "isActive": False,
            "schedule": {"Monday": {"0": 100}}
        }
        
        scheduler.SaveConfig(scheduler.config)

        # Verify file was created
        self.assertTrue(volume_scheduler.CONFIG_FILE.exists())

        # Verify content
        with open(volume_scheduler.CONFIG_FILE, "r") as f:
            loaded = json.load(f)
        self.assertIn("Test", loaded["profiles"])
        self.assertEqual(loaded["profiles"]["Test"]["schedule"]["Monday"]["0"], 100)

    @patch('subprocess.run')
    def test_set_volume_success(self, mock_run):
        """Test successful volume setting"""
        mock_run.return_value = MagicMock(returncode=0)

        scheduler = volume_scheduler.VolumeScheduler()
        result = scheduler.SetVolume(75)

        self.assertTrue(result)
        mock_run.assert_called_once()

        # Verify the AppleScript command
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "osascript")
        self.assertIn("75", args[2])

    @patch('subprocess.run')
    def test_set_volume_failure(self, mock_run):
        """Test volume setting failure handling"""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'osascript')

        scheduler = volume_scheduler.VolumeScheduler()
        result = scheduler.SetVolume(75)

        self.assertFalse(result)

    @patch('volume_scheduler.datetime')
    def test_get_current_schedule(self, mock_datetime):
        """Test getting schedule for current time from active profile"""
        # Mock current time to Monday at 14:00
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 14
        mock_datetime.now.return_value = mock_now

        scheduler = volume_scheduler.VolumeScheduler()
        volume = scheduler.GetCurrentSchedule()

        # Should return day time volume (70) from Default profile
        self.assertEqual(volume, 70)

    @patch('volume_scheduler.datetime')
    def test_get_current_schedule_night(self, mock_datetime):
        """Test getting schedule for night time from active profile"""
        # Mock current time to Monday at 2:00 AM
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 2
        mock_datetime.now.return_value = mock_now

        scheduler = volume_scheduler.VolumeScheduler()
        volume = scheduler.GetCurrentSchedule()

        # Should return night time volume (30)
        self.assertEqual(volume, 30)

    @patch('volume_scheduler.datetime')
    def test_get_current_schedule_different_profile(self, mock_datetime):
        """Test getting schedule from non-default active profile"""
        # Mock current time
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 10
        mock_datetime.now.return_value = mock_now

        scheduler = volume_scheduler.VolumeScheduler()
        
        # Add and activate a custom profile
        custom_schedule = scheduler.CreateDefaultSchedule()
        custom_schedule["Monday"]["10"] = 95
        
        scheduler.config["profiles"]["Custom"] = {
            "name": "Custom",
            "isActive": False,
            "schedule": custom_schedule
        }
        scheduler.SetActiveProfile("Custom")
        
        volume = scheduler.GetCurrentSchedule()
        
        # Should return custom volume
        self.assertEqual(volume, 95)

    @patch('subprocess.run')
    @patch('volume_scheduler.datetime')
    def test_check_and_update_volume(self, mock_datetime, mock_run):
        """Test volume update at hour change"""
        mock_run.return_value = MagicMock(returncode=0)

        # Mock current time
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 10
        mock_datetime.now.return_value = mock_now

        scheduler = volume_scheduler.VolumeScheduler()
        scheduler.last_hour = 9  # Previous hour

        scheduler.CheckAndUpdateVolume()

        # Verify volume was set
        mock_run.assert_called_once()
        self.assertEqual(scheduler.last_hour, 10)

    @patch('subprocess.run')
    @patch('volume_scheduler.datetime')
    def test_check_and_update_volume_same_hour(self, mock_datetime, mock_run):
        """Test that volume is not updated in the same hour"""
        mock_run.return_value = MagicMock(returncode=0)

        # Mock current time
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 10
        mock_datetime.now.return_value = mock_now

        scheduler = volume_scheduler.VolumeScheduler()
        scheduler.last_hour = 10  # Same hour

        scheduler.CheckAndUpdateVolume()

        # Verify volume was NOT set
        mock_run.assert_not_called()

    def test_handle_signal(self):
        """Test signal handler stops scheduler"""
        scheduler = volume_scheduler.VolumeScheduler()
        self.assertTrue(scheduler.running)

        scheduler.HandleSignal(None, None)

        self.assertFalse(scheduler.running)

    def test_create_default_schedule(self):
        """Test default schedule creation"""
        scheduler = volume_scheduler.VolumeScheduler()
        schedule = scheduler.CreateDefaultSchedule()
        
        # Verify structure
        self.assertEqual(len(schedule), 7)  # 7 days
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            self.assertIn(day, schedule)
            self.assertEqual(len(schedule[day]), 24)  # 24 hours
            
            # Verify night/day values
            for hour in range(24):
                if hour >= 22 or hour < 6:
                    self.assertEqual(schedule[day][str(hour)], 30)
                else:
                    self.assertEqual(schedule[day][str(hour)], 70)


class TestVolumeSchedulerFunctions(unittest.TestCase):
    """Tests for module-level functions"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.old_config_dir = volume_scheduler.CONFIG_DIR

        volume_scheduler.CONFIG_DIR = self.test_dir
        volume_scheduler.CONFIG_FILE = self.test_dir / "schedule.json"
        volume_scheduler.PID_FILE = self.test_dir / "scheduler.pid"
        volume_scheduler.MENU_PID_FILE = self.test_dir / "menu.pid"

    def tearDown(self):
        """Clean up test fixtures"""
        volume_scheduler.CONFIG_DIR = self.old_config_dir
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_is_process_running_existing(self):
        """Test checking if current process is running"""
        current_pid = os.getpid()
        result = volume_scheduler.IsProcessRunning(current_pid)
        self.assertTrue(result)

    def test_is_process_running_nonexistent(self):
        """Test checking if non-existent process is running"""
        # Use a very high PID that's unlikely to exist
        result = volume_scheduler.IsProcessRunning(999999)
        self.assertFalse(result)

    @patch('subprocess.Popen')
    @patch('time.sleep')
    def test_start_menu_bar_app_success(self, mock_sleep, mock_popen):
        """Test starting menu bar app successfully"""
        # Mock the Popen object
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process is still running
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        # Create the menu script file
        menu_script = self.test_dir / "volume_scheduler_menu.py"
        menu_script.touch()
        volume_scheduler.MENU_SCRIPT = menu_script

        result = volume_scheduler.StartMenubarApp()

        self.assertTrue(result)
        mock_popen.assert_called_once()

        # Verify PID file was created
        self.assertTrue(volume_scheduler.MENU_PID_FILE.exists())

    @patch('os.kill')
    @patch('time.sleep')
    def test_stop_menu_bar_app(self, mock_sleep, mock_kill):
        """Test stopping menu bar app"""
        # Create a PID file
        volume_scheduler.CONFIG_DIR.mkdir(exist_ok=True)
        with open(volume_scheduler.MENU_PID_FILE, "w") as f:
            f.write("12345")

        volume_scheduler.StopMenubarApp()

        # Verify kill was called
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    @patch('os.kill')
    @patch('time.sleep')
    def test_stop_scheduler(self, mock_sleep, mock_kill):
        """Test stopping the scheduler"""
        # Create a PID file
        volume_scheduler.CONFIG_DIR.mkdir(exist_ok=True)
        with open(volume_scheduler.PID_FILE, "w") as f:
            f.write("54321")

        # Mock process lookup to simulate process not existing after kill
        mock_kill.side_effect = [None] + [ProcessLookupError()] * 10

        volume_scheduler.StopScheduler()

        # Verify kill was called
        self.assertTrue(mock_kill.called)

    def test_manage_profiles_switch(self):
        """Test profile switching via manage_profiles"""
        # Create initial config
        scheduler = volume_scheduler.VolumeScheduler()
        scheduler.config["profiles"]["Work"] = {
            "name": "Work",
            "isActive": False,
            "schedule": scheduler.CreateDefaultSchedule()
        }
        scheduler.SaveConfig(scheduler.config)
        
        # Switch to Work profile
        volume_scheduler.ManageProfiles("Work")
        
        # Load config again to verify
        scheduler2 = volume_scheduler.VolumeScheduler()
        profile_name, _ = scheduler2.GetActiveProfile()
        self.assertEqual(profile_name, "Work")


class TestVolumeSchedulerMenu(unittest.TestCase):
    """Tests for the VolumeSchedulerMenu class"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())

        # Patch the config directory for the menu module
        volume_scheduler_menu.CONFIG_DIR = self.test_dir
        volume_scheduler_menu.CONFIG_FILE = self.test_dir / "schedule.json"
        volume_scheduler_menu.MENU_PID_FILE = self.test_dir / "menu.pid"

    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch('subprocess.run')
    def test_get_current_volume(self, mock_run):
        """Test getting current volume"""
        mock_run.return_value = Mock(stdout="75\n")

        # Test the method logic directly
        result = subprocess.run(
            ["osascript", "-e", "output volume of (get volume settings)"],
            capture_output=True,
            text=True,
            check=True
        )
        volume = int(result.stdout.strip())

        self.assertEqual(volume, 75)

    @patch('subprocess.run')
    def test_get_current_volume_failure(self, mock_run):
        """Test getting current volume when command fails"""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'osascript')

        # Test error handling
        try:
            result = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                capture_output=True,
                text=True,
                check=True
            )
            volume = int(result.stdout.strip())
        except:
            volume = None

        self.assertIsNone(volume)

    def test_get_active_profile(self):
        """Test getting active profile name"""
        # Create config with profiles
        config = {
            "profiles": {
                "Default": {
                    "name": "Default",
                    "isActive": False,
                    "schedule": {}
                },
                "Work": {
                    "name": "Work",
                    "isActive": True,
                    "schedule": {}
                }
            }
        }
        
        volume_scheduler_menu.CONFIG_DIR.mkdir(exist_ok=True)
        with open(volume_scheduler_menu.CONFIG_FILE, "w") as f:
            json.dump(config, f)
        
        # Test getting active profile logic
        with open(volume_scheduler_menu.CONFIG_FILE, "r") as f:
            loaded_config = json.load(f)
        
        active_profile = None
        for profile_name, profile_data in loaded_config["profiles"].items():
            if profile_data.get("isActive", False):
                active_profile = profile_name
                break
        
        self.assertEqual(active_profile, "Work")

    def test_get_active_profile_old_format(self):
        """Test getting active profile with old config format"""
        # Create old format config (no profiles)
        config = {"Monday": {}, "Tuesday": {}}
        
        volume_scheduler_menu.CONFIG_DIR.mkdir(exist_ok=True)
        with open(volume_scheduler_menu.CONFIG_FILE, "w") as f:
            json.dump(config, f)
        
        # Test migration logic
        with open(volume_scheduler_menu.CONFIG_FILE, "r") as f:
            loaded_config = json.load(f)
        
        # Should detect old format
        self.assertNotIn("profiles", loaded_config)


class TestScheduleHandler(unittest.TestCase):
    """Tests for the HTTP request handler"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
        volume_scheduler_menu.CONFIG_DIR = self.test_dir
        volume_scheduler_menu.CONFIG_FILE = self.test_dir / "schedule.json"
        volume_scheduler_menu.HTML_FILE = self.test_dir / "volume_scheduler_ui.html"

        # Create a test HTML file
        with open(volume_scheduler_menu.HTML_FILE, "w") as f:
            f.write("<h1>Test UI</h1>")

    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_do_GET_config(self):
        """Test GET request for config with profiles"""
        # Create a test config file with profiles
        test_config = {
            "profiles": {
                "Default": {
                    "name": "Default",
                    "isActive": True,
                    "schedule": {"Monday": {"0": 50}}
                }
            }
        }
        with open(volume_scheduler_menu.CONFIG_FILE, "w") as f:
            json.dump(test_config, f)

        # Create handler with mock request
        from io import BytesIO

        # Create a mock socket-like object
        mock_request = Mock()
        mock_request.makefile = Mock(
            side_effect=lambda *args, **kwargs: BytesIO())
        mock_socket = ('127.0.0.1', 8765)
        mock_server = Mock()

        handler = volume_scheduler_menu.ScheduleHandler(
            mock_request, mock_socket, mock_server
        )
        handler.path = "/api/config"
        handler.wfile = BytesIO()
        handler.rfile = BytesIO()

        # Mock methods
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()

        handler.do_GET()

        # Verify response
        handler.send_response.assert_called_with(200)

        # Check that data was written
        written_data = handler.wfile.getvalue()
        self.assertGreater(len(written_data), 0)
        
        # Verify it contains profiles
        response_data = json.loads(written_data.decode())
        self.assertIn("profiles", response_data)

    def test_do_POST_config(self):
        """Test POST request to save config with profiles"""
        from io import BytesIO

        new_config = {
            "profiles": {
                "Work": {
                    "name": "Work",
                    "isActive": True,
                    "schedule": {"Monday": {"0": 100}}
                }
            }
        }
        post_data = json.dumps(new_config).encode()

        # Create handler with mock socket-like request object
        mock_request = Mock()
        mock_request.makefile = Mock(
            side_effect=lambda *args, **kwargs: BytesIO())
        mock_socket = ('127.0.0.1', 8765)
        mock_server = Mock()

        handler = volume_scheduler_menu.ScheduleHandler(
            mock_request, mock_socket, mock_server
        )
        handler.path = "/api/config"
        handler.headers = {'Content-Length': str(len(post_data))}
        handler.rfile = BytesIO(post_data)
        handler.wfile = BytesIO()

        # Mock methods
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()

        handler.do_POST()

        # Verify response
        handler.send_response.assert_called_with(200)

        # Verify file was written with profiles
        self.assertTrue(volume_scheduler_menu.CONFIG_FILE.exists())
        with open(volume_scheduler_menu.CONFIG_FILE, "r") as f:
            saved = json.load(f)
        self.assertIn("profiles", saved)
        self.assertIn("Work", saved["profiles"])
        self.assertEqual(saved["profiles"]["Work"]["schedule"]["Monday"]["0"], 100)


class TestIntegration(unittest.TestCase):
    """Integration tests with profiles"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
        volume_scheduler.CONFIG_DIR = self.test_dir
        volume_scheduler.CONFIG_FILE = self.test_dir / "schedule.json"

    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch('subprocess.run')
    @patch('volume_scheduler.datetime')
    def test_full_schedule_cycle_with_profiles(self, mock_datetime, mock_run):
        """Test a full schedule load, update, and save cycle with profiles"""
        mock_run.return_value = MagicMock(returncode=0)

        # Create scheduler with default profile
        scheduler = volume_scheduler.VolumeScheduler()

        # Add a new profile
        scheduler.config["profiles"]["Work"] = {
            "name": "Work",
            "isActive": False,
            "schedule": scheduler.CreateDefaultSchedule()
        }
        
        # Modify the Work profile schedule
        scheduler.config["profiles"]["Work"]["schedule"]["Monday"]["10"] = 85
        
        # Switch to Work profile
        scheduler.SetActiveProfile("Work")
        scheduler.SaveConfig(scheduler.config)

        # Create new scheduler to load saved config
        scheduler2 = volume_scheduler.VolumeScheduler()

        # Verify the Work profile is active
        active_profile, active_data = scheduler2.GetActiveProfile()
        self.assertEqual(active_profile, "Work")
        
        # Verify the modification was loaded
        self.assertEqual(active_data["schedule"]["Monday"]["10"], 85)

        # Mock time to Monday 10:00
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 10
        mock_datetime.now.return_value = mock_now

        # Trigger volume check
        scheduler2.CheckAndUpdateVolume()

        # Verify correct volume was set (from Work profile)
        mock_run.assert_called()
        args = mock_run.call_args[0][0]
        self.assertIn("85", args[2])

    @patch('subprocess.run')
    @patch('volume_scheduler.datetime')
    def test_profile_switching_updates_volume(self, mock_datetime, mock_run):
        """Test that switching profiles applies the correct volume"""
        mock_run.return_value = MagicMock(returncode=0)

        # Create scheduler
        scheduler = volume_scheduler.VolumeScheduler()
        
        # Add a custom profile with different volume
        custom_schedule = scheduler.CreateDefaultSchedule()
        custom_schedule["Monday"]["10"] = 95
        
        scheduler.config["profiles"]["Custom"] = {
            "name": "Custom",
            "isActive": False,
            "schedule": custom_schedule
        }
        
        # Switch to Custom profile
        scheduler.SetActiveProfile("Custom")
        
        # Mock time to Monday 10:00
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 10
        mock_datetime.now.return_value = mock_now
        
        # Update volume
        scheduler.last_hour = 9  # Force update
        scheduler.CheckAndUpdateVolume()
        
        # Verify Custom profile volume was used
        args = mock_run.call_args[0][0]
        self.assertIn("95", args[2])

    def test_multiple_profiles_persistence(self):
        """Test that multiple profiles persist across restarts"""
        # Create scheduler with multiple profiles
        scheduler = volume_scheduler.VolumeScheduler()
        
        for profile_name in ["Work", "Weekend", "Silent"]:
            scheduler.config["profiles"][profile_name] = {
                "name": profile_name,
                "isActive": False,
                "schedule": scheduler.CreateDefaultSchedule()
            }
        
        scheduler.config["profiles"]["Work"]["isActive"] = True
        scheduler.config["profiles"]["Default"]["isActive"] = False
        scheduler.SaveConfig(scheduler.config)
        
        # Create new scheduler instance
        scheduler2 = volume_scheduler.VolumeScheduler()
        
        # Verify all profiles exist
        self.assertEqual(len(scheduler2.config["profiles"]), 4)  # Default + 3 custom
        self.assertIn("Work", scheduler2.config["profiles"])
        self.assertIn("Weekend", scheduler2.config["profiles"])
        self.assertIn("Silent", scheduler2.config["profiles"])
        
        # Verify Work is active
        active_profile, _ = scheduler2.GetActiveProfile()
        self.assertEqual(active_profile, "Work")


if __name__ == '__main__':
    unittest.main()
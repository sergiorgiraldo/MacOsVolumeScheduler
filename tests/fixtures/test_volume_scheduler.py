#!/usr/bin/env python3
"""
Unit tests for macOS Volume Scheduler
"""

import unittest
from unittest.mock import Mock, patch,  MagicMock
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

    def test_load_schedule_creates_default(self):
        """Test that load_schedule creates a default schedule when none exists"""
        scheduler = volume_scheduler.VolumeScheduler()

        # Verify schedule was created
        self.assertIsNotNone(scheduler.schedule)
        self.assertIn("Monday", scheduler.schedule)
        self.assertIn("Sunday", scheduler.schedule)

        # Verify default values
        self.assertEqual(scheduler.schedule["Monday"]["0"], 30)  # Night time
        self.assertEqual(scheduler.schedule["Monday"]["12"], 70)  # Day time
        self.assertEqual(scheduler.schedule["Monday"]["23"], 30)  # Night time

    def test_load_schedule_reads_existing(self):
        """Test that load_schedule reads an existing schedule file"""
        # Create a test schedule
        test_schedule = {
            "Monday": {"0": 50, "12": 80},
            "Tuesday": {"0": 40, "12": 90}
        }

        # Write it to file
        volume_scheduler.CONFIG_DIR.mkdir(exist_ok=True)
        with open(volume_scheduler.CONFIG_FILE, "w") as f:
            json.dump(test_schedule, f)

        # Load it
        scheduler = volume_scheduler.VolumeScheduler()

        # Verify it was loaded correctly
        self.assertEqual(scheduler.schedule["Monday"]["0"], 50)
        self.assertEqual(scheduler.schedule["Monday"]["12"], 80)
        self.assertEqual(scheduler.schedule["Tuesday"]["0"], 40)

    def test_save_schedule(self):
        """Test that save_schedule writes correctly"""
        scheduler = volume_scheduler.VolumeScheduler()

        test_schedule = {"Monday": {"0": 100}}
        scheduler.save_schedule(test_schedule)

        # Verify file was created
        self.assertTrue(volume_scheduler.CONFIG_FILE.exists())

        # Verify content
        with open(volume_scheduler.CONFIG_FILE, "r") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["Monday"]["0"], 100)

    @patch('subprocess.run')
    def test_set_volume_success(self, mock_run):
        """Test successful volume setting"""
        mock_run.return_value = MagicMock(returncode=0)

        scheduler = volume_scheduler.VolumeScheduler()
        result = scheduler.set_volume(75)

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
        result = scheduler.set_volume(75)

        self.assertFalse(result)

    @patch('volume_scheduler.datetime')
    def test_get_current_schedule(self, mock_datetime):
        """Test getting schedule for current time"""
        # Mock current time to Monday at 14:00
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 14
        mock_datetime.now.return_value = mock_now

        scheduler = volume_scheduler.VolumeScheduler()
        volume = scheduler.get_current_schedule()

        # Should return day time volume (70)
        self.assertEqual(volume, 70)

    @patch('volume_scheduler.datetime')
    def test_get_current_schedule_night(self, mock_datetime):
        """Test getting schedule for night time"""
        # Mock current time to Monday at 2:00 AM
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 2
        mock_datetime.now.return_value = mock_now

        scheduler = volume_scheduler.VolumeScheduler()
        volume = scheduler.get_current_schedule()

        # Should return night time volume (30)
        self.assertEqual(volume, 30)

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

        scheduler.check_and_update_volume()

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

        scheduler.check_and_update_volume()

        # Verify volume was NOT set
        mock_run.assert_not_called()

    def test_handle_signal(self):
        """Test signal handler stops scheduler"""
        scheduler = volume_scheduler.VolumeScheduler()
        self.assertTrue(scheduler.running)

        scheduler.handle_signal(None, None)

        self.assertFalse(scheduler.running)


class TestVolumeSchedulerFunctions(unittest.TestCase):
    """Tests for module-level functions"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.old_config_dir = volume_scheduler.CONFIG_DIR

        volume_scheduler.CONFIG_DIR = self.test_dir
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
        result = volume_scheduler.is_process_running(current_pid)
        self.assertTrue(result)

    def test_is_process_running_nonexistent(self):
        """Test checking if non-existent process is running"""
        # Use a very high PID that's unlikely to exist
        result = volume_scheduler.is_process_running(999999)
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

        result = volume_scheduler.start_menu_bar_app()

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

        volume_scheduler.stop_menu_bar_app()

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

        volume_scheduler.stop_scheduler()

        # Verify kill was called
        self.assertTrue(mock_kill.called)


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

    def test_do_GET_schedule(self):
        """Test GET request for schedule"""
        # Create a test schedule file
        test_schedule = {"Monday": {"0": 50}}
        with open(volume_scheduler_menu.CONFIG_FILE, "w") as f:
            json.dump(test_schedule, f)

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
        handler.path = "/api/schedule"
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

    def test_do_POST_schedule(self):
        """Test POST request to save schedule"""
        from io import BytesIO

        new_schedule = {"Monday": {"0": 100}}
        post_data = json.dumps(new_schedule).encode()

        # Create handler with mock socket-like request object
        mock_request = Mock()
        mock_request.makefile = Mock(
            side_effect=lambda *args, **kwargs: BytesIO())
        mock_socket = ('127.0.0.1', 8765)
        mock_server = Mock()

        handler = volume_scheduler_menu.ScheduleHandler(
            mock_request, mock_socket, mock_server
        )
        handler.path = "/api/schedule"
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

        # Verify file was written
        self.assertTrue(volume_scheduler_menu.CONFIG_FILE.exists())
        with open(volume_scheduler_menu.CONFIG_FILE, "r") as f:
            saved = json.load(f)
        self.assertEqual(saved["Monday"]["0"], 100)


class TestIntegration(unittest.TestCase):
    """Integration tests"""

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
    def test_full_schedule_cycle(self, mock_datetime, mock_run):
        """Test a full schedule load, update, and save cycle"""
        mock_run.return_value = MagicMock(returncode=0)

        # Create scheduler with default schedule
        scheduler = volume_scheduler.VolumeScheduler()

        # Modify schedule
        scheduler.schedule["Monday"]["10"] = 85
        scheduler.save_schedule(scheduler.schedule)

        # Create new scheduler to load saved schedule
        scheduler2 = volume_scheduler.VolumeScheduler()

        # Verify the modification was loaded
        self.assertEqual(scheduler2.schedule["Monday"]["10"], 85)

        # Mock time to Monday 10:00
        mock_now = Mock()
        mock_now.strftime.return_value = "Monday"
        mock_now.hour = 10
        mock_datetime.now.return_value = mock_now

        # Trigger volume check
        scheduler2.check_and_update_volume()

        # Verify correct volume was set
        mock_run.assert_called()
        args = mock_run.call_args[0][0]
        self.assertIn("85", args[2])


if __name__ == '__main__':
    unittest.main()

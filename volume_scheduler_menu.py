#!/usr/bin/env python3
"""
macOS Volume Scheduler - Menu Bar App
Adds a menu bar icon with volume control interface
Now with profile support
"""

import rumps
import subprocess
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from pathlib import Path
import os

# Import from your existing script
CONFIG_DIR = Path.home() / ".volume_scheduler"
CONFIG_FILE = CONFIG_DIR / "schedule.json"
PID_FILE = CONFIG_DIR / "scheduler.pid"
MENU_PID_FILE = CONFIG_DIR / "menu.pid"
HTML_FILE = Path(__file__).parent / "volume_scheduler_ui.html"


class ScheduleHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for web interface
    """

    def log_message(self, format, *args):
        pass

    """
    Handle GET requests
    """

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            if HTML_FILE.exists():
                with open(HTML_FILE, "r") as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(
                    b"<h1>Error: scheduler_ui.html not found</h1>")

        elif self.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                self.wfile.write(json.dumps(config).encode())
            else:
                self.wfile.write(json.dumps({"profiles": {}}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    """
    Handle POST requests
    """

    def do_POST(self):
        if self.path == "/api/config":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            config = json.loads(post_data.decode())

            CONFIG_DIR.mkdir(exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()


class VolumeSchedulerMenu(rumps.App):
    def __init__(self):
        super(VolumeSchedulerMenu, self).__init__(
            "Volume Scheduler",
            icon="/Users/GK47LX/source/MacOsVolumeScheduler/icon.svg",
            quit_button=None
        )

        self.server = None
        self.server_thread = None
        self.port = 8765

        # Menu items
        self.current_volume_item = rumps.MenuItem("Current Volume: --")
        self.current_profile_item = rumps.MenuItem("Profile: --")
        
        self.menu = [
            self.current_volume_item,
            self.current_profile_item,
            None,  # Separator
            rumps.MenuItem("Edit Schedule", callback=self.EditSchedule),
            None,  # Separator
            rumps.MenuItem("Quit", callback=self.QuitApp)
        ]

        # Update current volume and profile
        self.UpdateCurrentVolume()
        self.UpdateCurrentProfile()

        # Write PID file
        self.WritePIDFile()

    """
    Write PID file for this menu bar app
    """

    def WritePIDFile(self):
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(MENU_PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    """
    Get current macOS volume level
    """

    def GetCurrentVolume(self):
        try:
            result = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                capture_output=True,
                text=True,
                check=True
            )
            return int(result.stdout.strip())
        except:
            return None

    """
    Get current active profile name
    """

    def GetActiveProfile(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    
                    # Handle old format
                    if "profiles" not in config:
                        return "Default"
                    
                    for profile_name, profile_data in config["profiles"].items():
                        if profile_data.get("isActive", False):
                            return profile_name
            return "None"
        except:
            return "Error"

    """
    Update the current volume display
    """
    @rumps.timer(300)  # Update every 5 minutes
    def UpdateCurrentVolume(self, _=None):
        volume = self.GetCurrentVolume()
        self.current_volume_item.title = "Current Volume: " + \
            f"{volume}%" if volume is not None else "--"

    """
    Update the current profile display
    """
    @rumps.timer(60)  # Update every minute
    def UpdateCurrentProfile(self, _=None):
        profile = self.GetActiveProfile()
        self.current_profile_item.title = f"Profile: {profile}"

    """
    Start the web server in a background thread
    """

    def StartWebServer(self):
        if self.server is None:
            self.server = HTTPServer(('localhost', self.port), ScheduleHandler)
            self.server_thread = threading.Thread(
                target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()

    """
    Open the web UI for editing schedule
    """

    def EditSchedule(self, _):
        if not HTML_FILE.exists():
            rumps.alert(
                "Error",
                "scheduler_ui.html not found in the same directory as this script."
            )
            return

        # Start server if not already running
        self.StartWebServer()

        # Open browser
        webbrowser.open(f'http://localhost:{self.port}')

    """
    Quit the application
    """

    def QuitApp(self, _):
        # Stop web server if running
        if self.server:
            self.server.shutdown()

        # Clean up PID file
        try:
            if MENU_PID_FILE.exists():
                MENU_PID_FILE.unlink()
        except Exception:
            pass

        rumps.quit_application()


if __name__ == "__main__":
    VolumeSchedulerMenu().run()

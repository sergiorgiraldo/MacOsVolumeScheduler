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
HTML_FILE = Path(__file__).parent / "ui/volume_scheduler_ui.html"
LAUNCH_AGENT_DIR = Path.home() / "Library/LaunchAgents"
LAUNCH_AGENT_PLIST = LAUNCH_AGENT_DIR / "com.volumescheduler.plist"
ICON_FILE = Path(__file__).parent / "icon.svg"

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

        elif self.path.endswith(".css"):
                css_file = Path(__file__).parent / "ui" / self.path.lstrip("/")
                if css_file.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "text/css")
                    self.end_headers()
                    with open(css_file, "r") as f:
                        self.wfile.write(f.read().encode())
                else:
                    self.send_response(404)
                    self.end_headers()            
        elif self.path.endswith(".js"):
            js_file = Path(__file__).parent / "ui" / self.path.lstrip("/")
            if js_file.exists():
                self.send_response(200)
                self.send_header("Content-type", "application/javascript")
                self.end_headers()
                with open(js_file, "r") as f:
                    self.wfile.write(f.read().encode())
            else:
                self.send_response(404)
                self.end_headers()
        
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
            icon=str(ICON_FILE),
            quit_button=None
        )

        self.server = None
        self.server_thread = None
        self.port = 8765

        # Menu items
        self.current_volume_item = rumps.MenuItem("Current Volume: --")
        self.current_profile_item = rumps.MenuItem("Profile: --")
        self.startup_item = rumps.MenuItem(
            self.GetStartupMenuTitle(), 
            callback=self.ToggleStartup
        )
        
        self.menu = [
            self.current_volume_item,
            self.current_profile_item,
            None,  # Separator
            rumps.MenuItem("Edit Schedule", callback=self.EditSchedule),
            self.startup_item,
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
    Check if launch agent is installed
    """

    def IsStartupEnabled(self):
        return LAUNCH_AGENT_PLIST.exists()

    """
    Get the appropriate menu title for startup toggle
    """

    def GetStartupMenuTitle(self):
        return "Disable on Startup" if self.IsStartupEnabled() else "Enable on Startup"

    """
    Toggle startup launch agent
    """

    def ToggleStartup(self, _):
        # Run in a background thread so the main AppKit thread is not blocked
        # (blocking it causes macOS to grey out all menu items)
        threading.Thread(target=self._ToggleStartupWorker, daemon=True).start()

    def _ToggleStartupWorker(self):
        if self.IsStartupEnabled():
            self.DisableStartup()
        else:
            self.EnableStartup()

        # Update menu title back on the main thread via rumps
        self.startup_item.title = self.GetStartupMenuTitle()

    """
    Enable startup by creating launch agent
    """

    def EnableStartup(self):
        try:
            # Get the path to volume_scheduler.py (sibling of this script)
            scheduler_script = Path(__file__).parent / "volume_scheduler.py"
            
            if not scheduler_script.exists():
                rumps.alert(
                    "Error",
                    f"Could not find volume_scheduler.py at {scheduler_script}"
                )
                return

            # Create LaunchAgents directory if it doesn't exist
            LAUNCH_AGENT_DIR.mkdir(parents=True, exist_ok=True)

            # Create plist content
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.volumescheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>{scheduler_script}</string>
        <string>start</string>
        <string>--no-daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""

            # Write plist file
            with open(LAUNCH_AGENT_PLIST, "w") as f:
                f.write(plist_content)

            # Load the launch agent
            subprocess.run(
                ["launchctl", "load", str(LAUNCH_AGENT_PLIST)],
                check=True
            )

            rumps.notification(
                "Volume Scheduler",
                "Startup Enabled",
                "Volume Scheduler will now start automatically on login"
            )

        except subprocess.CalledProcessError as e:
            rumps.alert(
                "Error",
                f"Failed to load launch agent: {e}"
            )
        except Exception as e:
            rumps.alert(
                "Error",
                f"Failed to enable startup: {e}"
            )

    """
    Disable startup by removing launch agent
    """

    def DisableStartup(self):
        try:
            # Unload the launch agent first
            subprocess.run(
                ["launchctl", "unload", str(LAUNCH_AGENT_PLIST)],
                check=False  # Don't fail if already unloaded
            )

            # Remove plist file
            if LAUNCH_AGENT_PLIST.exists():
                LAUNCH_AGENT_PLIST.unlink()

            rumps.notification(
                "Volume Scheduler",
                "Startup Disabled",
                "Volume Scheduler will no longer start automatically on login"
            )

        except Exception as e:
            rumps.alert(
                "Error",
                f"Failed to disable startup: {e}"
            )

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
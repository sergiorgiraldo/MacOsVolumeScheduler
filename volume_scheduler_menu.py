#!/usr/bin/env python3
"""
macOS Volume Scheduler - Menu Bar App
Adds a menu bar icon with volume control interface
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
    """HTTP request handler for web interface"""
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            if HTML_FILE.exists():
                with open(HTML_FILE, "r") as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(b"<h1>Error: scheduler_ui.html not found</h1>")
                
        elif self.path == "/api/schedule":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r") as f:
                    schedule = json.load(f)
                self.wfile.write(json.dumps(schedule).encode())
            else:
                self.wfile.write(json.dumps({}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/api/schedule":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            schedule = json.loads(post_data.decode())
            
            CONFIG_DIR.mkdir(exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(schedule, f, indent=2)
            
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
            icon="/Users/GK47LX/source/MacOsVolumeScheduler/icon.svg",  # Speaker emoji as icon
            quit_button=None  # We'll add our own quit button
        )
        
        self.server = None
        self.server_thread = None
        self.port = 8765
        
        # Menu items
        self.current_volume_item = rumps.MenuItem("Current Volume: --")
        self.menu = [
            self.current_volume_item,
            None,  # Separator
            rumps.MenuItem("Edit Schedule", callback=self.edit_schedule),
            None,  # Separator
            rumps.MenuItem("Quit", callback=self.quit_app)
        ]
        
        # Update current volume
        self.update_current_volume()
        
        # Write PID file
        self.write_pid_file()
    
    def write_pid_file(self):
        """Write PID file for this menu bar app"""
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(MENU_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    
    def get_current_volume(self):
        """Get current macOS volume level"""
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
    
    @rumps.timer(300)  # Update every 5 minutes
    def update_current_volume(self, _=None):
        """Update the current volume display"""
        volume = self.get_current_volume()
        if volume is not None:
            self.current_volume_item.title = f"Current Volume: {volume}%"
        else:
            self.current_volume_item.title = "Current Volume: --"
    
    def start_web_server(self):
        """Start the web server in a background thread"""
        if self.server is None:
            self.server = HTTPServer(('localhost', self.port), ScheduleHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
    
    def edit_schedule(self, _):
        """Open the web UI for editing schedule"""
        if not HTML_FILE.exists():
            rumps.alert(
                "Error",
                "scheduler_ui.html not found in the same directory as this script."
            )
            return
        
        # Start server if not already running
        self.start_web_server()
        
        # Open browser
        webbrowser.open(f'http://localhost:{self.port}')
    
    def quit_app(self, _):
        """Quit the application"""
        # Stop web server if running
        if self.server:
            self.server.shutdown()
        
        # Clean up PID file
        try:
            if MENU_PID_FILE.exists():
                MENU_PID_FILE.unlink()
        except Exception:
            pass
        
        # Note: We don't stop the scheduler daemon here anymore
        # The main scheduler script will handle that when stopped
        
        rumps.quit_application()


if __name__ == "__main__":
    VolumeSchedulerMenu().run()
# Volume Scheduler

chmod +x volume_scheduler.py

## Start the scheduler (runs in background)

python volume_scheduler.py start

## Stop the scheduler

python volume_scheduler.py stop

## Edit the schedule

python volume_scheduler.py edit

## Check if it's running

python volume_scheduler.py status

## Create the plist file

```bash
vi ~/Library/LaunchAgents/com.volumescheduler.plist
```

with this content, adjust paths

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.volumescheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/YOUR_USERNAME/volume_scheduler.py</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

### launch on startup

launchctl load ~/Library/LaunchAgents/com.volumescheduler.plist

## configuration

schedule is stored in `~/.volume_scheduler/schedule.json`

### default

if config does not exists or reset:

>30% volume at night (22-6), 70% during day

### sample

`sample_schedule.json`


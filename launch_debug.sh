#!/bin/bash
# Debug launcher - captures environment and errors when launched from COSMIC
LOG=/tmp/GUI_sqlite_scrape_launch.log
echo "=== Launch at $(date) ===" >> "$LOG"
echo "USER=$USER HOME=$HOME" >> "$LOG"
echo "DISPLAY=$DISPLAY" >> "$LOG"
echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY" >> "$LOG"
echo "DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS" >> "$LOG"
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> "$LOG"
cd /home/daveg/Documents/GitHub/movie_Scraper
/home/daveg/Documents/GitHub/movie_Scraper/.venv/bin/python3 \
    /home/daveg/Documents/GitHub/movie_Scraper/GUI_sqlite_scrape.py >> "$LOG" 2>&1
echo "Exit code: $?" >> "$LOG"

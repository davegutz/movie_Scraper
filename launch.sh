#!/bin/bash
cd /home/daveg/Documents/GitHub/movie_Scraper
exec /home/daveg/Documents/GitHub/movie_Scraper/.venv/bin/python \
    /home/daveg/Documents/GitHub/movie_Scraper/GUI_sqlite_scrape.py "$@"

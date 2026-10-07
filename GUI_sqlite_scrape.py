#! /bin/sh
"exec" "`dirname $0`/.venv/bin/python3" "$0" "$@"
##! /users/daveg/Documents/GitHub/myStateOfCharge/SOC_Particle/py/venv/bin/python3.12
# The #! operates for macOS only. 'Python Launcher' (Python Script Preferences) option for 'Allow override with #! in script' is checked.
#  Manage movie database in conjunction with 'DB Browser for SQLite'
#  Run in PyCharm
#     or
#  'python3 GUI_sqlite_scrape.py
#
#  2024-Jan-16  Dave Gutz   Create
# Copyright (C) 2023 Dave Gutz
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation;
# version 2.1 of the License.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# See http://www.fsf.org/licensing/licenses/lgpl.txt for full license text
#
# Can create Windows executable as follows:
#  use pycharm settings to install pyinstaller
#  use pycharm terminal app to run:
#    pyinstaller .\GUI_sqlite_scrape.py --i popcorn.ico -y
#    cp blank.png .\dist\GUI_sqlite_scrape\.; cp popcorn.png .\dist\GUI_sqlite_scrape\.
#  double-click, browse to database, and pin to taskbar
#
#  Linux:
#    pyinstaller ./GUI_sqlite_scrape.py --hidden-import='PIL._tkinter_finder' --icon="popcorn.ico" -y
#    cp blank.png ./dist/GUI_sqlite_scrape/.; cp popcorn.png ./dist/GUI_sqlite_scrape/.
#  result found in dist folder
#
import io
import re
ANSI_ESCAPE_RE = re.compile(r'\x1b\[([0-9;]+)m')
import os
import sys
from configparser import ConfigParser
from tkinter import filedialog, ttk
import tkinter.simpledialog
import tkinter.messagebox
import sqlite3
import csv
# import imdb  # superseded
from datetime import datetime
from PIL import ImageTk, Image  # install pillow
import urllib.request
import numpy as np
import PySimpleGUI as pSG  # install PySimpleGUI-4-foss
from time import sleep
import subprocess
import threading
from tkinter import scrolledtext
from GitHub_util import check_newer_git_database, check_newer_git_repo

if sys.platform == 'darwin':
    # noinspection PyUnresolvedReferences
    from ttwidgets import TTButton as myButton
    import tkinter as tk
else:
    import tkinter as tk
    from tkinter import Button as myButton
from Colors import Colors
import requests
API_KEY = 'fd597cf0'

# Define frames
min_width = 820
main_height = 500
folder_reveal = 25
wrap_length = 500
wrap_length_note = 700
note_font = ("Arial bold", 10)
label_font = ("Arial bold", 12)
label_font_gentle = ("Arial", 10)
butt_font = ("Arial", 8)
butt_font_large = ("Arial bold", 10)
bg_color = "lightgray"
blue_back_color = '#3a4470'
blue_front_color = '#477bc9'
entry_color = '#2e3a4d'
light_purple = '#7258db'


class Begini(ConfigParser):

    def __init__(self, name, def_dict_):
        ConfigParser.__init__(self)

        (config_path, config_basename) = os.path.split(name)
        if sys.platform == 'linux':
            config_txt = os.path.splitext(config_basename)[0] + '_linux.ini'
            self.config_file_path = os.path.join('/home/daveg/.local/', config_txt)
        elif sys.platform == 'darwin':
            config_txt = os.path.splitext(config_basename)[0] + '_macos.ini'
            self.config_file_path = os.path.join('/Users/daveg/.local/', config_txt)
        else:
            config_txt = os.path.splitext(config_basename)[0] + '.ini'
            self.config_file_path = os.path.join(os.getenv('LOCALAPPDATA'), config_txt)
        print('config file', self.config_file_path)
        if os.path.isfile(self.config_file_path):
            self.read(self.config_file_path)
        else:
            with open(self.config_file_path, 'w') as cfg_file:
                self.read_dict(def_dict_)
                self.write(cfg_file)
            print('wrote', self.config_file_path)

    # Get an item
    def get_item(self, ind, item):
        return self[ind][item]

    # Put an item
    def put_item(self, ind, item, value):
        self[ind][item] = value
        self.save_to_file()

    # Save again
    def save_to_file(self):
        with open(self.config_file_path, 'w') as cfg_file:
            self.write(cfg_file)
        print('wrote', self.config_file_path)


class Feature:
    """Container of a film's information"""
    def __init__(self, ID, watched=None, myRating=None, have_dvd=0, added=None):
        self.ID = ID
        self.DVD = have_dvd
        movie = None
        while movie is None:
            try:
                sleep(0.5)
                movie = get_movie_details_id(self.ID, API_KEY)
            except imdb.IMDbDataAccessError:
                print('timeout.......retry after 0.5 second')
                sleep(0.5)
                continue
        self.title = movie['Title'].replace(':', '-').replace('?', '').replace('/', '-').replace('\u00e9', 'e').replace('\u00b7', '-').replace('\u00e1', 'a')
        try:
            self.year = movie['Year']
        except KeyError:
            self.year = 1900
        if watched is None:
            self.watched = ''
        else:
            self.watched = watched
        if added is None:
            self.added = str(datetime.today().strftime('%Y-%m-%d'))
        else:
            self.added = added
        try:
            self.rating = movie['imdbRating']
        except KeyError:
            self.rating = 0.
        if myRating is None or myRating == '':
            self.my_rating = self.rating
        else:
            self.my_rating = myRating
        try:
            self.directors = movie['Director']
        except KeyError:
            self.directors = ['']
        try:
            casting = movie['Actors']
            self.casting = str(casting)
        except KeyError:
            self.casting = ''
        try:
            self.genres = movie['Genre']
        except KeyError:
            self.genres = ''
        try:
            self.summary = movie['Plot']
        except KeyError:
            self.summary = ['']
        try:
            self.cover = movie['Poster']
        except KeyError:
            self.cover = ''
        try:
            self.runtime = movie['Runtime'].split()[0]
        except KeyError:
            self.runtime = ''
        try:
            self.certification = movie['Rated']
        except (KeyError, IndexError):
            self.certification = 'NR'


class IMDBdataBase:
    """Interface using Tkinter that has the API from IMDB to search the feature that is specified,
    enter the results into BBDD Sqlite3.
    https://gist.github.com/VictorLG98/30410204f175c278018a97dc5efbfe05
    https://www.youtube.com/watch?v=8PB3oFRkSeI
    """
    DB_FIELDS = [
        ('IMDB_ID',       'IMDB ID',              'integer'),
        ('title',         'Title',                 'text'),
        ('year',          'Year',                  'integer'),
        ('rating',        'Rating (IMDB)',         'real'),
        ('my_rating',     'My Rating',             'real'),
        ('director',      'Director',              'text'),
        ('actors',        'Actors',                'text'),
        ('generes',       'Genres',                'text'),
        ('summary',       'Summary',               'text'),
        ('cover',         'Cover URL',             'text'),
        ('WATCHED',       'Watched (YYYY-MM-DD)',  'text'),
        ('DVD',           'DVD',                   'text'),
        ('runtime',       'Runtime',               'text'),
        ('certification', 'Certification',         'text'),
        ('ADDED',         'Added (YYYY-MM-DD)',    'text'),
    ]

    def __init__(self, cf_):
        self.cf = cf_
        self.db_folder = self.cf['path']['db_folder']
        self.db_name = self.cf['path']['db_name']
        self.db_name = 'IMDB_Films.db'
        self.db_path = ''
        self.update_db_path()
        try:
            self.movies_dir = self.cf['path'].get('movies_dir', '/media/daveg/Lib/Movies')
        except Exception:
            self.movies_dir = '/media/daveg/Lib/Movies'
        try:
            self.rclone_remote = self.cf['rclone'].get('remote', 'gdrive:Movies')
        except Exception:
            self.rclone_remote = 'gdrive:Movies'
        self.rclone_tpslimit = '8'
        self.rclone_transfers = '2'
        self.rclone_checkers = '4'
        self.rclone_chunk_size = '512M'
        self.rclone_stats = '5s'
        self.rclone_log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rclone-error.log')
        self.year = datetime.now().year
        self.search_entry = None
        self.selected_id = []
        self.selected_titles = []
        self.picked = '<search and select something above>'

        # Set up main window
        self.path_disp_len = 25  # length of a path to reveal
        self.root = tk.Tk(className='GUI_sqlite_scrape')
        self.root.config(pady=20, padx=20, bg=bg_color)
        self.root.resizable(False, False)
        self.root.iconphoto(False, tk.PhotoImage(file='./popcorn.png'))
        self.top_frame = tk.Frame(self.root)
        self.top_frame.pack(side='top', expand=True, fill='both')
        self.mid_frame = tk.Frame(self.root)
        self.mid_frame.pack(side='top', expand=True, fill='both')
        self.mid_frame_left = tk.Frame(self.mid_frame, bg=blue_back_color)
        self.mid_frame_left.pack(side='left', expand=True, fill='both')
        self.mid_frame_right = tk.Frame(self.mid_frame, bg=bg_color)
        self.mid_frame_right.pack(side='right', expand=True, fill='both')
        self.bot_frame = tk.Frame(self.root)
        self.bot_frame.pack(side='top', expand=True, fill='both')
        self.bot_frame_left = tk.Frame(self.bot_frame, bg=bg_color)
        self.bot_frame_left.pack(side='left', expand=True, fill='both')
        self.bot_frame_right = tk.Frame(self.bot_frame, bg=blue_back_color)
        self.bot_frame_right.pack(side='right', expand=True, fill='both')

        # Lower left stuff
        img = ImageTk.PhotoImage(Image.open("blank.png"))
        self.poster = tk.Label(self.bot_frame_left, image=img)
        self.poster.pack(side='right')

        self.select_label_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.select_label_frame.pack(side='top', fill='both')
        self.select_label = tk.Label(self.select_label_frame, text='Selection =', bg=bg_color, anchor='w')
        self.select_display = tk.Label(self.select_label_frame, text=self.picked, fg=blue_front_color, bg=blue_back_color)
        self.select_label.pack(side='left')
        self.select_display.pack(side='left', pady=10)

        self.del_btn_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.del_btn_frame.pack(side='top', fill='both')
        self.del_btn = tk.Button(self.del_btn_frame, text="Delete selection", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                 width=25, command=self.delete_film)
        self.del_btn.pack(side='left')

        self.edit_btn_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.edit_btn_frame.pack(side='top', fill='both')
        self.edit_btn = tk.Button(self.edit_btn_frame, text="Edit Selection", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                  width=25, command=self.edit_selection)
        self.edit_btn.pack(side='left')

        self.watched_today_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.watched_today_frame.pack(side='top', fill='both')
        self.enter_today_btn = tk.Button(self.watched_today_frame, text="Watched today", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                         width=25, command=self.enter_today)
        self.enter_today_btn.pack(side='left')
        self.watched_today_btn = self.enter_today_btn

        self.db_loc_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.db_loc_frame.pack(side='top', fill='both')
        self.working_label = tk.Label(self.db_loc_frame, text="DB location =", bg=bg_color)
        self.destination_folder_butt = myButton(self.db_loc_frame, text=self.db_folder,
                                                command=self.enter_db_folder, fg="blue", bg=bg_color)
        slash = tk.Label(self.db_loc_frame, text="/", fg="blue", bg=bg_color)
        self.title_butt = myButton(self.db_loc_frame, text=self.db_name, command=self.enter_db, fg="blue",
                                   bg=bg_color)
        self.working_label.pack(side="left", fill='x')
        self.destination_folder_butt.pack(side="left", fill='x')
        slash.pack(side="left", fill='x')
        self.title_butt.pack(side="left", fill='x')

        self.backup_btn_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.backup_btn_frame.pack(side='top', fill='both', pady=(20, 0))
        self.backup_btn = tk.Button(self.backup_btn_frame, text="G-Drive rclone sync",
                                    font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                    width=25, command=self.google_drive_backup)
        self.backup_btn.pack(side='left')

        self.check_db_health_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.check_db_health_frame.pack(side='top', fill='both')
        self.check_db_health_btn = tk.Button(self.check_db_health_frame, text="Check Database Health",
                                             font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                             width=25, command=self.run_check_database_health)
        self.check_db_health_btn.pack(side='left')

        self.check_git_db_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.check_git_db_frame.pack(side='top', fill='both')
        self.check_git_db_btn = tk.Button(self.check_git_db_frame, text="Check Git Versions",
                                          font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                          width=25, command=lambda: self.check_git_newer_version(verbose=True))
        self.check_git_db_btn.pack(side='left')

        self.export_web_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.export_web_frame.pack(side='top', fill='both')
        self.export_web_btn = tk.Button(self.export_web_frame, text="Export movies.json",
                                        font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                        width=25, command=self.export_movies_to_web)
        self.export_web_btn.pack(side='left')

        # Database
        self.scroll = tk.Scrollbar(self.top_frame, orient=tk.VERTICAL)
        try:
            self.conn = sqlite3.connect(self.db_path)
        except sqlite3.OperationalError:
            print(Colors.fg.red, f"\n\nCouldn't open database file.  Sign into google-drive\n\n",
                  Colors.reset)
            tk.messagebox.showerror(title="Error", message='Sign into google-drive')
        self.c = None
        self.style = ttk.Style()
        self.tree = ttk.Treeview(self.top_frame, style="mystyle.Treeview", selectmode=tk.BROWSE)
        self.tree_modified = None
        self.db_tree_init()

        # Search
        self.search_title_lbl = tk.Label(self.mid_frame_left, text="Enter title search term:",
                                         font=('David', 15, 'bold'), bg=blue_back_color, fg=blue_front_color)
        self.search_title_lbl.pack(side='top')
        self.search_title_entry = tk.Entry(self.mid_frame_left, width=30, font=('LilyUPC', 13, 'bold'),
                                           fg=blue_front_color, bg=entry_color)
        self.search_title_entry.pack(side='top')
        self.search_title_entry.bind("<Return>", self.search_titles_event)
        self.search_title_btn = tk.Button(self.mid_frame_left, text="Search in titles", font=('LilyUPC', 13, 'bold'),
                                          bg=light_purple, width=25, command=self.search_titles)
        self.search_title_btn.pack(side='top')

        img = ImageTk.PhotoImage(Image.open("popcorn.png"))  # for some reason this has to be separate line
        self.icon = tk.Label(self.mid_frame_right, image=img)
        self.icon.pack(side='left')

        self.search_dirs_frame = tk.Frame(self.mid_frame_right, bg=bg_color)
        self.search_dirs_frame.pack(side='top')
        self.search_dirs_lbl = tk.Label(self.search_dirs_frame, text="Enter Director search term:",
                                        font=('David', 15, 'bold'), bg=blue_back_color, fg=blue_front_color)
        self.search_dirs_lbl.pack(side='left')
        self.search_dirs_entry = tk.Entry(self.search_dirs_frame, width=30, font=('LilyUPC', 13, 'bold'),
                                          fg=blue_front_color, bg=entry_color)
        self.search_dirs_entry.pack(side='left')
        self.search_dirs_entry.bind("<Return>", self.search_dirs_event)

        self.search_acts_frame = tk.Frame(self.mid_frame_right, bg=bg_color)
        self.search_acts_frame.pack(side='top')
        self.search_acts_lbl = tk.Label(self.search_acts_frame, text="Enter Actor search term:",
                                        font=('David', 15, 'bold'), bg=blue_back_color, fg=blue_front_color)
        self.search_acts_lbl.pack(side='left')
        self.search_acts_entry = tk.Entry(self.search_acts_frame, width=30, font=('LilyUPC', 13, 'bold'),
                                          fg=blue_front_color, bg=entry_color)
        self.search_acts_entry.pack(side='left')
        self.search_acts_entry.bind("<Return>", self.search_acts_event)

        # Controls
        self.film_lbl = tk.Label(self.bot_frame_right, text="Enter film:", font=('David', 15, 'bold'), bg=blue_back_color,
                                 fg=blue_front_color)
        self.film_lbl.pack(side='top')
        self.entry = tk.Entry(self.bot_frame_right, width=30, font=('LilyUPC', 13, 'bold'), fg=blue_front_color, bg=entry_color)
        self.entry.pack(side='top')
        self.entry.focus()
        self.year_lbl = tk.Label(self.bot_frame_right, text="Enter year (optional):", font=('David', 15, 'bold'), bg=blue_back_color,
                                 fg=blue_front_color)
        self.year_lbl.pack(side='top')
        self.entry_year = tk.Entry(self.bot_frame_right, width=30, font=('LilyUPC', 13, 'bold'), fg=blue_front_color, bg=entry_color)
        self.entry_year.pack(side='top')
        self.entry_year.bind("<Return>", self.add_film_auto)
        self.add_film_btn = tk.Button(self.bot_frame_right, text="Add film", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                      width=25, command=self.add_film)
        self.add_film_btn.pack(side='top')
        self.add_file_btn = tk.Button(self.bot_frame_right, text="Add file(s)", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                      width=25, command=self.add_file)
        self.add_file_btn.pack(side='top')
        self.add_manual_btn = tk.Button(self.bot_frame_right, text="Add entry manually", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                        width=25, command=self.open_add_manual_entry_window)
        self.add_manual_btn.pack(side='top')
        self.check_files_btn = tk.Button(self.bot_frame_right, text="Check file listing", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                         width=25, command=self.check_files)
        self.check_files_btn.pack(side='top')
        self.update_cert_time_btn = tk.Button(self.bot_frame_right, text="Update Cert and Time", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                              width=25, command=self.update_cert_time)
        self.update_cert_time_btn.pack(side='top')

        self.root.title(f"Features ({len(self.tree.get_children())})")
        self.root.after(200, self.check_git_newer_version)
        self.root.mainloop()
        self.conn.close()

    def add_file(self):
        """Insert film fields to Database"""
        filepaths = filedialog.askopenfilenames(title='Choose file(s)', filetypes=[('csv', '.csv')])
        if filepaths is None or filepaths == '':
            print("No file chosen")
        else:
            for filepath in filepaths:
                with open(filepath, mode='r') as file:
                    csvFile = csv.reader(file)
                    for line in csvFile:
                        if csvFile.line_num == 1:  # skip header line
                            continue
                        if len(line):
                            title = line[0].lower()
                        else:
                            continue
                        try:
                            year = int(line[1])
                        except (ValueError, IndexError):
                            year = 1860
                        watched_in = line[2]
                        try:
                            rating_in = line[3]
                        except IndexError:
                            rating_in = 0.
                        if self.already_have_film_year((title, year)):
                            print(f"The film ( {title}, {year} ) is already in the list")
                        else:
                            try:
                                id_film = self.look_smart(title, year)
                                added_in = str(datetime.today().strftime('%Y-%m-%d'))
                                new_movie = Feature(id_film, watched=watched_in, myRating=rating_in, added=added_in)
                            except (IOError, TypeError):
                                print(f"There is an error with the {title=}")
                                new_movie = None
                            # Enter into BBDD
                            if new_movie is not None:
                                try:
                                    print(f"new_movie: '{new_movie.title}' ({new_movie.year})")
                                    self.c.execute(f"""INSERT INTO My_Films(IMDB_ID, title, year, rating, my_rating,
                                                    director, actors, generes, summary, cover, WATCHED, DVD,
                                                    runtime, certification, ADDED) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);""",
                                                   (new_movie.ID, str(new_movie.title), int(year),
                                                    float(new_movie.rating), float(new_movie.my_rating),
                                                    str(new_movie.directors[0]), str(new_movie.casting),
                                                    str(new_movie.genres), str(new_movie.summary[0]),
                                                    str(new_movie.cover), new_movie.watched, new_movie.DVD,
                                                    new_movie.runtime, new_movie.certification, new_movie.added)),
                                    self.fill_tree_view()
                                except (UnboundLocalError, sqlite3.IntegrityError) as e:
                                    print(e)
                                    print(f"Trouble adding {new_movie.title} ({new_movie.year})")
                                    pass
                        self.root.title(f"Features ({len(self.tree.get_children())})")
                        self.conn.commit()
                print(f"{filepath=} done")

    def add_film_auto(self, _e):
        self.add_film_btn.config(bg='white')
        self.add_film()
        self.add_film_btn.config(bg=light_purple)

    def add_film(self):
        """Insert film fields to Database"""
        self.root.focus_set()
        if self.entry.get() == "" or self.entry.get().isspace():
            tk.messagebox.showerror(title="Error", message='You should pick a title')
        else:
            film = self.entry.get().strip().lower()
            if self.entry_year.get() != "" and not self.entry_year.get().isspace():
                year = self.entry_year.get().strip()
            else:
                year = str(0)
            have_film_year = self.already_have_film_year((film, year))
            if have_film_year:
                tk.messagebox.showerror(title="Error", message="The film is already in the list")
            else:
                try:
                    id_film = self.look_smart(film, year=year)
                    if id_film is None:
                        print(f"add_film:  not found at OMDB {film} ({year})")
                        tk.messagebox.showerror(title="Error", message="The film is not found")
                        return
                    have_id = self.already_have_id(id_film)
                    if have_id:
                        tk.messagebox.showerror(title="Error", message="The selected film is already in the list")
                        return
                    added_in = str(datetime.today().strftime('%Y-%m-%d'))
                    new_movie = Feature(id_film, have_dvd=4, added=added_in)  # 4=screencast copy
                    print(f"new_movie: '{new_movie.title}' ({new_movie.year})")
                except KeyError:
                    print(f"{film=} {year=}")
                    tk.messagebox.showerror(title="Error", message="There is an error with the film")
                    return
                # Enter into BBDD
                try:
                    new_movie.ID = new_movie.ID.replace('tt', '')
                    try:
                        new_movie.rating = float(new_movie.rating)
                    except ValueError:
                        new_movie.rating = 0.
                    try:
                        new_movie.my_rating = float(new_movie.my_rating)
                    except ValueError:
                        new_movie.my_rating = 0.
                    self.c.execute(f"""INSERT INTO My_Films(IMDB_ID, title, year, rating, my_rating,
                                    director, actors, generes, summary, cover, WATCHED, 
                                    DVD, runtime, certification, ADDED)
                                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);""",
                                   (new_movie.ID, str(new_movie.title), int(new_movie.year),
                                    float(new_movie.rating), float(new_movie.my_rating), str(new_movie.directors),
                                    str(new_movie.casting), str(new_movie.genres), str(new_movie.summary),
                                    str(new_movie.cover), str(''), int(new_movie.DVD),
                                    str(new_movie.runtime), str(new_movie.certification), str(new_movie.added)),)
                    self.fill_tree_view()
                    self.highlight_film((str(new_movie.title).lower(), int(new_movie.year)))
                except (UnboundLocalError, ValueError):
                    print(f"add_film:  couldn't enter film '{film} ({year}) id:{id_film}'")
                    pass
            self.root.title(f"Features ({len(self.tree.get_children())})")
            self.conn.commit()

    def open_add_manual_entry_window(self):
        """Open a Toplevel window to manually add a new entry to the database"""
        win = tk.Toplevel(self.root)
        win.title("Add New Entry Manually")
        win.config(bg=bg_color, padx=20, pady=20)
        win.grab_set()

        entries = {}
        today = str(datetime.today().strftime('%Y-%m-%d'))

        header = tk.Label(win, text="Add New Film Entry", font=('David', 15, 'bold'),
                          bg='white', fg='black')
        header.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))

        for i, (col, label, _typ) in enumerate(self.DB_FIELDS):
            tk.Label(win, text=label + ':', font=label_font, bg=bg_color, anchor='w').grid(
                row=i + 1, column=0, sticky='w', pady=3, padx=(0, 10))
            ent = tk.Entry(win, width=50, font=('LilyUPC', 11, 'bold'), fg='black', bg='white')
            ent.grid(row=i + 1, column=1, sticky='ew', pady=3)
            if col == 'ADDED':
                ent.insert(0, today)
            entries[col] = ent

        def save_entry():
            values = {}
            for col, label, typ in self.DB_FIELDS:
                raw = entries[col].get().strip()
                if typ == 'integer':
                    try:
                        values[col] = int(raw) if raw else 0
                    except ValueError:
                        tk.messagebox.showerror(title="Error", message=f"'{label}' must be an integer", parent=win)
                        return
                elif typ == 'real':
                    try:
                        values[col] = float(raw) if raw else 0.0
                    except ValueError:
                        tk.messagebox.showerror(title="Error", message=f"'{label}' must be a number", parent=win)
                        return
                else:
                    values[col] = raw
            if not str(values['IMDB_ID']).strip():
                tk.messagebox.showerror(title="Error", message="IMDB ID is required", parent=win)
                return
            try:
                cols = [c[0] for c in self.DB_FIELDS]
                placeholders = ', '.join(['?'] * len(cols))
                self.c.execute(f"""INSERT INTO My_Films({', '.join(cols)}) VALUES({placeholders});""",
                               tuple(values[c] for c in cols))
                self.conn.commit()
                self.fill_tree_view()
                self.root.title(f"Features ({len(self.tree.get_children())})")
                self.highlight_film((str(values['title']).lower(), int(values['year'])))
                win.destroy()
            except sqlite3.IntegrityError as e:
                tk.messagebox.showerror(title="Error", message=f"Database error: {e}", parent=win)

        btn_frame = tk.Frame(win, bg=bg_color)
        btn_frame.grid(row=len(self.DB_FIELDS) + 1, column=0, columnspan=2, pady=(10, 0))
        tk.Button(btn_frame, text="Save Entry", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                  width=20, command=save_entry).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                  width=20, command=win.destroy).pack(side='left', padx=5)

    def open_edit_entry_window(self, item):
        """Open a Toplevel window to edit an existing database entry, prepopulated with current values"""
        win = tk.Toplevel(self.root)
        win.title("Edit Entry")
        win.config(bg=bg_color, padx=20, pady=20)
        win.grab_set()

        original_imdb_id = item['values'][0]
        cols = [col for col, _, _ in self.DB_FIELDS]
        self.c.execute(f"SELECT {', '.join(cols)} FROM My_Films WHERE IMDB_ID = ?", (original_imdb_id,))
        row = self.c.fetchone()
        if row:
            existing = {col: ('' if val is None else str(val)) for col, val in zip(cols, row)}
        else:
            existing = {}

        entries = {}

        header = tk.Label(win, text="Edit Film Entry", font=('David', 15, 'bold'),
                          bg='white', fg='black')
        header.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))

        for i, (col, label, _typ) in enumerate(self.DB_FIELDS):
            tk.Label(win, text=label + ':', font=label_font, bg=bg_color, anchor='w').grid(
                row=i + 1, column=0, sticky='w', pady=3, padx=(0, 10))
            ent = tk.Entry(win, width=50, font=('LilyUPC', 11, 'bold'), fg='black', bg='white')
            ent.grid(row=i + 1, column=1, sticky='ew', pady=3)
            ent.insert(0, existing.get(col, ''))
            entries[col] = ent

        def save_entry():
            values = {}
            for col, label, typ in self.DB_FIELDS:
                raw = entries[col].get().strip()
                if typ == 'integer':
                    try:
                        values[col] = int(raw) if raw else 0
                    except ValueError:
                        tk.messagebox.showerror(title="Error", message=f"'{label}' must be an integer", parent=win)
                        return
                elif typ == 'real':
                    try:
                        values[col] = float(raw) if raw else 0.0
                    except ValueError:
                        tk.messagebox.showerror(title="Error", message=f"'{label}' must be a number", parent=win)
                        return
                else:
                    values[col] = raw
            if not str(values['IMDB_ID']).strip():
                tk.messagebox.showerror(title="Error", message="IMDB ID is required", parent=win)
                return
            try:
                set_str = ', '.join([f"{c}=?" for c in cols])
                self.c.execute(f"""UPDATE My_Films SET {set_str} WHERE IMDB_ID=?""",
                               tuple(values[c] for c in cols) + (original_imdb_id,))
                self.conn.commit()
                self.fill_tree_view()
                self.root.title(f"Features ({len(self.tree.get_children())})")
                self.highlight_film((str(values['title']).lower(), int(values['year'])))
                win.destroy()
            except sqlite3.IntegrityError as e:
                tk.messagebox.showerror(title="Error", message=f"Database error: {e}", parent=win)

        btn_frame = tk.Frame(win, bg=bg_color)
        btn_frame.grid(row=len(self.DB_FIELDS) + 1, column=0, columnspan=2, pady=(10, 0))
        tk.Button(btn_frame, text="Update", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                  width=20, command=save_entry).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                  width=20, command=win.destroy).pack(side='left', padx=5)

    def already_have_film_year(self, film):
        """Check for existence by year and title (film = (year, title))"""
        have = False
        title, year = film
        title = title.strip().lower()
        self.c.execute(f"SELECT title,year FROM My_Films ORDER BY title")
        rows = self.c.fetchall()
        row = [(item[0].strip().lower(), item[1]) for item in rows]
        for possible in [int(year)-2, int(year)-1, int(year), int(year)+1, int(year)+2]:
            film = (title, possible)
            if film in row:
                have = True
                break
        return have

    def already_have_id(self, id_):
        """Check for existence by IMDB_ID"""
        have = False
        self.c.execute(f"SELECT IMDB_ID FROM My_Films ORDER BY IMDB_ID")
        rows = self.c.fetchall()
        row = [item[0] for item in rows]
        # if int(id_) in row:
        if int(id_.replace('tt', '')) in row:
            have = True
        return have

    def check_files(self):
        """Take a listing of folder and check against DB for consistent naming"""
        filepaths = filedialog.askopenfilenames(title='Choose file(s)', filetypes=[('csv', '.csv')])
        if filepaths is None or filepaths == '':
            print("No file chosen")
        else:
            self.c.execute("SELECT title, year FROM My_Films ORDER BY title")
            rows = self.c.fetchall()
            for filepath in filepaths:
                with open(filepath, mode='r') as file:
                    csvFile = csv.reader(file)
                    file_names = []
                    for line in csvFile:
                        # Find best match
                        best_name = 0
                        best_similarity = 0.0
                        file_name = line[0]
                        file_root_name, ext = os.path.splitext(file_name)
                        for row in rows:
                            # Consider translate to names compatible both Windows and Linux
                            # You may need to work over your file system names to make this go smoothly
                            db_can = f"{row[0].replace(':', '-').replace('?', '').replace('/', '-').replace('\u00e9', 'e').replace('\u00b7', '-').replace('\u00e1', 'a')} ({row[1]}){ext}"
                            val = string_similarity(file_name, db_can)
                            if val > best_similarity:
                                best_name = db_can
                                best_similarity = val
                        name_i = (file_name, best_name, best_similarity)
                        if name_i[2] < 1.0:
                            print("mv \"{:s}\" \"{:s}\"  # {:5.2f}".format(name_i[0], name_i[1], name_i[2]))
                        file_names.append(name_i)
                out_file = filepath.replace('.csv', '.sh')
                with open(out_file, mode='w') as outf:
                    outf.write("# !/usr/bin/env bash")
                    for result in file_names:
                        if result[2] < 1.0:
                            out_str = "mv \"{:s}\" \"{:s}\"  # {:5.2f}\n".format(result[0], result[1], result[2])
                            outf.write(out_str)

    def db_tree_init(self):
        # Initialize database
        self.conn = sqlite3.connect(self.db_path)
        self.c = self.conn.cursor()
        self.c.execute(f"CREATE TABLE if not exists My_Films(IMDB_ID integer PRIMARY KEY,"
                       "title text, year integer, rating real, my_rating real,  director text, actors text,\
                        generes text, summary text, cover text, WATCHED text, DVD integer, runtime text, \
                        certification text, ADDED text)")
        self.conn.commit()

        # Set up Tree style
        self.style.configure("mystyle.Treeview.Heading", font=('Calibri', 12, 'bold'))

        # Set up the Tree columns
        self.tree['columns'] = ('IMDB_ID', 'Title', 'Year', 'Rating', 'MyRating', 'Director', 'Actors', 'Generes',
                                'Summary', 'Cover', 'WATCHED', 'DVD', 'Runtime', 'Certification', 'ADDED')
        self.tree.column('#0', width=0, stretch=tk.NO)
        self.tree.column('IMDB_ID', width=70, minwidth=50, anchor=tk.CENTER)
        self.tree.column('Title', width=150, minwidth=150, anchor=tk.CENTER)
        self.tree.column('Year', width=50, minwidth=50, anchor=tk.CENTER)
        self.tree.column('Rating', width=55, minwidth=55, anchor=tk.CENTER)
        self.tree.column('MyRating', width=78, minwidth=78, anchor=tk.CENTER)
        self.tree.column('Director', width=100, minwidth=100, anchor=tk.CENTER)
        self.tree.column('Actors', width=150, minwidth=150, anchor=tk.CENTER)
        self.tree.column('Generes', width=100, minwidth=100, anchor=tk.CENTER)
        self.tree.column('Summary', width=350, minwidth=350, anchor=tk.CENTER)
        self.tree.column('Cover', width=50, minwidth=50, anchor=tk.CENTER)
        self.tree.column('WATCHED', width=80, minwidth=80, anchor=tk.CENTER)
        self.tree.column('DVD', width=40, minwidth=40, anchor=tk.CENTER)
        self.tree.column('Runtime', width=50, minwidth=50, anchor=tk.CENTER)
        self.tree.column('Certification', width=50, minwidth=50, anchor=tk.CENTER)
        self.tree.column('ADDED', width=80, minwidth=80, anchor=tk.CENTER)

        # Set up the Tree headings
        col_heading_text = {
            'IMDB_ID': 'IMDB_ID',
            'Title': 'Title',
            'Year': 'Year',
            'Rating': 'Rating',
            'MyRating': 'My Rating',
            'Director': 'Director',
            'Actors': 'Actors',
            'Generes': 'Generes',
            'Summary': 'Summary',
            'Cover': 'Cover',
            'WATCHED': 'WATCHED',
            'DVD': 'DVD',
            'Runtime': 'Time',
            'Certification': 'Cert',
            'ADDED': 'ADDED',
        }
        self.tree.heading('#0', text='', anchor=tk.CENTER)
        for col, heading_txt in col_heading_text.items():
            self.tree.heading(col, text=heading_txt, anchor=tk.CENTER)

        self.tree["displaycolumns"] = ("IMDB_ID", "Title", "Certification", "Runtime", "Year", "Rating",
                                       "MyRating", "WATCHED", "ADDED", "DVD", "Director", "Actors", "Generes",
                                       "Summary")

        # Finish Tree
        self.scroll.pack(side='right')
        self.tree.config(yscrollcommand=self.scroll.set)
        self.scroll.config(command=self.tree.yview)
        self.sort_title(1)
        self.tree_modified = False
        self.tree.pack(side='left')

        # Bind for tree double click item
        self.tree.bind("<ButtonRelease-1>", self.OnSingleClick)
        self.tree.bind("<Double-1>", self.OnDoubleClick)
        self.tree.bind("<Return>", self.OnDoubleClick)

        # Bind for click column sort
        for col in self.tree["displaycolumns"]:
            if col == 'IMDB_ID' or col == 'Runtime' or col == 'Year':
                self.tree.heading(col, command=lambda _col=col:
                                  self.treeview_sort_column_int(self.tree, _col, False))
            elif col == 'MyRating' or col == 'Rating':
                self.tree.heading(col, command=lambda _col=col:
                                  self.treeview_sort_column_float(self.tree, _col, False))
            else:
                self.tree.heading(col, command=lambda _col=col:
                                  self.treeview_sort_column(self.tree, _col, False))

        self.fill_tree_view()
        print("tree initialized and packed")

    def highlight_film(self, film):
        """Check for existence by year and title (film = (year, title)) and set focus in tree"""
        (title, year) = film
        if film == () or film is None:
            print('nothing entered')
            return
        first_child = None
        for child in self.tree.get_children():
            can_title = str(self.tree.item(child)['values'][1]).lower()
            can_year = int(self.tree.item(child)['values'][2])
            if can_title == title and can_year == year:
                first_child = child
                break
        if first_child is not None:
            self.tree.focus(first_child)
            self.tree.selection_set(first_child)
            self.tree.see(first_child)
            self.picked = first_child
            self.select_display.config(text=self.tree.item(self.picked)['values'][1])
            self.raise_it(self.tree.item(first_child))
            print(f"found and focused on {film}")
        else:
            print(f"did not find {film}")

    def delete_film(self):
        """Delete from Database"""
        if self.picked is None:
            tk.messagebox.showerror(title="Error", message='You should pick a film')
        elif self.picked == '<search and select something above>':
            tk.messagebox.showerror(title="Error", message='You should select some features first')
        else:
            IMDB_ID = self.tree.item(self.picked)['values'][0]
            title = self.tree.item(self.picked)['values'][1]
            year = self.tree.item(self.picked)['values'][2]
            print(f"deleting {self.picked=} {IMDB_ID=} {title=} {year=}")
            self.c.execute(f"""DELETE from My_Films WHERE IMDB_ID = {IMDB_ID}""")
            self.fill_tree_view()
            self.root.title(f"Features ({len(self.tree.get_children())})")
            self.conn.commit()

    def edit_selection(self):
        """Open edit window for currently selected film"""
        curItem = self.tree.focus()
        if not curItem:
            selection = self.tree.selection()
            if selection:
                curItem = selection[0]
        if not curItem:
            if self.picked and self.picked != '<search and select something above>':
                curItem = self.picked
        if not curItem or curItem == '<search and select something above>':
            tk.messagebox.showinfo(title="Edit Selection", message="choose entry to edit", parent=self.root)
            return

        item = self.tree.item(curItem)
        if not item or not item.get('values'):
            tk.messagebox.showinfo(title="Edit Selection", message="choose entry to edit", parent=self.root)
            return

        self.open_edit_entry_window(item)

    def enter_today(self):
        """Update the WATCHED date of the currently selected film to today's date"""
        curItem = self.tree.focus()
        if not curItem:
            selection = self.tree.selection()
            if selection:
                curItem = selection[0]
        if not curItem:
            if self.picked and self.picked != '<search and select something above>':
                curItem = self.picked
        if not curItem or curItem == '<search and select something above>':
            tk.messagebox.showerror(title="Error", message='You should pick a film')
            return

        item = self.tree.item(curItem)
        if not item or not item.get('values'):
            tk.messagebox.showerror(title="Error", message='You should pick a film')
            return

        IMDB_ID = item['values'][0]
        title = item['values'][1]
        year = item['values'][2]
        new_watched = str(datetime.today().strftime('%Y-%m-%d'))
        print(f"setting watched date for '{title} ({year})' = {new_watched}")
        self.c.execute("UPDATE My_Films SET WATCHED = ? WHERE IMDB_ID = ?", (new_watched, IMDB_ID))
        self.conn.commit()
        self.fill_tree_view()
        self.highlight_film((str(title).lower(), int(year)))

    def enter_db(self):
        """Change to a different database name"""
        self.db_name = tk.simpledialog.askstring("Database Name", "Enter database name:", initialvalue=self.db_name)
        self.cf.put_item('path', 'db_name', self.db_name)
        self.title_butt.config(text=self.db_name)
        self.update_db_path()
        self.db_tree_init()

    def enter_db_folder(self):
        """Change to a different database folder"""
        self.db_folder = filedialog.askdirectory(title='Choose a Database folder', initialdir=self.db_folder)
        self.cf.put_item('path', 'db_folder', self.db_folder)
        self.destination_folder_butt.config(text=self.db_folder)
        self.update_db_path()
        self.db_tree_init()

    @staticmethod
    def fetch_image_from_url(url, timeout=5):
        """Fetch image bytes from URL with User-Agent header, returning PIL Image or None on error."""
        if not url:
            return None
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw_data = response.read()
                return Image.open(io.BytesIO(raw_data))
        except urllib.error.HTTPError as e:
            print(f"HTTPError fetching cover image from {url}: {e.code} {e.reason}")
            return None
        except urllib.error.URLError as e:
            print(f"URLError fetching cover image from {url}: {e.reason}")
            return None
        except Exception as e:
            print(f"Error fetching cover image from {url}: {e}")
            return None

    def fill_tree_view(self):
        # Delete old
        for child in self.tree.get_children():
            self.tree.delete(child)

        # Repopulate
        cols = [c[0] for c in self.DB_FIELDS]
        self.c.execute(f"SELECT {', '.join(cols)} FROM My_Films ORDER BY title")
        rows = self.c.fetchall()
        for row in rows:
            if row[0] is not None:
                rating_str = f"{row[3]:3.1f}" if isinstance(row[3], (int, float)) else str(row[3])
                my_rating_str = f"{row[4]:3.1f}" if isinstance(row[4], (int, float)) else str(row[4])
                self.tree.insert("", tk.END, values=(row[0], row[1], row[2], rating_str, my_rating_str,
                                                     row[5], row[6], row[7], row[8], row[9], row[10], row[11],
                                                     row[12], row[13], row[14]))

    def look_smart(self, film, year=0):
        # Look in IMDb
        print(f"searching OMDB for {film} ({year})...")
        search_result = get_movie_details(film, year, API_KEY)
        if search_result is None or search_result['Response'] == 'False':
            clean_film = ignore_articles(film)
            print(f"retry without articles: searching OMDB for {clean_film} ({year})...")
            search_result = get_movie_details(clean_film, year, API_KEY)
        if search_result is not None:
            id_film = search_result['imdbID']
        else:
            id_film = None
        return id_film

    def search_acts(self):
        self.search_acts_entry.config(bg='white')
        self.search_actors()
        self.search_acts_entry.config(bg=entry_color)

    def search_acts_event(self, _e):
        self.search_acts()

    def search_actors(self):
        actor = self.search_acts_entry.get().strip().lower()
        if actor == "" or actor.isspace():
            tk.messagebox.showerror(title="Error", message='You should pick an Actor')
        else:
            cols = [c[0] for c in self.DB_FIELDS]
            self.c.execute(f"""SELECT {', '.join(cols)} FROM My_Films WHERE actors LIKE '%{actor}%' ORDER BY title""")
            rows = self.c.fetchall()
            row = [item[0] for item in rows]
            if not row:
                tk.messagebox.showerror(title="Error", message='No films found')
            else:
                for child in self.tree.get_children():
                    self.tree.delete(child)
                for item in rows:
                    rating_str = f"{item[3]:3.1f}" if isinstance(item[3], (int, float)) else str(item[3])
                    my_rating_str = f"{item[4]:3.1f}" if isinstance(item[4], (int, float)) else str(item[4])
                    self.tree.insert("", tk.END, values=(item[0], item[1], item[2], rating_str, my_rating_str,
                                                         item[5], item[6], item[7], item[8], item[9], item[10], item[11],
                                                         item[12], item[13], item[14]))
                self.root.title(f"Features ({len(self.tree.get_children())})")

    def search_dirs(self):
        self.search_dirs_entry.config(bg='white')
        self.search_directors()
        self.search_dirs_entry.config(bg=entry_color)

    def search_dirs_event(self, _e):
        self.search_dirs()

    def search_directors(self):
        director = self.search_dirs_entry.get().strip().lower()
        if director == "" or director.isspace():
            tk.messagebox.showerror(title="Error", message='You should pick a Director')
        else:
            cols = [c[0] for c in self.DB_FIELDS]
            self.c.execute(f"""SELECT {', '.join(cols)} FROM My_Films WHERE director LIKE '%{director}%' ORDER BY title""")
            rows = self.c.fetchall()
            row = [item[0] for item in rows]
            if not row:
                tk.messagebox.showerror(title="Error", message='No films found')
            else:
                for child in self.tree.get_children():
                    self.tree.delete(child)
                for item in rows:
                    rating_str = f"{item[3]:3.1f}" if isinstance(item[3], (int, float)) else str(item[3])
                    my_rating_str = f"{item[4]:3.1f}" if isinstance(item[4], (int, float)) else str(item[4])
                    self.tree.insert("", tk.END, values=(item[0], item[1], item[2], rating_str, my_rating_str,
                                                         item[5], item[6], item[7], item[8], item[9], item[10], item[11],
                                                         item[12], item[13], item[14]))
                self.root.title(f"Features ({len(self.tree.get_children())})")

    def search_titles(self):
        title = self.search_title_entry.get().strip().lower()
        if title == "" or title.isspace():
            tk.messagebox.showerror(title="Error", message='You should pick a title')
        else:
            cols = [c[0] for c in self.DB_FIELDS]
            self.c.execute(f"""SELECT {', '.join(cols)} FROM My_Films WHERE title LIKE '%{title}%' ORDER BY title""")
            rows = self.c.fetchall()
            row = [item[0] for item in rows]
            if not row:
                tk.messagebox.showerror(title="Error", message='No films found')
            else:
                for child in self.tree.get_children():
                    self.tree.delete(child)
                for item in rows:
                    rating_str = f"{item[3]:3.1f}" if isinstance(item[3], (int, float)) else str(item[3])
                    my_rating_str = f"{item[4]:3.1f}" if isinstance(item[4], (int, float)) else str(item[4])
                    self.tree.insert("", tk.END, values=(item[0], item[1], item[2], rating_str, my_rating_str,
                                                         item[5], item[6], item[7], item[8], item[9], item[10], item[11],
                                                         item[12], item[13], item[14]))
                self.root.title(f"Features ({len(self.tree.get_children())})")

    def search_titles_event(self, _e):
        self.search_title_btn.config(bg='white')
        self.search_titles()
        self.search_title_btn.config(bg=light_purple)

    def sort_title(self, order):
        # Sort by title
        self.tree_modified = True
        cols = [c[0] for c in self.DB_FIELDS]
        self.c.execute(f"""SELECT {', '.join(cols)} FROM My_Films ORDER BY title {'ASC' if order == 1 else 'DESC'}""")
        rows = self.c.fetchall()
        for child in self.tree.get_children():
            self.tree.delete(child)
        for item in rows:
            rating_str = f"{item[3]:3.1f}" if isinstance(item[3], (int, float)) else str(item[3])
            my_rating_str = f"{item[4]:3.1f}" if isinstance(item[4], (int, float)) else str(item[4])
            self.tree.insert("", tk.END, values=(item[0], item[1], item[2], rating_str, my_rating_str,
                                                 item[5], item[6], item[7], item[8], item[9], item[10], item[11],
                                                 item[12], item[13], item[14]))
        self.tree_modified = False

    def treeview_sort_column(self, tv, col, reverse):
        self.tree_modified = True
        line = [(tv.set(k, col), k) for k in tv.get_children('')]
        line.sort(reverse=reverse)
        # rearrange items in sorted positions
        for index, (val, k) in enumerate(line):
            tv.move(k, '', index)
        # reverse sort next time
        tv.heading(col, command=lambda: self.treeview_sort_column(tv, col, not reverse))
        self.tree_modified = False

    def treeview_sort_column_float(self, tv, col, reverse):
        self.tree_modified = True
        line = [(float(tv.set(k, col)), k) for k in tv.get_children('')]
        line.sort(reverse=reverse)
        # rearrange items in sorted positions
        for index, (val, k) in enumerate(line):
            tv.move(k, '', index)
        # reverse sort next time
        tv.heading(col, command=lambda: self.treeview_sort_column_float(tv, col, not reverse))
        self.tree_modified = False

    def treeview_sort_column_int(self, tv, col, reverse):
        self.tree_modified = True
        line = []
        for k in tv.get_children(''):
            try:
                line.append((int(tv.set(k, col)), k))
            except ValueError:
                line.append((-1, k))
        line.sort(reverse=reverse)
        # rearrange items in sorted positions
        for index, (val, k) in enumerate(line):
            tv.move(k, '', index)
        # reverse sort next time
        tv.heading(col, command=lambda: self.treeview_sort_column_int(tv, col, not reverse))
        self.tree_modified = False

    def OnDoubleClick(self, _event):
        """Called when user double clicks an element from TreeView"""
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        print(f"OnDoubleClick: {curItem=} {item=}")
        self.renew()
        self.raise_it(item)
        self.picked = curItem
        try:
            self.select_display.config(text=self.tree.item(self.picked)['values'][1])
        except IndexError:
            pass

        edit_requested = [False]

        def on_edit_btn():
            edit_requested[0] = True
            win.destroy()

        def on_key(event):
            if event.keysym.lower() == 'e':
                on_edit_btn()
            elif event.keysym in ('Return', 'Escape', 'space'):
                win.destroy()

        win = tk.Toplevel(self.root)
        win.title("Summary")
        win.config(bg=bg_color, padx=10, pady=10)
        win.bind('<Key>', on_key)
        try:
            win.title(f"{item['values'][1]} ({item['values'][2]})")
            raw_summary = str(item['values'][8])
            lines = raw_summary.splitlines()
            wrapped_lines = []
            for l in lines:
                if len(l) > 100:
                    wrapped_lines.extend(re.findall(r'.{1,100}(?:\s+|$)', l))
                else:
                    wrapped_lines.append(l)
            summary_txt = "\n".join([wl.strip() for wl in wrapped_lines if wl.strip()])

            summary_label = tk.Label(win, text=summary_txt, font=note_font, bg='white', fg='black',
                                     wraplength=wrap_length_note, justify='left', anchor='w')
            summary_label.pack(side='top', fill='both', expand=True, padx=5, pady=5)
        except IndexError:
            pass

        btn_frame = tk.Frame(win, bg=bg_color)
        btn_frame.pack(side='bottom', fill='x', pady=(10, 0))

        edit_btn = tk.Button(btn_frame, text="Edit Entry (E)", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                             width=15, command=on_edit_btn)
        edit_btn.pack(side='left', padx=5)

        close_btn = tk.Button(btn_frame, text="Close (Esc)", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                              width=15, command=win.destroy)
        close_btn.pack(side='right', padx=5)

        win.focus_set()
        win.wait_window()

        if edit_requested[0]:
            self.open_edit_entry_window(item)

    def OnSingleClick(self, _event):
        """Called when user focuses element from TreeView"""
        curItem = self.tree.focus()
        if curItem != '':
            item = self.tree.item(curItem)
            print(f"OnSingleClick: {curItem=} {item=}")
            self.renew()
            self.raise_it(item)
            self.picked = curItem
            try:
                self.select_display.config(text=self.tree.item(self.picked)['values'][1])
            except IndexError:
                pass
        else:
            pass  # print(f"OnSingleClick: ignoring header")

    def raise_it(self, item):
        """Called when user focuses element from TreeView"""
        self.renew()
        try:
            values = item.get('values', []) if isinstance(item, dict) else []
            cover_url = str(values[9]).strip() if len(values) > 9 and values[9] else ''
            image = self.fetch_image_from_url(cover_url, timeout=5)
            if image is not None:
                my_img = ImageTk.PhotoImage(image)
                self.poster.configure(image=my_img)
                self.poster.image = my_img
            else:
                blank_img = ImageTk.PhotoImage(Image.open("blank.png"))
                self.poster.configure(image=blank_img)
                self.poster.image = blank_img
        except Exception as e:
            try:
                blank_img = ImageTk.PhotoImage(Image.open("blank.png"))
                self.poster.configure(image=blank_img)
                self.poster.image = blank_img
            except Exception:
                pass
            title = item.get('values', [''])[1] if isinstance(item, dict) and len(item.get('values', [])) > 1 else 'unknown'
            print(f"Could not load poster for '{title}': {e}")

    def renew(self):
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.entry.delete(0, "end")
        try:
            self.entry.insert(0, item['values'][1])
        except IndexError:
            pass

    def update_db_path(self):
        self.db_path = os.path.join(self.db_folder, self.db_name)

    def update_cert_time(self):
        """Check all Cert and Time values.  If NR or 0:00 go lookup the actual and save"""
        print("update_cert_time")
        count = 0
        change = 0
        for child in self.tree.get_children():
            count += 1
            can_time = str(self.tree.item(child)['values'][12]).lower()
            can_cert = str(self.tree.item(child)['values'][13]).lower()
            self.selected_id = child
            IMDB_ID = self.tree.item(self.selected_id)['values'][0]
            if IMDB_ID < 10000:
                continue
            if (can_cert == 'nr' or can_cert == '') and (can_time == '0:00' or can_time == '0'):
                can_title = self.tree.item(child)['values'][1]
                movie = Feature(IMDB_ID)
                new_cert = movie.certification
                new_time = movie.runtime
                self.c.execute(f"""UPDATE My_Films SET certification = (?) WHERE IMDB_ID = (?)""",
                               (new_cert, IMDB_ID))
                self.c.execute(f"""UPDATE My_Films SET runtime = (?) WHERE IMDB_ID = (?)""",
                               (new_time, IMDB_ID))
                self.conn.commit()
                print(f"title {can_title} ID {self.selected_id} IMDB_ID {IMDB_ID} certificate {can_cert}-->\
{new_cert} runtime {can_time}-->{new_time}")
                change += 1
        self.fill_tree_view()
        print(f"{count=} {change=}")

    def run_check_database_health(self):
        """Run check_database_health script and display progress/results in a top-level window."""
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check_database_health.py')
        if not os.path.isfile(script_path):
            tk.messagebox.showerror("Error", f"Could not find script: {script_path}")
            return

        cmd = [sys.executable, script_path, '--color', 'always']
        if self.db_path and os.path.isfile(self.db_path):
            cmd.extend(['--db', self.db_path])

        win = tk.Toplevel(self.root)
        win.title("Check Database Health")
        win.geometry("1150x650")
        win.config(bg=bg_color, padx=10, pady=10)

        header_frame = tk.Frame(win, bg=bg_color)
        header_frame.pack(side='top', fill='x', pady=(0, 5))
        status_lbl = tk.Label(
            header_frame,
            text="Running database health check...",
            font=('David', 12, 'bold'),
            bg=bg_color,
            fg=blue_back_color
        )
        status_lbl.pack(side='left')

        txt_frame = tk.Frame(win)
        txt_frame.pack(side='top', fill='both', expand=True)

        txt = scrolledtext.ScrolledText(
            txt_frame,
            wrap='none',
            font=('Courier', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white'
        )
        txt.pack(side='left', fill='both', expand=True)

        # Tags for colored output
        txt.tag_config('red', foreground='#ff6b6b')
        txt.tag_config('orange', foreground='#ff9f43')
        txt.tag_config('yellow', foreground='#feca57')
        txt.tag_config('green', foreground='#1dd1a1')

        h_scroll = tk.Scrollbar(win, orient='horizontal', command=txt.xview)
        txt.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(side='top', fill='x')

        btn_frame = tk.Frame(win, bg=bg_color)
        btn_frame.pack(side='bottom', fill='x', pady=(10, 0))

        close_btn = tk.Button(
            btn_frame,
            text="Close",
            font=('LilyUPC', 11, 'bold'),
            bg=light_purple,
            width=15,
            command=win.destroy
        )
        close_btn.pack(side='right', padx=5)

        def parse_ansi(raw_text):
            segments = []
            curr_tag = None
            last_idx = 0
            for match in ANSI_ESCAPE_RE.finditer(raw_text):
                if match.start() > last_idx:
                    segments.append((raw_text[last_idx:match.start()], curr_tag))
                code = match.group(1)
                if code in ('0', ''):
                    curr_tag = None
                elif code in ('91', '31'):
                    curr_tag = 'red'
                elif code in ('38;5;208', '38;5;214', '33'):
                    curr_tag = 'orange'
                elif code in ('93',):
                    curr_tag = 'yellow'
                elif code in ('92', '32'):
                    curr_tag = 'green'
                last_idx = match.end()
            if last_idx < len(raw_text):
                segments.append((raw_text[last_idx:], curr_tag))
            return segments

        def append_text(line):
            txt.config(state='normal')
            if line.startswith('\r'):
                txt.delete("end-1c linestart", "end-1c")
                line = line.lstrip('\r')
            for seg_text, tag in parse_ansi(line):
                if tag:
                    txt.insert(tk.END, seg_text, (tag,))
                else:
                    txt.insert(tk.END, seg_text)
            txt.see(tk.END)
            txt.config(state='disabled')

        def on_done(ret_code):
            if ret_code == 0:
                status_lbl.config(text="Database Health Check Complete.")
            else:
                status_lbl.config(text=f"Database Health Check finished with exit code {ret_code}.")

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                for line in iter(proc.stdout.readline, ''):
                    print(line, end='', flush=True)
                    txt.after(0, append_text, line)
                proc.stdout.close()
                proc.wait()
                txt.after(0, on_done, proc.returncode)
            except Exception as e:
                err_msg = "\nError executing check_database_health: " + str(e) + "\n"
                print(err_msg, flush=True)
                txt.after(0, append_text, err_msg)
                txt.after(0, on_done, -1)

        threading.Thread(target=worker, daemon=True).start()

    def export_movies_to_web(self):
        """Export My_Films to movies.json in this repository so regular git commits include it."""
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'export_movies_json.py')
        if not os.path.isfile(script_path):
            tk.messagebox.showerror("Error", f"Could not find export script: {script_path}", parent=self.root)
            return

        cmd = [sys.executable, script_path]
        if self.db_path and os.path.isfile(self.db_path):
            cmd.extend(["--db", self.db_path])

        win = tk.Toplevel(self.root)
        win.title("Export movies.json")
        win.geometry("750x350")
        win.config(bg=bg_color, padx=10, pady=10)

        header_frame = tk.Frame(win, bg=bg_color)
        header_frame.pack(side='top', fill='x', pady=(0, 5))
        status_lbl = tk.Label(
            header_frame,
            text="Exporting database to movies.json...",
            font=('David', 12, 'bold'),
            bg=bg_color,
            fg=blue_back_color
        )
        status_lbl.pack(side='left')

        txt_frame = tk.Frame(win)
        txt_frame.pack(side='top', fill='both', expand=True)

        txt = scrolledtext.ScrolledText(
            txt_frame,
            wrap='none',
            font=('Courier', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white'
        )
        txt.pack(side='left', fill='both', expand=True)

        txt.tag_config('red', foreground='#ff6b6b')
        txt.tag_config('green', foreground='#1dd1a1')
        txt.tag_config('yellow', foreground='#feca57')

        h_scroll = tk.Scrollbar(win, orient='horizontal', command=txt.xview)
        txt.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(side='top', fill='x')

        btn_frame = tk.Frame(win, bg=bg_color)
        btn_frame.pack(side='bottom', fill='x', pady=(10, 0))

        close_btn = tk.Button(
            btn_frame,
            text="Close",
            font=('LilyUPC', 11, 'bold'),
            bg=light_purple,
            width=15,
            command=win.destroy
        )
        close_btn.pack(side='right', padx=5)

        def append_text(line):
            txt.config(state='normal')
            tag = None
            l_low = line.lower()
            if "error" in l_low or "fatal" in l_low or "failed" in l_low or "[!]" in line:
                tag = 'red'
            elif "successfully" in l_low or "[✓]" in line:
                tag = 'green'
            elif "warning" in l_low or "[i]" in line:
                tag = 'yellow'

            if tag:
                txt.insert(tk.END, line, (tag,))
            else:
                txt.insert(tk.END, line)
            txt.see(tk.END)
            txt.config(state='disabled')

        def on_done(ret_code):
            if ret_code == 0:
                status_lbl.config(text="Export to movies.json Complete (Success)!")
                append_text("\n[✓] movies.json is updated. You can now commit and push via your normal git workflow.\n")
            else:
                status_lbl.config(text=f"Export finished with exit code {ret_code}.")

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                for line in iter(proc.stdout.readline, ''):
                    print(line, end='', flush=True)
                    txt.after(0, append_text, line)
                proc.stdout.close()
                proc.wait()
                txt.after(0, on_done, proc.returncode)
            except Exception as e:
                err_msg = "\nError executing export_movies_json: " + str(e) + "\n"
                print(err_msg, flush=True)
                txt.after(0, append_text, err_msg)
                txt.after(0, on_done, -1)

        threading.Thread(target=worker, daemon=True).start()

    def google_drive_backup(self):
        """Run rclone sync (INSTALL_Google_Drive_Backup.md lines 44-50) in background and open a monitor window (line 52)."""
        movies_src = self.movies_dir if self.movies_dir.endswith('/') else f"{self.movies_dir}/"
        rclone_cmd = [
            "rclone", "sync",
            movies_src,
            self.rclone_remote,
            "--tpslimit", str(self.rclone_tpslimit),
            "--transfers", str(self.rclone_transfers),
            "--checkers", str(self.rclone_checkers),
            "--drive-chunk-size", str(self.rclone_chunk_size),
            "--stats", str(self.rclone_stats),
            "-vv",
            "--log-file", self.rclone_log_file,
        ]

        # Ensure directory for log file exists
        log_dir = os.path.dirname(os.path.abspath(self.rclone_log_file))
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Clear or initialize log file
        try:
            with open(self.rclone_log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Google Drive Backup Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                f.write(f"Command: {' '.join(rclone_cmd)}\n\n")
        except Exception as e:
            print(f"Warning: could not initialize log file: {e}")

        # Start rclone sync in background (hidden process)
        try:
            backup_proc = subprocess.Popen(
                rclone_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True
            )
        except Exception as e:
            tk.messagebox.showerror("Error", f"Failed to start rclone backup: {e}", parent=self.root)
            return

        # Open monitor window for tail -f rclone-error.log
        win = tk.Toplevel(self.root)
        win.title("Google Drive Backup Monitor (tail -f rclone-error.log)")
        win.geometry("1100x600")
        win.config(bg=bg_color, padx=10, pady=10)

        header_frame = tk.Frame(win, bg=bg_color)
        header_frame.pack(side='top', fill='x', pady=(0, 5))
        status_lbl = tk.Label(
            header_frame,
            text=f"Syncing: {movies_src} -> {self.rclone_remote} (PID: {backup_proc.pid})...",
            font=('David', 12, 'bold'),
            bg=bg_color,
            fg=blue_back_color
        )
        status_lbl.pack(side='left')

        txt_frame = tk.Frame(win)
        txt_frame.pack(side='top', fill='both', expand=True)

        txt = scrolledtext.ScrolledText(
            txt_frame,
            wrap='none',
            font=('Courier', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white'
        )
        txt.pack(side='left', fill='both', expand=True)

        txt.tag_config('red', foreground='#ff6b6b')
        txt.tag_config('green', foreground='#1dd1a1')
        txt.tag_config('yellow', foreground='#feca57')
        txt.tag_config('cyan', foreground='#48dbfb')
        txt.tag_config('gray', foreground='#8395a7')

        h_scroll = tk.Scrollbar(win, orient='horizontal', command=txt.xview)
        txt.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(side='top', fill='x')

        btn_frame = tk.Frame(win, bg=bg_color)
        btn_frame.pack(side='bottom', fill='x', pady=(10, 0))

        stop_btn = tk.Button(
            btn_frame,
            text="Stop Backup",
            font=('LilyUPC', 11, 'bold'),
            bg='#e74c3c',
            fg='white',
            width=15
        )
        stop_btn.pack(side='left', padx=5)

        close_btn = tk.Button(
            btn_frame,
            text="Close",
            font=('LilyUPC', 11, 'bold'),
            bg=light_purple,
            width=15,
            command=win.destroy
        )
        close_btn.pack(side='right', padx=5)

        stop_tail_event = threading.Event()

        def on_stop():
            if backup_proc.poll() is None:
                if tk.messagebox.askyesno("Confirm Stop", "Are you sure you want to stop the Google Drive Backup process?", parent=win):
                    backup_proc.terminate()
                    stop_btn.config(state='disabled')
                    status_lbl.config(text="Backup stopped by user.")

        stop_btn.config(command=on_stop)

        def on_window_close():
            stop_tail_event.set()
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_window_close)

        def append_text(line):
            txt.config(state='normal')
            tag = None
            l_upper = line.upper()
            if "ERROR" in l_upper or "FATAL" in l_upper or "FAILED" in l_upper:
                tag = 'red'
            elif "NOTICE" in l_upper or "TRANSFERRED:" in l_upper or "100%" in l_upper:
                tag = 'green'
            elif "WARN" in l_upper or "STATS" in l_upper or "ELAPSED" in l_upper:
                tag = 'yellow'
            elif "INFO" in l_upper:
                tag = 'cyan'
            elif "DEBUG" in l_upper:
                tag = 'gray'

            if tag:
                txt.insert(tk.END, line, (tag,))
            else:
                txt.insert(tk.END, line)
            txt.see(tk.END)
            txt.config(state='disabled')

        def on_done(ret_code):
            stop_btn.config(state='disabled')
            if ret_code == 0:
                status_lbl.config(text="Google Drive Backup Complete successfully.")
            elif ret_code in (-15, 15, 1):
                status_lbl.config(text=f"Google Drive Backup stopped/ended with status {ret_code}.")
            else:
                status_lbl.config(text=f"Google Drive Backup finished with exit code {ret_code}.")

        def tail_worker():
            time_waited = 0.0
            while not os.path.exists(self.rclone_log_file) and not stop_tail_event.is_set() and time_waited < 10.0:
                sleep(0.2)
                time_waited += 0.2

            try:
                with open(self.rclone_log_file, 'r', encoding='utf-8', errors='replace') as f:
                    while not stop_tail_event.is_set():
                        line = f.readline()
                        if line:
                            txt.after(0, append_text, line)
                        else:
                            if backup_proc.poll() is not None:
                                for rem_line in f:
                                    txt.after(0, append_text, rem_line)
                                break
                            sleep(0.3)
            except Exception as ex:
                txt.after(0, append_text, f"\n[Log Monitor Error]: {ex}\n")

            ret = backup_proc.poll()
            if ret is not None:
                txt.after(0, on_done, ret)

        threading.Thread(target=tail_worker, daemon=True).start()

    def check_git_newer_version(self, verbose=False):
        """Check if a newer version of movie_Scraper or the database exists in git repository."""
        app_dir = os.path.dirname(os.path.abspath(__file__))
        app_name = os.path.basename(app_dir)
        db_name = os.path.basename(self.db_path) if self.db_path else "IMDB_Films.db"

        # 1. Check application repository (movie_Scraper)
        is_newer_app = False
        info_app = {}
        try:
            print(Colors.fg.cyan, f"\n--- Checking git version for application '{app_name}' ({app_dir}) ---", Colors.reset)
            is_newer_app, info_app = check_newer_git_repo(repo_dir=app_dir, print_status=True)
            if is_newer_app:
                rem_date = info_app.get('remote_date', 'Unknown')
                rem_msg = info_app.get('remote_msg', '')
                rem_sha = info_app.get('remote_sha', '')
                behind = info_app.get('behind_count')

                msg_lines = [
                    f"A newer version of '{app_name}' is available on git!\n",
                    f"Remote commit date:    {rem_date}",
                ]
                if rem_msg:
                    msg_lines.append(f"Remote commit message: {rem_msg}")
                if rem_sha:
                    msg_lines.append(f"Remote commit SHA:     {rem_sha}")
                if behind:
                    msg_lines.append(f"Commits behind:        {behind}")
                if 'local_date' in info_app and info_app['local_date']:
                    msg_lines.append(f"Local commit date:     {info_app['local_date']}")
                msg_lines.append(f"\nPlease update your '{app_name}' repository ('git pull') to get the latest updates.")
                msg = "\n".join(msg_lines)
                print(Colors.fg.yellow, f"\n[WARNING] Newer application version found on git!\n{msg}\n", Colors.reset)
                tk.messagebox.showwarning(title=f"Warning: Newer {app_name} on Git", message=msg, parent=self.root)
            else:
                if 'error' in info_app:
                    print(Colors.fg.orange, f"[Git Check] Application status: {info_app.get('error')}\n", Colors.reset)
                else:
                    method = info_app.get('method', 'git')
                    print(Colors.fg.green, f"[Git Check] Status: Application '{app_name}' is up to date with {method}.\n", Colors.reset)
        except Exception as e:
            print(Colors.fg.red, f"[Git Check] Error checking application git version: {e}\n", Colors.reset)

        # 2. Check database file (e.g. myComputer/IMDB_Films.db)
        is_newer_db = False
        info_db = {}
        try:
            print(Colors.fg.cyan, f"--- Checking git version for database '{db_name}' ({self.db_path}) ---", Colors.reset)
            is_newer_db, info_db = check_newer_git_database(self.db_path, print_status=True)
            if is_newer_db:
                rem_date = info_db.get('remote_date', 'Unknown')
                rem_msg = info_db.get('remote_msg', '')
                rem_sha = info_db.get('remote_sha', '')
                behind = info_db.get('behind_count')

                msg_lines = [
                    f"A newer version of {db_name} is available in git (myComputer)!\n",
                    f"Remote commit date:    {rem_date}",
                ]
                if rem_msg:
                    msg_lines.append(f"Remote commit message: {rem_msg}")
                if rem_sha:
                    msg_lines.append(f"Remote commit SHA:     {rem_sha}")
                if behind:
                    msg_lines.append(f"Commits behind:        {behind}")
                if 'local_date' in info_db and info_db['local_date']:
                    msg_lines.append(f"Local commit date:     {info_db['local_date']}")
                elif 'local_mtime' in info_db:
                    msg_lines.append(f"Local file date:       {info_db['local_mtime']}")
                msg_lines.append("\nPlease update your local repository ('git pull') before modifying the database.")
                msg = "\n".join(msg_lines)
                print(Colors.fg.yellow, f"\n[WARNING] Newer database version found on git!\n{msg}\n", Colors.reset)
                tk.messagebox.showwarning(title="Warning: Newer Database on Git", message=msg, parent=self.root)
            else:
                if 'error' in info_db:
                    print(Colors.fg.orange, f"[Git Check] Database status: {info_db.get('error')}\n", Colors.reset)
                else:
                    method = info_db.get('method', 'git')
                    print(Colors.fg.green, f"[Git Check] Status: Database '{db_name}' is up to date with {method}.\n", Colors.reset)
        except Exception as e:
            print(Colors.fg.red, f"[Git Check] Error checking database git version: {e}\n", Colors.reset)

        if verbose:
            if not is_newer_app and not is_newer_db:
                if 'error' in info_app or 'error' in info_db:
                    errs = []
                    if 'error' in info_app:
                        errs.append(f"Application: {info_app['error']}")
                    if 'error' in info_db:
                        errs.append(f"Database: {info_db['error']}")
                    tk.messagebox.showwarning(title="Git Check Notice", message="\n".join(errs), parent=self.root)
                else:
                    tk.messagebox.showinfo(title="Git Status", message=f"Both '{app_name}' and '{db_name}' are up to date with git.", parent=self.root)

def get_bigrams(string):
    """Take a string and return a list of bigrams"""
    s = string.lower()
    return [s[i:i + 2] for i in list(range(len(s) - 1))]


def get_movie_details(search_title, year, api_key):
    """
    Fetches movie details from OMDb API by title and year.
    """
    # The 't' parameter is for title, 'y' for year, and 'plot' for plot length
    params = {
        't': search_title,
        'y': year,
        'plot': 'full',
        'apikey': api_key
    }
    # OMDb API endpoint
    url = "http://www.omdbapi.com/"

    try:
        response = requests.get(url, params=params)
        # Raise an exception for bad status codes
        response.raise_for_status()
        movie_data = response.json()

        # Check if the request was successful
        if movie_data and movie_data.get('Title') is not None:
            print_movie_detail(movie_data)
            return movie_data
        else:
            print(f"Error: {movie_data.get('Error')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"A request error occurred: {e}")
        return None


def get_movie_details_id(ID, api_key):
    """
    Fetches movie details from OMDb API by title and year.
    """
    params = {
        'i': ID,
        'apikey': api_key
    }
    # OMDb API endpoint
    url = "http://www.omdbapi.com/"

    try:
        response = requests.get(url, params=params)
        # Raise an exception for bad status codes
        response.raise_for_status()
        movie_data = response.json()

        # Check if the request was successful
        if movie_data and movie_data.get('Title') is not None:
            print_movie_detail(movie_data)
            return movie_data
        else:
            print(f"Error: {movie_data.get('Error')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"A request error occurred: {e}")
        return None


def ignore_articles(text):
    articles = ['the', 'a', 'an', 'la', "l'", 'le', 'les', 'el', 'lo', 'las', 'los']
    for article in articles:
        if text.lower().startswith(article + ' '):
            return text[len(article)+1:].strip()
    return text


def print_movie_detail(movie_data):
    print(f"--- Details for '{movie_data['Title']}' ({movie_data['Year']}) ---")
    print(f"\tID: {movie_data['imdbID']}")
    print(f"\tRuntime: {movie_data['Runtime']}")
    print(f"\tDirectors: {movie_data['Director']}")
    print(f"\tActors: {movie_data['Actors']}")
    print(f"\tPlot Synopsis: {movie_data['Plot']}")
    if movie_data['Ratings']:
        print("\tRatings: ", movie_data['Ratings'])
        for rating in movie_data['Ratings']:
            print(f"\t\t  - {rating['Source']}: {rating['Value']}")


def string_similarity(str1, str2):
    """Perform bigram comparison between two strings and return a percentage match in decimal form."""
    pairs1 = get_bigrams(str1)
    pairs2 = get_bigrams(str2)
    union = len(pairs1) + len(pairs2)
    hit_count = 0
    for x in pairs1:
        for y in pairs2:
            if x == y:
                hit_count += 1
                break
    return (2.0 * hit_count) / union


if __name__ == "__main__":

    # Configuration for entire folder selection read with filepaths
    if sys.platform == 'linux':
        default_dict = {'path': {"db_folder": '/home/daveg/Documents/GitHub/myComputer', "db_name": 'myMovies.db', "movies_dir": '/media/daveg/Lib/Movies'},
                        'rclone': {"remote": 'gdrive:Movies'}}
    elif sys.platform == 'darwin':
        default_dict = {'path': {"db_folder": '/Users/daveg/Library/CloudStorage/GoogleDrive-davegutz2006@gmail.com/My Drive/Movies Stuff', "db_name": 'myMovies.db', "movies_dir": '/media/daveg/Lib/Movies'},
                        'rclone': {"remote": 'gdrive:Movies'}}
    else:
        default_dict = {'path': {"db_folder": 'G:/My Drive/Movies Stuff', "db_name": 'myMovies.db', "movies_dir": 'G:/Movies'},
                        'rclone': {"remote": 'gdrive:Movies'}}

    cf = Begini(__file__, default_dict)
    imdb = IMDBdataBase(cf_=cf)

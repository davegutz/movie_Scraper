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
import io
import os
import sys
from configparser import ConfigParser
from tkinter import filedialog, ttk
import tkinter.simpledialog
import tkinter.messagebox
import sqlite3
import csv
import imdb
from imdb import Cinemagoer  # install cinemagoer
from datetime import datetime
from PIL import ImageTk, Image  # install pillow
import urllib.request
import platform
import numpy as np
import PySimpleGUI as pSG
if platform.system() == 'Darwin':
    # noinspection PyUnresolvedReferences
    from ttwidgets import TTButton as myButton
else:
    import tkinter as tk
    from tkinter import Button as myButton

# Define frames
min_width = 800
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
        elif sys.platform == 'Darwin':
            config_txt = os.path.splitext(config_basename)[0] + '_macos.ini'
        else:
            config_txt = os.path.splitext(config_basename)[0] + '.ini'
        self.config_file_path = os.path.join(config_path, config_txt)
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
    def __init__(self, ID, watched=None, myRating=None):
        self.ID = ID
        movie = None
        while movie is None:
            try:
                movie = Cinemagoer().get_movie(self.ID)
            except imdb.IMDbDataAccessError:
                print('timeout.......retry')
                continue
        self.title = movie['title'].replace(':', '-').replace('?', '').replace('/', '-').replace('é', 'e').replace('·', '-').replace('á', 'a')
        self.year = movie['year']
        if watched is None:
            self.watched = ''
        else:
            self.watched = watched
        try:
            self.rating = movie['rating']
        except KeyError:
            self.rating = 0.
        if myRating is None or myRating == '':
            self.my_rating = self.rating
        else:
            self.my_rating = myRating
        try:
            self.directors = movie['directors']
        except KeyError:
            self.directors = ['']
        try:
            casting = movie['cast']
            self.casting = str(casting[0])
            for cas in casting[1:5]:
                self.casting += str(f', {cas}')
        except KeyError:
            self.casting = ''
        try:
            generes = movie['genres']
            self.genres = str(generes[0])
            for gen in generes[1:]:
                self.genres += str(f', {gen}')
        except KeyError:
            self.genres = ''
        try:
            self.summary = movie['plot']
        except KeyError:
            self.summary = ['']
        try:
            self.cover = movie['cover url']
        except KeyError:
            self.cover = ''


class IMDBdataBase:
    """Interface using Tkinter that has the API from IMDB to search the feature that is specified,
    enter the results into BBDD Sqlite3.
    https://gist.github.com/VictorLG98/30410204f175c278018a97dc5efbfe05
    https://www.youtube.com/watch?v=8PB3oFRkSeI
    """

    def __init__(self, cf_):
        self.cf = cf_
        self.db_folder = self.cf['path']['db_folder']
        self.db_name = self.cf['path']['db_name']
        self.db_name = 'IMDB_Films.db'
        self.db_path = ''
        self.update_db_path()
        self.year = datetime.now().year
        self.search_entry = None
        self.selected_id = []
        self.selected_titles = []
        self.picked = '<search and select something above>'

        # Set up main window
        self.path_disp_len = 25  # length of a path to reveal
        self.root = tk.Tk()
        self.root.config(pady=20, padx=20, bg=bg_color)
        self.root.resizable(False, False)
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

        self.change_watched_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.change_watched_frame.pack(side='top', fill='both')
        self.date_label = tk.Label(self.change_watched_frame, text="Change selection Watched   =", bg=bg_color)
        self.entry_date = tk.Entry(self.change_watched_frame, width=10, font=('LilyUPC', 13, 'bold'), fg=blue_front_color, bg=entry_color)
        self.entry_date_btn = tk.Button(self.change_watched_frame, text="Enter new Watched date", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                        width=20, command=self.enter_watched_date)
        self.date_label.pack(side='left')
        self.entry_date.pack(side="left", pady=5)
        self.entry_date_btn.pack(side='left', pady=5)

        self.change_rating_frame = tk.Frame(self.bot_frame_left, bg=bg_color)
        self.change_rating_frame.pack(side='top', fill='both')
        self.rating_label = tk.Label(self.change_rating_frame, text="Change selection My Rating =", bg=bg_color)
        self.entry_rating = tk.Entry(self.change_rating_frame, width=10, font=('LilyUPC', 13, 'bold'), fg=blue_front_color, bg=entry_color)
        self.entry_rating_btn = tk.Button(self.change_rating_frame, text="Enter new My Rating", font=('LilyUPC', 9, 'bold'), bg=light_purple,
                                          width=20, command=self.enter_my_rating)
        self.rating_label.pack(side='left')
        self.entry_rating.pack(side="left", pady=5)
        self.entry_rating_btn.pack(side='left', pady=5)

        self.working_label = tk.Label(self.bot_frame_left, text="DB location =", bg=bg_color)
        self.destination_folder_butt = myButton(self.bot_frame_left, text=self.db_folder,
                                                command=self.enter_db_folder, fg="blue", bg=bg_color)
        slash = tk.Label(self.bot_frame_left, text="/", fg="blue", bg=bg_color)
        self.title_butt = myButton(self.bot_frame_left, text=self.db_name, command=self.enter_db, fg="blue",
                                   bg=bg_color)
        self.working_label.pack(side="left", fill='x')
        self.destination_folder_butt.pack(side="left", fill='x')
        slash.pack(side="left", fill='x')
        self.title_butt.pack(side="left", fill='x')

        # IMDB API
        self.moviesDB = Cinemagoer()
        # Database
        self.conn = sqlite3.connect(self.db_path)
        self.c = self.conn.cursor()
        self.c.execute(f"CREATE TABLE if not exists My_Films(IMDB_ID integer PRIMARY KEY,"
                       "title text, year integer, rating real, my_rating real, director text, actors text, generes text, summary text, cover text, WATCHED text)")
        self.conn.commit()

        # Set up Tree style
        self.style = ttk.Style()
        self.style.configure("mystyle.Treeview.Heading", font=('Calibri', 12, 'bold'))
        self.tree = ttk.Treeview(self.top_frame, style="mystyle.Treeview", selectmode=tk.BROWSE)

        # Set up the Tree columns
        self.tree['columns'] = ('IMDB_ID', 'Title', 'Year', 'Rating', 'MyRating', 'Director', 'Actors', 'Generes', 'Summary', 'Cover', 'WATCHED')
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

        # Set up the Tree headings
        self.tree.heading('#0', text='', anchor=tk.CENTER)
        self.tree.heading('IMDB_ID', text='IMDB_ID', anchor=tk.CENTER)
        self.tree.heading('Title', text='Title', anchor=tk.CENTER)
        self.tree.heading('Year', text='Year', anchor=tk.CENTER)
        self.tree.heading('Rating', text='Rating', anchor=tk.CENTER)
        self.tree.heading('MyRating', text='My Rating', anchor=tk.CENTER)
        self.tree.heading('Director', text='Director', anchor=tk.CENTER)
        self.tree.heading('Actors', text='Actors', anchor=tk.CENTER)
        self.tree.heading('Generes', text='Generes', anchor=tk.CENTER)
        self.tree.heading('Summary', text='Summary', anchor=tk.CENTER)
        self.tree.heading('Cover', text='Cover', anchor=tk.CENTER)
        self.tree.heading('WATCHED', text='WATCHED', anchor=tk.CENTER)

        # Finish Tree
        self.scroll = tk.Scrollbar(self.top_frame, orient=tk.VERTICAL)
        self.scroll.pack(side='left')
        self.tree.config(yscrollcommand=self.scroll.set)
        self.scroll.config(command=self.tree.yview)

        # Bind for tree double click item
        self.tree.bind("<ButtonRelease-1>", self.OnSingleClick)
        # self.tree.bind("<<TreeviewSelect>>", self.OnSingleClick)
        self.tree.bind("<Double-1>", self.OnDoubleClick)
        self.tree.bind("<Return>", self.OnDoubleClick)
        self.tree.pack(side='left')

        # Search
        self.search_title_lbl = tk.Label(self.mid_frame_left, text="Enter title search term:",
                                         font=('David', 15, 'bold'), bg=blue_back_color, fg=blue_front_color)
        self.search_title_lbl.pack(side='top')
        self.search_title_entry = tk.Entry(self.mid_frame_left, width=30, font=('LilyUPC', 13, 'bold'),
                                           fg=blue_front_color, bg=entry_color)
        self.search_title_entry.pack(side='top')
        self.search_title_btn = tk.Button(self.mid_frame_left, text="Search in titles", font=('LilyUPC', 13, 'bold'),
                                          bg=light_purple, width=25, command=self.search_titles)
        self.search_title_btn.pack(side='top')
        self.search_select = ttk.Combobox(self.mid_frame_right)
        self.search_select.pack(pady=20)
        self.search_select.bind("<<ComboboxSelected>>", self.pick_title)

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
        self.add_film_btn = tk.Button(self.bot_frame_right, text="Add film", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                      width=25, command=self.add_film)
        self.add_film_btn.pack(side='top')
        self.add_file_btn = tk.Button(self.bot_frame_right, text="Add file(s)", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                      width=25, command=self.add_file)
        self.add_file_btn.pack(side='top')
        self.del_btn = tk.Button(self.bot_frame_right, text="Delete record", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                 width=25, command=self.delete_film)
        self.del_btn.pack(side='top')
        self.check_files_btn = tk.Button(self.bot_frame_right, text="Check file listing", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                         width=25, command=self.check_files)
        self.check_files_btn.pack(side='top')
        self.fill_tree_view()

        self.root.title(f"Features ({len(self.tree.get_children())})")

        self.root.mainloop()
        self.conn.close()
        print("Connection finished")

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
                                new_movie = Feature(id_film, watched=watched_in, myRating=rating_in)
                            except (IOError, TypeError):
                                print(f"There is an error with the {title=}")
                                new_movie = None
                            # Enter into BBDD
                            if new_movie is not None:
                                try:
                                    print(f"new_movie: '{new_movie.title}' ({new_movie.year})")
                                    self.c.execute(f"""INSERT INTO My_Films(IMDB_ID, title, year, rating, my_rating,
                                                    director, actors, generes, summary, cover, WATCHED) VALUES(?,?,?,?,?,?,?,?,?,?,?);""",
                                                   (new_movie.ID, str(new_movie.title), int(year),
                                                    float(new_movie.rating), float(new_movie.my_rating),
                                                    str(new_movie.directors[0]), str(new_movie.casting),
                                                    str(new_movie.genres), str(new_movie.summary[0]), str(new_movie.cover),
                                                    new_movie.watched)),
                                    self.fill_tree_view()
                                except (UnboundLocalError, sqlite3.IntegrityError) as e:
                                    print(e)
                                    print(f"Trouble adding {new_movie.title} ({new_movie.year})")
                                    pass
                        self.root.title(f"Features ({len(self.tree.get_children())})")
                        self.conn.commit()
                print(f"{filepath=} done")

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
                id_film = None
                try:
                    id_film = self.look_smart(film, year=year)
                    if id_film is None:
                        print(f"add_film:  not found at IMDB {film} ({year})")
                        tk.messagebox.showerror(title="Error", message="The film is not found")
                        return
                    new_movie = Feature(id_film)
                    print(f"new_movie: '{new_movie.title}' ({new_movie.year})")
                except KeyError:
                    print(f"{film=} {year=}")
                    tk.messagebox.showerror(title="Error", message="There is an error with the film")
                    return
                # Enter into BBDD
                try:
                    self.c.execute(f"""INSERT INTO My_Films(IMDB_ID, title, year, rating, my_rating,
                                    director, actors, generes, summary, cover, WATCHED) VALUES(?,?,?,?,?,?,?,?,?,?,?);""",
                                   (new_movie.ID, str(new_movie.title), int(new_movie.year),
                                    float(new_movie.rating), float(new_movie.my_rating), str(new_movie.directors[0]),
                                    str(new_movie.casting), str(new_movie.genres), str(new_movie.summary[0]),
                                    str(new_movie.cover), str(datetime.today().strftime('%Y/%m/%d')))),
                    self.fill_tree_view()
                except UnboundLocalError:
                    print(f"add_film:  couldn't enter film '{film} ({year}) id:{id_film}'")
                    pass
            self.root.title(f"Features ({len(self.tree.get_children())})")
            self.conn.commit()

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
        """Check for existence by year and title (film = (year))"""
        have = False
        self.c.execute(f"SELECT ID FROM My_Films ORDER BY ID")
        rows = self.c.fetchall()
        print(f"{rows=}")
        row = [item[0] for item in rows]
        if id_ in row:
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
                            # Consider translate to names compatible both Windows and linux
                            # You may need to work over your file system names to make this go smoothly
                            db_can = f"{row[0].replace(':', '-').replace('?', '').replace('/', '-').replace('é', 'e').replace('·', '-').replace('á', 'a')} ({row[1]}){ext}"
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

    def enter_watched_date(self):
        if self.picked is None or self.entry_date.get() == "" or self.entry.get().isspace():
            tk.messagebox.showerror(title="Error", message='You should pick something')
        else:
            IMDB_ID = self.tree.item(self.picked)['values'][0]
            WATCHED = str(self.tree.item(self.picked)['values'][10])
            new_WATCHED = self.entry_date.get()
            print(f"setting date = {new_WATCHED}")
            print(f"old picked ID {self.picked} IMDB_ID {IMDB_ID} date {WATCHED}")
            self.c.execute(f"""UPDATE My_Films SET WATCHED = (?) WHERE IMDB_ID = (?)""",
                           (new_WATCHED, IMDB_ID)),
            self.fill_tree_view()

    def enter_my_rating(self):
        if self.picked is None or self.entry_rating.get() == "" or self.entry_rating.get().isspace():
            tk.messagebox.showerror(title="Error", message='You should pick something')
        else:
            IMDB_ID = self.tree.item(self.picked)['values'][0]
            my_rating = str(self.tree.item(self.picked)['values'][4])
            new_my_rating = self.entry_rating.get()
            print(f"setting rating = {new_my_rating}")
            print(f"old picked ID {self.picked} IMDB_ID {IMDB_ID} rating {my_rating}")
            self.c.execute(f"""UPDATE My_Films SET my_rating = (?) WHERE IMDB_ID = (?)""",
                           (new_my_rating, IMDB_ID)),
            self.fill_tree_view()

    # noinspection
    def pick_title(self, _e):
        selected_title = self.search_select.get()
        for i in range(len(self.selected_id)):
            if self.selected_titles[i] == selected_title:
                self.picked = self.selected_id[i]
                self.tree.selection_set(self.picked)
                self.tree.see(self.picked)
                self.select_display.config(text=self.selected_titles[i])

    def search_titles(self):
        query = self.search_title_entry.get().strip().lower()
        self.selected_id = []
        self.selected_titles = []
        first_child = None
        for child in self.tree.get_children():
            can_Title = str(self.tree.item(child)['values'][1])
            can_title = can_Title.lower()
            if query in can_title:  # compare strings in  lower cases.
                if first_child is None:
                    first_child = child
                print(self.tree.item(child)['values'][1])
                self.selected_id.append(child)
                self.selected_titles.append(f"'{can_Title}'")
        self.tree.selection_set(self.selected_id)
        if first_child is not None:
            self.tree.see(first_child)
            self.search_select.config(values=self.selected_titles)
        else:
            print("Nothing found")

    def delete_film(self):
        """Delete selected film from database"""
        try:
            curItem = self.tree.focus()
            item = self.tree.item(curItem)
            deleting = tk.messagebox.askyesno(title="Warning", message=f"Are you sure you want to delete feature: "f"{(str(item['values'][1]))}?")
            if deleting:
                self.c.execute(f"DELETE FROM My_Films where IMDB_ID = (?);", (item['values'][0],))
                print(f"deleted", item['values'][1])
        except IndexError:
            tk.messagebox.showinfo(title='Info', message='You should pick an entry')
            print("Index Error")
        self.conn.commit()
        self.fill_tree_view()
        self.root.title(f"Features ({len(self.tree.get_children())})")

    def enter_db(self):
        answer = tk.simpledialog.askstring(title=__file__, prompt="enter db name", initialvalue=self.db_name)
        if answer is not None:
            self.db_name = answer
        if self.db_name == '':
            self.db_name = '<enter title>'
        cf['path']['db_name'] = self.db_name
        cf.save_to_file()
        self.title_butt.config(text=self.db_name)

    def enter_db_folder(self):
        """Select database folder"""
        answer = filedialog.askdirectory(title="Select a database storage folder", initialdir=self.db_folder)
        if answer is not None and answer != '':
            self.db_folder = answer
        self.cf['path']['db_folder'] = self.db_folder
        self.cf.save_to_file()
        self.destination_folder_butt.config(text=self.db_folder)

    def fill_tree_view(self):
        """Fill the TreeView with database fields"""
        self.tree.delete(*self.tree.get_children())
        self.c.execute(f"SELECT IMDB_ID, title, year, rating, my_rating, director, actors, generes, summary, cover, WATCHED FROM My_Films ORDER BY title")
        rows = self.c.fetchall()
        for row in rows:
            self.tree.insert("", tk.END, values=row)
        self.conn.commit()

    def look_smart(self, title, year=None):
        """Find IMDB match as good as possible, returning the ID"""
        film = (title, year)
        candidates = None
        while candidates is None:
            try:
                candidates = self.moviesDB.search_movie(title, results=12)
            except imdb.IMDbDataAccessError:
                print("timeout...retry")
                continue
        list_of_cans, array_of_cans, array_of_titles, array_of_years = self.make_list_of_cans(candidates)
        if not len(array_of_cans):
            return None

        # If exact matches take the first one
        exact_matches = (array_of_cans == film).all(axis=1)
        if exact_matches.any():
            exact_match = np.where(exact_matches)[0][0]  # take first one
            ID = list_of_cans[exact_match][0]
            return ID

        # Next find 'exact' matches within one year and take the first one
        film_p1 = (title, str(int(year)+1))
        film_m1 = (title, str(int(year)-1))
        exact_matches_m1 = (array_of_cans == film_m1).all(axis=1)
        exact_matches_p1 = (array_of_cans == film_p1).all(axis=1)
        if exact_matches_m1.any():
            exact_match = np.where(exact_matches_m1)[0][0]  # take first one
            ID = list_of_cans[exact_match][0]
            return ID
        elif exact_matches_p1.any():
            exact_match = np.where(exact_matches_p1)[0][0]  # take first one
            ID = list_of_cans[exact_match][0]
            return ID

        # Next offer choices of all that IMDB came up with
        print(f"{film}: {candidates=}")
        ID = None
        select_list = []
        for i in range(len(array_of_titles)):
            try:
                ID = candidates[i].getID()
                movie = Feature(ID)
                select_list.append(f"{movie.ID}:   {movie.title} ({movie.year})   cast = {movie.casting}   dir = {movie.directors}")
            except IOError:
                print(f"skipped: ", end='')
            print(f"{i}, ", end='')
        print(f"{select_list=}")
        lst = pSG.Listbox(select_list, size=(400, 100), font=('Arial Bold', 12), expand_y=True, enable_events=True,
                          key='-SELECTION-', horizontal_scroll=True)
        layout = [[pSG.Input(size=(20, 1), font=('Arial Bold', 14), expand_x=True, key='-INPUT-'), pSG.Button('Process'), pSG.Button('Cancel')], [lst], [pSG.Text("", key='-MSG-', font=('Arial Bold', 14), justification='center')]]
        window = pSG.Window(f"Match to '{title} ({year})'", layout, size=(900, 400))
        event, selection = window.read()
        window.close()
        print(selection)
        if event in (pSG.WIN_CLOSED, 'Cancel'):
            ID = None
        if event == '-SELECTION-':
            ID = selection['-SELECTION-'][0].split(':')[0]
            print(f"Selected from GUI {ID=}")
        window.close()

        return ID

    @staticmethod
    def make_list_of_cans(cans):
        """String together data; difficult to do for some reason.  Resort to this manual way"""
        result = []
        searchable_result = []
        titles = []
        years = []
        for item in cans:
            title = item['title'].strip().lower()
            ID = item.getID()
            try:
                year = item['year']
            except KeyError:
                year = 0
            result.append((ID, title, year))
            titles.append(title)
            years.append(year)
            searchable_result.append(np.array([title, year]))
        return result, np.array(searchable_result), np.array(titles, dtype='<U78'), np.array(years, dtype='<U78')

    def OnDoubleClick(self, _event):
        """Called when user double clicks element from TreeView"""
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.renew()
        with urllib.request.urlopen(item['values'][9]) as u:
            raw_data = u.read()
        image = Image.open(io.BytesIO(raw_data))
        my_img = ImageTk.PhotoImage(image)
        pic = tk.Label(self.root, image=my_img)
        pic.pack(side='left')
        tk.messagebox.showinfo(title=f"{item['values'][1]}", message=f"""
ID: {item['values'][0]}\n
Title: {item['values'][1]}\n
Year: {item['values'][2]}\n
Rating: {item['values'][3]}\n
MyRating: {item['values'][4]}\n
Director: {item['values'][5]}\n
Actors: {item['values'][6]}\n
Generes: {item['values'][7]}\n
Summary: {item['values'][8]}\n
Cover: {item['values'][9]}\n
Viewed: {item['values'][10]}
""")
        pic.pack_forget()

    def OnSingleClick(self, _event):
        """Called when user focuses element from TreeView"""
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        print(f"OnSingleClick: {curItem=} {item=}")
        self.renew()
        try:
            with urllib.request.urlopen(item['values'][9]) as u:
                raw_data = u.read()
            image = Image.open(io.BytesIO(raw_data))
            my_img = ImageTk.PhotoImage(image)
            self.poster.configure(image=my_img)
            self.poster.image = my_img
        except IndexError:
            pass
        self.picked = curItem
        print(f"OnSingleClick: {self.picked=}")
        self.select_display.config(text=self.tree.item(self.picked)['values'][1])

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


def get_bigrams(string):
    """Take a string and return a list of bigrams"""
    s = string.lower()
    return [s[i:i + 2] for i in list(range(len(s) - 1))]


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
    default_dict = {'path': {"db_folder": './', "db_name": 'myMovies.db'}}

    cf = Begini(__file__, default_dict)
    imdb = IMDBdataBase(cf_=cf)

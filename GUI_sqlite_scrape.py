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
from imdb import Cinemagoer
from datetime import datetime
from PIL import ImageTk, Image
import urllib.request
import platform
if platform.system() == 'Darwin':
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


# Begini - configuration class using .ini files
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

        # Set up main window
        self.path_disp_len = 25  # length of a path to reveal
        self.root = tk.Tk()
        self.root.config(pady=20, padx=20, bg=bg_color)
        self.root.resizable(False, False)
        self.top_frame = tk.Frame(self.root)
        self.top_frame.pack(side='top', expand=True, fill='both')
        self.bot_frame = tk.Frame(self.root)
        self.bot_frame.pack(side='top', expand=True, fill='both')
        self.bot_frame_left = tk.Frame(self.bot_frame, bg=bg_color)
        self.bot_frame_left.pack(side='left', expand=True, fill='both')
        self.bot_frame_right = tk.Frame(self.bot_frame, bg=blue_back_color)
        self.bot_frame_right.pack(side='right', expand=True, fill='both')

        # film icon
        img = ImageTk.PhotoImage(Image.open("blank.png"))
        self.poster = tk.Label(self.bot_frame_left, image=img)
        self.poster.pack(side='right')

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

        self.year = datetime.now().year

        # IMDB API
        self.moviesDB = Cinemagoer()
        # Database
        self.conn = sqlite3.connect(self.db_path)
        print("Connection made on exit")
        self.c = self.conn.cursor()
        self.c.execute(f"CREATE TABLE if not exists My_Films(id integer PRIMARY KEY, title text, "
                       "year integer, rating real, my_rating real, director text, actors text, generes text, summary text, cover text, date text)")
        self.conn.commit()
        # Set up Tree style
        self.style = ttk.Style()
        # self.current_theme = self.style.theme_use('clam')

        self.style.configure("mystyle.Treeview.Heading", font=('Calibri', 12, 'bold'))
        self.tree = ttk.Treeview(self.top_frame, style="mystyle.Treeview", selectmode=tk.BROWSE)
        # Set up the columns
        self.tree['columns'] = ('Title', 'Year', 'Rating', 'MyRating', 'Director', 'Actors', 'Generes', 'Summary', 'Cover', 'Watched')
        self.tree.column('#0', width=0, stretch=tk.NO)
        self.tree.column('Title', width=200, minwidth=200, anchor=tk.CENTER)
        self.tree.column('Year', width=70, minwidth=70, anchor=tk.CENTER)
        self.tree.column('Rating', width=82, minwidth=82, anchor=tk.CENTER)
        self.tree.column('MyRating', width=82, minwidth=82, anchor=tk.CENTER)
        self.tree.column('Director', width=100, minwidth=100, anchor=tk.CENTER)
        self.tree.column('Actors', width=150, minwidth=150, anchor=tk.CENTER)
        self.tree.column('Generes', width=100, minwidth=100, anchor=tk.CENTER)
        self.tree.column('Summary', width=350, minwidth=350, anchor=tk.CENTER)
        self.tree.column('Cover', width=50, minwidth=50, anchor=tk.CENTER)
        self.tree.column('Watched', width=80, minwidth=80, anchor=tk.CENTER)
        # Set up the headings
        self.tree.heading('#0', text='', anchor=tk.CENTER)
        self.tree.heading('Title', text='Title', anchor=tk.CENTER)
        self.tree.heading('Year', text='Year', anchor=tk.CENTER)
        self.tree.heading('Rating', text='Rating', anchor=tk.CENTER)
        self.tree.heading('MyRating', text='My Rating', anchor=tk.CENTER)
        self.tree.heading('Director', text='Director', anchor=tk.CENTER)
        self.tree.heading('Actors', text='Actors', anchor=tk.CENTER)
        self.tree.heading('Generes', text='Generes', anchor=tk.CENTER)
        self.tree.heading('Summary', text='Summary', anchor=tk.CENTER)
        self.tree.heading('Cover', text='Cover', anchor=tk.CENTER)
        self.tree.heading('Watched', text='Watched', anchor=tk.CENTER)

        self.scroll = tk.Scrollbar(self.top_frame, orient=tk.VERTICAL)
        self.scroll.pack(side='left')
        self.tree.config(yscrollcommand=self.scroll.set)
        self.scroll.config(command=self.tree.yview)
        # Bind for tree double click item
        self.tree.bind("<ButtonRelease-1>", self.OnSingleClick)
        self.tree.bind("<<TreeviewSelect>>", self.OnSingleClick)
        self.tree.bind("<Double-1>", self.OnDoubleClick)
        self.tree.bind("<Return>", self.OnDoubleClick)
        self.tree.pack(side='left')

        self.film_lbl = tk.Label(self.bot_frame_right, text="Enter film:", font=('David', 15, 'bold'), bg=blue_back_color,
                                 fg=blue_front_color)
        self.film_lbl.pack(side='top')
        self.entry = tk.Entry(self.bot_frame_right, width=30, font=('LilyUPC', 13, 'bold'), fg=blue_front_color, bg=entry_color)
        self.entry.pack(side='top')
        self.entry.focus()
        self.add_film_btn = tk.Button(self.bot_frame_right, text="Add film", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                      width=25, command=self.add_film)
        self.add_film_btn.pack(side='top')

        self.add_file_btn = tk.Button(self.bot_frame_right, text="Add file(s)", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                      width=25, command=self.add_file)
        self.add_file_btn.pack(side='top')

        self.del_btn = tk.Button(self.bot_frame_right, text="Delete record", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                 width=25, command=self.delete_film)
        self.del_btn.pack(side='top')
        self.list_it()

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
                        if csvFile.line_num == 1:
                            continue
                        title = line[0]
                        year = int(line[1])
                        watched = line[2]
                        rating_in = line[3]
                        film = (title.strip().lower(), year)
                        print(f"{film=} {watched=} {rating_in=}")
                        self.c.execute(f"SELECT title,year FROM My_Films")
                        rows = self.c.fetchall()
                        row = [(item[0].lower(), item[1]) for item in rows]
                        if film in row:
                            print(f"The film ( {title}, {year} ) is already in the list")
                        else:
                            try:
                                movies = self.moviesDB.search_movie(film[0])
                                id_film = movies[0].getID()
                                movie = self.moviesDB.get_movie(id_film)
                                title = movie['title']
                                year = movie['year']
                                rating = movie['rating']
                                if rating_in == '':
                                    my_rating = 0.
                                else:
                                    my_rating = float(rating_in)
                                directors = movie['directors']
                                casting = movie['cast']
                                sentence = ""
                                for cas in casting[0:5]:
                                    sentence += str(f'{cas}, ')
                                generes = movie['genres']
                                genres = ""
                                for gen in generes:
                                    genres += str(f'{gen}, ')
                                summary = movie['plot']
                                cover = movie['cover url']
                            except IOError:
                                tk.messagebox.showerror(title="Error", message=f"There is an error with the {film=}")
                            # Enter into BBDD
                            try:
                                self.c.execute(f"""INSERT INTO My_Films(title, year, rating, my_rating,
                                                director, actors, generes, summary, cover, date) VALUES(?,?,?,?,?,?,?,?,?,?);""",
                                               (str(title), int(year),
                                                float(rating), my_rating, str(directors[0]),
                                                str(sentence),
                                                str(genres), str(summary[0]), str(cover), watched)),
                                self.list_it()
                            except UnboundLocalError:
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
            self.c.execute(f"SELECT title FROM My_Films")
            rows = self.c.fetchall()
            row = [item[0].lower() for item in rows]
            if film in row:
                tk.messagebox.showerror(title="Error", message="The film is already in the list")
            else:
                try:
                    movies = self.moviesDB.search_movie(film)
                    print(f"{movies=}")
                    id_film = movies[0].getID()
                    movie = self.moviesDB.get_movie(id_film)
                    title = movie['title']
                    year = movie['year']
                    rating = movie['rating']
                    my_rating = rating
                    directors = movie['directors']
                    casting = movie['cast']
                    sentence = ""
                    for cas in casting[0:5]:
                        sentence += str(f'{cas}, ')
                    generes = movie['genres']
                    genres = ""
                    for gen in generes:
                        genres += str(f'{gen}, ')
                    summary = movie['plot']
                    cover = movie['cover url']
                except KeyError:
                    print(f"{movies=}")
                    tk.messagebox.showerror(title="Error", message="There is an error with the film")
                # Enter into BBDD
                try:
                    self.c.execute(f"""INSERT INTO My_Films(title, year, rating, my_rating,
                                    director, actors, generes, summary, cover, date) VALUES(?,?,?,?,?,?,?,?,?,?);""",
                                   (str(title), int(year),
                                    float(rating), float(my_rating), str(directors[0]),
                                    str(sentence),
                                    str(genres), str(summary[0]), str(cover),
                                    str(datetime.today().strftime('%Y/%m/%d')))),
                    self.list_it()
                except UnboundLocalError:
                    pass
            self.root.title(f"Features ({len(self.tree.get_children())})")
            self.conn.commit()

    def already_have_film(self, film):
        """Check for existence by year and title (film = (year, title))"""
        have = False
        title, year = film
        self.c.execute(f"SELECT title,year FROM My_Films")
        rows = self.c.fetchall()
        row = [(item[0].lower(), item[1]) for item in rows]
        for possible in [year-2, year-1, year, year+1, year+2]:
            if (title, possible) in row:
                have = True
                break
        return have

    def delete_film(self):
        """Delete selected film from database"""
        try:
            curItem = self.tree.focus()
            item = self.tree.item(curItem)
            mb = tk.messagebox.askyesno(title="Warning", message=f"Are you sure you want to delete feature: "
                                        f"{(str(item['values'][0]))}?")
            if mb:
                self.c.execute(f"DELETE FROM My_Films where title = (?);",
                               (str(item['values'][0]),))
        except IndexError:
            tk.messagebox.showinfo(title='Info', message='You should pick an entry')
            print("Index Error")
        self.conn.commit()
        self.list_it()
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

    def list_it(self):
        """Fill the TreeView with database fields"""
        self.tree.delete(*self.tree.get_children())
        self.c.execute(f"SELECT title, year, rating, my_rating, director, actors, generes, summary, cover, date FROM My_Films")
        rows = self.c.fetchall()
        for row in rows:
            self.tree.insert("", tk.END, values=row)
        self.conn.commit()

    def OnDoubleClick(self, event):
        """Called when user double clicks element from TreeView"""
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.renew()
        with urllib.request.urlopen(item['values'][8]) as u:
            raw_data = u.read()
        image = Image.open(io.BytesIO(raw_data))
        my_img = ImageTk.PhotoImage(image)
        pic = tk.Label(self.root, image=my_img)
        pic.pack(side='left')
        tk.messagebox.showinfo(title=f"{item['values'][0]}", message=f"""
Title: {item['values'][0]}\n
Year: {item['values'][1]}\n
Rating: {item['values'][2]}\n
MyRating: {item['values'][3]}\n
Director: {item['values'][4]}\n
Actors: {item['values'][5]}\n
Generes: {item['values'][6]}\n
Summary: {item['values'][7]}\n
Cover: {item['values'][8]}\n
Viewed: {item['values'][9]}
""")
        pic.pack_forget()

    def OnSingleClick(self, event):
        """Called when user focuses element from TreeView"""
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.renew()
        try:
            with urllib.request.urlopen(item['values'][8]) as u:
                raw_data = u.read()
            image = Image.open(io.BytesIO(raw_data))
            my_img = ImageTk.PhotoImage(image)
            self.poster.configure(image=my_img)
            self.poster.image = my_img
        except IndexError:
            pass

    def renew(self):
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.entry.delete(0, "end")
        try:
            self.entry.insert(0, item['values'][0])
        except IndexError:
            pass

    def update_db_path(self):
        self.db_path = os.path.join(self.db_folder, self.db_name)


if __name__ == "__main__":

    # Configuration for entire folder selection read with filepaths
    default_dict = {'path': {"db_folder": './', "db_name": 'myMovies.db'}}

    cf = Begini(__file__, default_dict)
    imdb = IMDBdataBase(cf_=cf)

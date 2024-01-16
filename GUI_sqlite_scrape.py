import io
from tkinter import messagebox
from tkinter import *
from tkinter import ttk, filedialog
import sqlite3
import csv
from imdb import Cinemagoer
from datetime import datetime
from PIL import ImageTk, Image
import urllib.request
import numpy as np

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


class IMDBdataBase:
    """Interface using Tkinter that has the API from IMDB to search the feature that is specified,
    enter the results into BBDD Sqlite3.
    https://gist.github.com/VictorLG98/30410204f175c278018a97dc5efbfe05
    https://www.youtube.com/watch?v=8PB3oFRkSeI
    """

    def __init__(self):
        # Set up main window
        self.root = Tk()
        self.root.config(pady=20, padx=20, bg=bg_color)
        self.root.resizable(False, False)
        self.top_frame = Frame(self.root)
        self.top_frame.pack(side='top', expand=True, fill='both')
        self.bot_frame_left = Frame(self.root, bg=bg_color)
        self.bot_frame_left.pack(side='bottom', expand=True, fill='both')
        self.bot_frame_right = Frame(self.root, bg=blue_back_color)
        self.bot_frame_right.pack(side='right', expand=True, fill='both')

        # film icon
        img = ImageTk.PhotoImage(Image.open("blank.png"))
        self.poster = Label(self.bot_frame_left, image=img)
        self.poster.pack(side='left')

        self.year = datetime.now().year

        # IMDB API
        self.moviesDB = Cinemagoer()
        # Database
        self.conn = sqlite3.connect('IMDB_Films.db')
        print("Connection made on exit")
        self.c = self.conn.cursor()
        self.c.execute(f"CREATE TABLE if not exists My_Films(id integer PRIMARY KEY, title text, "
                       "year integer, rating real, my_rating real, director text, actors text, generes text, summary text, cover text, date text)")
        self.conn.commit()
        # Set up Tree style
        self.style = ttk.Style()
        # self.current_theme = self.style.theme_use('clam')

        self.style.configure("mystyle.Treeview.Heading", font=('Calibri', 12, 'bold'))
        self.tree = ttk.Treeview(self.top_frame, style="mystyle.Treeview", selectmode=BROWSE)
        # Set up the columns
        self.tree['columns'] = ('Title', 'Year', 'Rating', 'MyRating', 'Director', 'Actors', 'Generes', 'Summary', 'Cover', 'Watched')
        self.tree.column('#0', width=0, stretch=NO)
        self.tree.column('Title', width=200, minwidth=200, anchor=CENTER)
        self.tree.column('Year', width=70, minwidth=70, anchor=CENTER)
        self.tree.column('Rating', width=82, minwidth=82, anchor=CENTER)
        self.tree.column('MyRating', width=82, minwidth=82, anchor=CENTER)
        self.tree.column('Director', width=100, minwidth=100, anchor=CENTER)
        self.tree.column('Actors', width=150, minwidth=150, anchor=CENTER)
        self.tree.column('Generes', width=100, minwidth=100, anchor=CENTER)
        self.tree.column('Summary', width=350, minwidth=350, anchor=CENTER)
        self.tree.column('Cover', width=50, minwidth=50, anchor=CENTER)
        self.tree.column('Watched', width=80, minwidth=80, anchor=CENTER)
        # Set up the headings
        self.tree.heading('#0', text='', anchor=CENTER)
        self.tree.heading('Title', text='Title', anchor=CENTER)
        self.tree.heading('Year', text='Year', anchor=CENTER)
        self.tree.heading('Rating', text='Rating', anchor=CENTER)
        self.tree.heading('MyRating', text='My Rating', anchor=CENTER)
        self.tree.heading('Director', text='Director', anchor=CENTER)
        self.tree.heading('Actors', text='Actors', anchor=CENTER)
        self.tree.heading('Generes', text='Generes', anchor=CENTER)
        self.tree.heading('Summary', text='Summary', anchor=CENTER)
        self.tree.heading('Cover', text='Cover', anchor=CENTER)
        self.tree.heading('Watched', text='Watched', anchor=CENTER)

        self.scroll = Scrollbar(self.top_frame, orient=VERTICAL)
        self.scroll.pack(side='left')
        self.tree.config(yscrollcommand=self.scroll.set)
        self.scroll.config(command=self.tree.yview)
        # Bind for tree double click item
        self.tree.bind("<ButtonRelease-1>", self.OnSingleClick)
        self.tree.bind("<<TreeviewSelect>>", self.OnSingleClick)
        self.tree.bind("<Double-1>", self.OnDoubleClick)
        self.tree.bind("<Return>", self.OnDoubleClick)
        self.tree.pack(side='left')

        self.film_lbl = Label(self.bot_frame_right, text="Enter film:", font=('David', 15, 'bold'), bg=blue_back_color,
                              fg=blue_front_color)
        self.film_lbl.pack(side='top')
        self.entry = Entry(self.bot_frame_right, width=30, font=('LilyUPC', 13, 'bold'), fg=blue_front_color, bg=entry_color)
        self.entry.pack(side='top')
        self.entry.focus()
        self.add_film_btn = Button(self.bot_frame_right, text="Add film", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                   width=25, command=self.add_film)
        self.add_film_btn.pack(side='top')

        self.add_file_btn = Button(self.bot_frame_right, text="Add file(s)", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                                   width=25, command=self.add_file)
        self.add_file_btn.pack(side='top')

        self.del_btn = Button(self.bot_frame_right, text="Delete record", font=('LilyUPC', 13, 'bold'), bg=light_purple,
                              width=25, command=self.delete_film)
        self.del_btn.pack(side='top')
        self.list_it()

        self.root.title(f"Features ({len(self.tree.get_children())})")

        self.root.mainloop()
        self.conn.close()
        print("Connection finished")

    def list_it(self):
        """Fill the TreeView with database fields"""
        self.tree.delete(*self.tree.get_children())
        self.c.execute(f"SELECT title, year, rating, my_rating, director, actors, generes, summary, cover, date FROM My_Films")
        rows = self.c.fetchall()
        for row in rows:
            self.tree.insert("", END, values=row)
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
        pic = Label(self.root, image=my_img)
        pic.pack(side='left')
        messagebox.showinfo(title=f"{item['values'][0]}", message=f"""
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
        """Called when user clicks element from TreeView"""
        print(f"OnSingleClick")
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.renew()
        with urllib.request.urlopen(item['values'][8]) as u:
            raw_data = u.read()
        image = Image.open(io.BytesIO(raw_data))
        my_img = ImageTk.PhotoImage(image)
        self.poster.configure(image=my_img)
        self.poster.image = my_img

    def renew(self):
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.entry.delete(0, "end")
        self.entry.insert(0, item['values'][0])

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
                                messagebox.showerror(title="Error", message=f"There is an error with the {film=}")
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
        if self.entry.get() == "" or self.entry.get().isspace():
            messagebox.showerror(title="Error", message='You should pick a title')
        else:
            film = self.entry.get().strip().lower()
            print(f"add_film:  {film=}")
            self.c.execute(f"SELECT title FROM My_Films")
            rows = self.c.fetchall()
            row = [item[0].lower() for item in rows]
            if film in row:
                messagebox.showerror(title="Error", message="The film is already in the list")
            else:
                try:
                    movies = self.moviesDB.search_movie(film)
                    id_film = movies[0].getID()
                    movie = self.moviesDB.get_movie(id_film)
                    title = movie['title']
                    year = movie['year']
                    rating = movie['rating']
                    my_rating = movie['rating']
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
                except:
                    messagebox.showerror(title="Error", message="There is an error with the film")
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

    def delete_film(self):
        """Delete selected film from database"""

        try:
            curItem = self.tree.focus()
            item = self.tree.item(curItem)
            mb = messagebox.askyesno(title="Warning", message=f"Are you sure you want to delete feature: "
                                     f"{(str(item['values'][0]))}?")
            if mb:
                self.c.execute(f"DELETE FROM My_Films where title = (?);",
                               (str(item['values'][0]),))
        except IndexError:
            messagebox.showinfo(title='Info', message='You should pick an entry')
            print("Index Error")
        self.conn.commit()
        self.list_it()
        self.root.title(f"Features ({len(self.tree.get_children())})")


if __name__ == "__main__":
    imdb = IMDBdataBase()

from tkinter import messagebox
from tkinter import *
from tkinter import ttk
import sqlite3
from imdb import Cinemagoer
from datetime import datetime


class IMDBdataBase:
    """Interface using Tkinter that has the API from IMDB to search the feature that is specified,
    enter the results into BBDD Sqlite3.
    https://gist.github.com/VictorLG98/30410204f175c278018a97dc5efbfe05
    https://www.youtube.com/watch?v=8PB3oFRkSeI
    """

    def __init__(self):
        # Set up main window
        self.window = Tk()
        self.window.config(pady=20, padx=20, bg='#3a4470')
        self.window.resizable(False, False)

        self.combo = ttk.Combobox(self.window, state="readonly",
                                  values=['2022', '2023'], font=('Comic Sans MS', 10, 'bold'),
                                  justify=CENTER)
        self.combo.grid(row=7, column=0)
        self.combo.current(0)
        self.year = datetime.now().year

        # self.window = ThemedTk(theme='plastik')
        # Set up second window
        self.new_win = Toplevel(self.window)
        self.new_win.title("Choose a film")
        self.new_win.resizable(False, False)
        self.new_win.config(pady=20, padx=20, bg='#378060')
        self.new_win.withdraw()
        self.new_win.protocol("WM_DELETE_WINDOW", self.on_closing)
        # IMDB API
        self.moviesDB = Cinemagoer()
        # Database
        self.conn = sqlite3.connect('IMDB_Films.db')
        print("Connection made on exit")
        self.c = self.conn.cursor()
        self.c.execute(f"CREATE TABLE if not exists Year{self.year}_Films(id integer PRIMARY KEY, title text, "
                       "year integer, rating real, my_rating real, director text, actors text, generes text, summary text, cover text, date text)")
        self.conn.commit()
        # Set up Tree style
        self.style = ttk.Style()
        # self.current_theme = self.style.theme_use('clam')

        self.style.configure("mystyle.Treeview.Heading", font=('Calibri', 12, 'bold'))
        self.tree = ttk.Treeview(style="mystyle.Treeview", selectmode=BROWSE)
        # Set up the columns
        self.tree['columns'] = ('Title', 'Year', 'Rating', 'MyRating', 'Director', 'Actors', 'Generes', 'Summary', 'Cover', 'Date')
        self.tree.column('#0', width=0, stretch=NO)
        self.tree.column('Title', width=200, minwidth=200, anchor=CENTER)
        self.tree.column('Year', width=80, minwidth=80, anchor=CENTER)
        self.tree.column('Rating', width=82, minwidth=82, anchor=CENTER)
        self.tree.column('MyRating', width=82, minwidth=82, anchor=CENTER)
        self.tree.column('Director', width=150, minwidth=150, anchor=CENTER)
        self.tree.column('Actors', width=250, minwidth=250, anchor=CENTER)
        self.tree.column('Generes', width=230, minwidth=230, anchor=CENTER)
        self.tree.column('Summary', width=350, minwidth=350, anchor=CENTER)
        self.tree.column('Cover', width=150, minwidth=150, anchor=CENTER)
        self.tree.column('Date', width=80, minwidth=80, anchor=CENTER)
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
        self.tree.heading('Date', text='Date', anchor=CENTER)

        self.scroll = Scrollbar(self.window, orient=VERTICAL)
        self.scroll.grid(row=0, column=1, sticky=NS)
        self.tree.config(yscrollcommand=self.scroll.set)
        self.scroll.config(command=self.tree.yview)
        # Bind for tree double click item
        self.tree.bind("<Double-1>", self.OnDoubleClick)
        self.tree.bind("<Return>", self.OnDoubleClick)

        self.tree.grid(row=0, column=0)
        self.film_lbl = Label(text="Enter film:", font=('David', 15, 'bold'), bg='#3a4470', fg='#477bc9')
        self.film_lbl.grid(row=1, column=0, pady=5)
        self.entry = Entry(width=30, font=('LilyUPC', 13, 'bold'), fg='#477bc9', bg='#2e3a4d')
        self.entry.grid(row=2, column=0)
        self.entry.focus()
        self.add_film_btn = Button(text="Add film", font=('LilyUPC', 13, 'bold'), bg='#7258db', width=25,
                                   command=self.add_film)
        self.add_film_btn.grid(row=3, column=0, pady=8)

        self.file_lbl = Label(text="Enter file:", font=('David', 15, 'bold'), bg='#3a4470', fg='#477bc9')
        self.file_lbl.grid(row=4, column=0, pady=5)
        self.file_entry = Entry(width=30, font=('LilyUPC', 13, 'bold'), fg='#477bc9', bg='#2e3a4d')
        self.file_entry.grid(row=5, column=0)
        self.file_entry.focus()
        self.add_file_btn = Button(text="Add file", font=('LilyUPC', 13, 'bold'), bg='#7258db', width=25,
                                   command=self.add_file)
        self.add_file_btn.grid(row=6, column=0, pady=8)


        self.del_btn = Button(text="Delete record", font=('LilyUPC', 13, 'bold'), bg='#7258db', width=25,
                              command=self.delete_film)
        self.del_btn.grid(row=7, column=0, pady=8)
        self.list_it()

        self.new_btn = Button(text="List features", font=('LilyUPC', 13, 'bold'), bg='#7258db', width=25,
                              command=self.win2)
        self.new_btn.grid(row=8, column=0, pady=8)
        self.list = Listbox(self.new_win, width=50, height=10, highlightthickness=0, font=('Andalus', 12, 'bold'),
                            selectmode=SINGLE, bg='#044f19', fg='#65eb8a', selectbackground='#aed6b9',
                            selectforeground='#68786d', selectborderwidth=3, activestyle=NONE)
        self.list.grid(row=1, column=0)
        self.scroll = Scrollbar(self.new_win, orient=VERTICAL)
        self.scroll.grid(row=1, column=3, sticky=NS, rowspan=7)
        self.scroll2 = Scrollbar(self.new_win, orient=HORIZONTAL)
        self.scroll2.grid(row=2, column=0, sticky=EW)
        self.list.config(yscrollcommand=self.scroll.set, xscrollcommand=self.scroll2.set)
        self.scroll.config(command=self.list.yview)
        self.scroll2.config(command=self.list.xview)
        # Bind for ListBox double click item
        self.list.bind('<Double-Button>', self.double_click)

        self.combo.bind("<<ComboboxSelected>>", self.cambioCombo)

        self.lbl = Label(self.new_win, text="Top 250 IMDB", font=('David', 20, 'bold'), bg='#378060', fg='#65eb8a')
        self.lbl.grid(row=0, column=0)
        self.label = Label(text=f'Viewed {len(self.tree.get_children())} features in {self.year}', bg='#3a4470',
                           font=('David', 12, 'bold'), fg='white')
        self.label.grid(row=9, column=0)
        self.window.title(f"Features viewed {self.year} -> ({len(self.tree.get_children())})")

        self.window.mainloop()
        self.conn.close()
        print("Connection finished")

    def cambioCombo(self, event):
        self.year = self.combo.get()
        try:
            self.list_it()
        except sqlite3.OperationalError:
            self.c.execute(f"CREATE TABLE if not exists Year{self.year}_Films(id integer PRIMARY KEY, title text, "
                           "year integer, rating real, my_rating real, director text, actors text, generes text, summary text, cover text, date text)")
            self.conn.commit()
        finally:
            self.list_it()

        self.window.title(f"Features viewed {self.year} -> ({len(self.tree.get_children())})")
        self.label.config(text=f'Viewed {len(self.tree.get_children())} features in {self.year}', bg='#3a4470',
                          font=('David', 12, 'bold'), fg='white')

    def double_click(self, event):
        """Called when user double clicks element from ListBox"""
        self.entry.delete(0, 'end')
        self.new_win.clipboard_clear()
        self.new_win.clipboard_append(self.list.get(self.list.curselection()))
        self.entry.insert(0, self.list.get(self.list.curselection()))
        messagebox.showinfo(title="Info", message=self.get_movie_info())

    def win2(self):
        """Called when user press 'List features' button to show up second window"""
        self.list.delete(0, 'end')
        self.window.grab_set()
        self.new_win.deiconify()

        top = self.moviesDB.get_top250_movies()
        self.list.insert('end', *top)

    def on_closing(self):
        """Called when user closes second window"""
        self.new_win.withdraw()

    def list_it(self):
        """Fill the TreeView with database fields"""
        self.tree.delete(*self.tree.get_children())
        self.c.execute(f"SELECT title, year, rating, my_rating, director, actors, generes, summary, cover, date FROM Year{self.year}_Films")
        rows = self.c.fetchall()
        for row in rows:
            self.tree.insert("", END, values=row)
        self.conn.commit()

    def OnDoubleClick(self, event):
        """Called when user double clicks element from TreeView"""
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.renew()

        messagebox.showinfo(title=f"{item['values'][0]}", message=f"""
Title: {item['values'][0]}\n
Year: {item['values'][1]}\n
Rating: {item['values'][2]}\n
MyRating: {item['values'][2]}\n
Director: {item['values'][3]}\n
Actors: {item['values'][4]}\n
Generes: {item['values'][5]}\n
Summary: {item['values'][6]}\n
Cover: {item['values'][7]}\n
Viewed: {item['values'][8]}
""")

    def renew(self):
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.entry.delete(0, "end")
        self.entry.insert(0, item['values'][0])

    def add_file(self):
        """Insert film fields to Database"""

    def add_film(self):
        """Insert film fields to Database"""
        if self.entry.get() == "" or self.entry.get().isspace():
            messagebox.showerror(title="Error", message='You should pick a title')
        else:
            film = self.entry.get().strip().lower()
            self.c.execute(f"SELECT title FROM Year{self.year}_Films")
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
                    self.c.execute(f"""INSERT INTO Year{self.year}_Films(title, year, rating, my_rating,
                                    director, actors, generes, summary, cover, date) VALUES(?,?,?,?,?,?,?,?,?,?);""",
                                   (str(title), int(year),
                                    float(rating), float(my_rating), str(directors[0]),
                                    str(sentence),
                                    str(genres), str(summary[0]), str(cover),
                                    str(datetime.today().strftime('%d/%m/%Y')) )),
                    self.list_it()
                except UnboundLocalError:
                    pass
            self.label.config(text=f'Viewed {len(self.tree.get_children())} features in {self.year}', bg='#3a4470',
                              font=('David', 12, 'bold'), fg='white')
            self.window.title(f"Features viewed {self.year} -> ({len(self.tree.get_children())})")
            self.conn.commit()

    def add_films_from_csv(self):
        self.entry.set('True Grit (1969)')
        self.add_film()


    def delete_film(self):
        """Delete selected film from database"""

        try:
            curItem = self.tree.focus()
            item = self.tree.item(curItem)
            mb = messagebox.askyesno(title="Warning", message=f"Are you sure you want to delete feature: "
                                     f"{(str(item['values'][0]))}?")
            if mb:
                self.c.execute(f"DELETE FROM Year{self.year}_Films where title = (?);",
                               (str(item['values'][0]),))
        except IndexError:
            messagebox.showinfo(title='Info', message='You should pick an entry')
            print("Index Error")
        self.conn.commit()
        self.list_it()
        self.label.config(text=f'Viewed {len(self.tree.get_children())} features in {self.year}', bg='#3a4470',
                          font=('David', 12, 'bold'), fg='white')
        self.window.title(f"Features viewed {self.year} -> ({len(self.tree.get_children())})")

    def get_movie_info(self):
        """Get selected movie info when users double click it"""
        film = self.list.get(self.list.curselection())

        movies = self.moviesDB.search_movie(film)
        id_film = movies[0].getID()
        movie = self.moviesDB.get_movie(id_film)
        title = movie['title']
        year = movie['year']
        rating = movie['rating']
        my_rating = rating
        directors = movie['directors']
        casting = movie['cast']
        summary = movie['summary']
        cover = movie['cover url']
        sentence = ""
        for cas in casting[0:5]:
            sentence += str(f'{cas}, ')
        generes = movie['genres']
        genres = ""
        for gen in generes:
            genres += str(f'{gen}, ')
        info = f"""
Title: {title}\n
Year: {year}\n
Rating: {rating}\n
MyRating: {my_rating}\n
Director: {directors[0]}\n
Actors: {sentence}\n
Generes: {genres}\n
Summary: {summary[0]}\n
Cover: {cover}"""
        return info


if __name__ == "__main__":
    imdb = IMDBdataBase()

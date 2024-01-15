import sys
from tkinter import messagebox
from tkinter import *
from tkinter import ttk
from ttkthemes import ThemedTk
import sqlite3
import imdb
from datetime import datetime


class IMDBdataBase:
    """Interfaz usando Tkinter que usa la API de IMDB para buscar la película que le especifiques,
     mostrar su información y añadirla a una BBDD Sqlite3."""

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
        self.ano = datetime.now().year

        # self.window = ThemedTk(theme='plastik')
        # Set up second window
        self.new_win = Toplevel(self.window)
        self.new_win.title("Elige una película")
        self.new_win.resizable(False, False)
        self.new_win.config(pady=20, padx=20, bg='#378060')
        self.new_win.withdraw()
        self.new_win.protocol("WM_DELETE_WINDOW", self.on_closing)
        # IMDB API
        self.moviesDB = imdb.IMDb()
        # Base de datos
        self.conn = sqlite3.connect('IMDB_Films.db')
        print("Conexión realizada con éxito")
        self.c = self.conn.cursor()
        self.c.execute(f"CREATE TABLE if not exists Year{self.ano}_Films(id integer PRIMARY KEY, titulo text, "
                       "ano integer, valoracion real, director text, actores text, generos text, resumen text, fecha text)")
        self.conn.commit()
        # Set up Tree style
        self.style = ttk.Style()
        # self.current_theme = self.style.theme_use('clam')

        self.style.configure("mystyle.Treeview.Heading", font=('Calibri', 12, 'bold'))
        self.tree = ttk.Treeview(style="mystyle.Treeview", selectmode=BROWSE)
        # Set up the columns
        self.tree['columns'] = ('Título', 'Año', 'Valoración', 'Director', 'Actores', 'Géneros', 'Resumen', 'Fecha')
        self.tree.column('#0', width=0, stretch=NO)
        self.tree.column('Título', width=200, minwidth=200, anchor=CENTER)
        self.tree.column('Año', width=80, minwidth=80, anchor=CENTER)
        self.tree.column('Valoración', width=82, minwidth=82, anchor=CENTER)
        self.tree.column('Director', width=150, minwidth=150, anchor=CENTER)
        self.tree.column('Actores', width=250, minwidth=250, anchor=CENTER)
        self.tree.column('Géneros', width=230, minwidth=230, anchor=CENTER)
        self.tree.column('Resumen', width=350, minwidth=350, anchor=CENTER)
        self.tree.column('Fecha', width=80, minwidth=80, anchor=CENTER)
        # Set up the headings
        self.tree.heading('#0', text='', anchor=CENTER)
        self.tree.heading('Título', text='Título', anchor=CENTER)
        self.tree.heading('Año', text='Año', anchor=CENTER)
        self.tree.heading('Valoración', text='Valoración', anchor=CENTER)
        self.tree.heading('Director', text='Director', anchor=CENTER)
        self.tree.heading('Actores', text='Actores', anchor=CENTER)
        self.tree.heading('Géneros', text='Géneros', anchor=CENTER)
        self.tree.heading('Resumen', text='Resumen', anchor=CENTER)
        self.tree.heading('Fecha', text='Fecha', anchor=CENTER)

        self.scroll = Scrollbar(self.window, orient=VERTICAL)
        self.scroll.grid(row=0, column=1, sticky=NS)
        self.tree.config(yscrollcommand=self.scroll.set)
        self.scroll.config(command=self.tree.yview)
        # Bind for tree double click item
        self.tree.bind("<Double-1>", self.OnDoubleClick)
        self.tree.bind("<Return>", self.OnDoubleClick)

        self.tree.grid(row=0, column=0)
        self.film_lbl = Label(text="Introduce la película:", font=('David', 15, 'bold'), bg='#3a4470', fg='#477bc9')
        self.film_lbl.grid(row=1, column=0, pady=5)
        self.entrada = Entry(width=30, font=('LilyUPC', 13, 'bold'), fg='#477bc9', bg='#2e3a4d')
        self.entrada.grid(row=2, column=0)
        self.entrada.focus()
        self.btn = Button(text="Añadir", font=('LilyUPC', 13, 'bold'), bg='#7258db', width=25, command=self.anadir_peli)
        self.btn.grid(row=3, column=0, pady=8)
        self.del_btn = Button(text="Borrar registro", font=('LilyUPC', 13, 'bold'), bg='#7258db', width=25,
                              command=self.borrar_peli)
        self.del_btn.grid(row=4, column=0, pady=8)
        self.listar()
        self.new_btn = Button(text="Listar películas", font=('LilyUPC', 13, 'bold'), bg='#7258db', width=25,
                              command=self.win2)
        self.new_btn.grid(row=5, column=0, pady=8)
        self.lista = Listbox(self.new_win, width=50, height=10, highlightthickness=0, font=('Andalus', 12, 'bold'),
                        selectmode=SINGLE, bg='#044f19', fg='#65eb8a', selectbackground='#aed6b9',
                        selectforeground='#68786d', selectborderwidth=3, activestyle=NONE)
        self.lista.grid(row=1, column=0)
        self.scroll = Scrollbar(self.new_win, orient=VERTICAL)
        self.scroll.grid(row=1, column=3, sticky=NS, rowspan=7)
        self.scroll2 = Scrollbar(self.new_win, orient=HORIZONTAL)
        self.scroll2.grid(row=2, column=0, sticky=EW)
        self.lista.config(yscrollcommand=self.scroll.set, xscrollcommand=self.scroll2.set)
        self.scroll.config(command=self.lista.yview)
        self.scroll2.config(command=self.lista.xview)
        # Bind for ListBox double click item
        self.lista.bind('<Double-Button>', self.double_click)

        self.combo.bind("<<ComboboxSelected>>", self.cambioCombo)

        self.lbl = Label(self.new_win, text="Top 250 IMDB", font=('David', 20, 'bold'), bg='#378060', fg='#65eb8a')
        self.lbl.grid(row=0, column=0)
        self.label = Label(text=f'Has visto {len(self.tree.get_children())} películas en {self.ano}', bg='#3a4470',
                           font=('David', 12, 'bold'), fg='white')
        self.label.grid(row=6, column=0)
        self.window.title(f"Pelis vistas {self.ano} -> ({len(self.tree.get_children())})")

        self.window.mainloop()
        self.conn.close()
        print("Conexión finalizada.")

    def cambioCombo(self, event):
        self.ano = self.combo.get()
        try:
            self.listar()
        except sqlite3.OperationalError:
            self.c.execute(f"CREATE TABLE if not exists Year{self.ano}_Films(id integer PRIMARY KEY, titulo text, "
                           "ano integer, valoracion real, director text, actores text, generos text, resumen text, fecha text)")
            self.conn.commit()
        finally:
            self.listar()

        self.window.title(f"Pelis vistas {self.ano} -> ({len(self.tree.get_children())})")
        self.label.config(text=f'Has visto {len(self.tree.get_children())} películas en {self.ano}', bg='#3a4470',
                          font=('David', 12, 'bold'), fg='white')

    def double_click(self, event):
        """Called when user double clicks element from ListBox"""
        self.entrada.delete(0, 'end')
        self.new_win.clipboard_clear()
        self.new_win.clipboard_append(self.lista.get(self.lista.curselection()))
        self.entrada.insert(0, self.lista.get(self.lista.curselection()))
        messagebox.showinfo(title="Info", message=self.get_movie_info())

    def win2(self):
        """Called when user press 'Listar películas' button to show up second window"""
        self.lista.delete(0, 'end')
        self.window.grab_set()
        self.new_win.deiconify()

        top = self.moviesDB.get_top250_movies()
        self.lista.insert('end', *top)

    def on_closing(self):
        """Called when user closes second window"""
        self.new_win.withdraw()

    def listar(self):
        """Fill the TreeView with database fields"""
        self.tree.delete(*self.tree.get_children())
        self.c.execute(f"SELECT titulo, ano, valoracion, director, actores, generos, resumen, fecha FROM Year{self.ano}_Films")
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
Título: {item['values'][0]}\n
Año: {item['values'][1]}\n
Valoración: {item['values'][2]}\n
Director: {item['values'][3]}\n
Actores: {item['values'][4]}\n
Géneros: {item['values'][5]}\n
Resumen: {item['values'][6]}\n
Vista en: {item['values'][7]}""")

    def renew(self):
        curItem = self.tree.focus()
        item = self.tree.item(curItem)
        self.entrada.delete(0, "end")
        self.entrada.insert(0, item['values'][0])

    def anadir_peli(self):
        """Insert film fields to Database"""
        if self.entrada.get() == "" or self.entrada.get().isspace():
            messagebox.showerror(title="Error", message='Debes introducir un título.')
        else:
            peli = self.entrada.get().strip().lower()
            self.c.execute(f"SELECT titulo FROM Year{self.ano}_Films")
            rows = self.c.fetchall()
            row = [item[0].lower() for item in rows]
            if peli in row:
                messagebox.showerror(title="Error", message="La película ya está en la lista.")
            else:
                try:
                    movies = self.moviesDB.search_movie(peli)
                    id_peli = movies[0].getID()
                    movie = self.moviesDB.get_movie(id_peli)
                    title = movie['title']
                    year = movie['year']
                    rating = movie['rating']
                    directors = movie['directors']
                    casting = movie['cast']
                    sentence = ""
                    for cas in casting[0:5]:
                        sentence += str(f'{cas}, ')
                    generos = movie['genres']
                    genres = ""
                    for gen in generos:
                        genres += str(f'{gen}, ')
                    plot = movie['plot']
                except:
                    messagebox.showerror(title="Error", message="Se ha producido un error con la película.")
                # Insertar en BBDD
                try:
                    self.c.execute(f"""INSERT INTO Year{self.ano}_Films(titulo, ano, valoracion,
                                            director, actores, generos, resumen, fecha) VALUES(?,?,?,?,?,?,?,?);""",
                                           (str(title), int(year),
                                            float(rating), str(directors[0]),
                                            str(sentence),
                                            str(genres), str(plot[0]),
                                            str(datetime.today().strftime('%d/%m/%Y')))),
                    self.listar()
                except UnboundLocalError:
                    pass
            self.label.config(text=f'Has visto {len(self.tree.get_children())} películas en {self.ano}', bg='#3a4470',
                           font=('David', 12, 'bold'), fg='white')
            self.window.title(f"Pelis vistas {self.ano} -> ({len(self.tree.get_children())})")
            self.conn.commit()

    def borrar_peli(self):
        """Delete selected film from database"""

        try:
            curItem = self.tree.focus()
            item = self.tree.item(curItem)
            mb = messagebox.askyesno(title="Atención!", message=f"¿Estás seguro de que deseas borrar la película: "
                                                                f"{(str(item['values'][0]))}?")
            if mb:
                self.c.execute(f"DELETE FROM Year{self.ano}_Films where titulo = (?);", (str(item['values'][0]),))
        except IndexError:
            messagebox.showinfo(title='Info', message='Debes seleccionar un registro')
            print("Index Error")
        self.conn.commit()
        self.listar()
        self.label.config(text=f'Has visto {len(self.tree.get_children())} películas en {self.ano}', bg='#3a4470',
                          font=('David', 12, 'bold'), fg='white')
        self.window.title(f"Pelis vistas {self.ano} -> ({len(self.tree.get_children())})")

    def get_movie_info(self):
        """Get selected movie info when users double click it"""
        peli = self.lista.get(self.lista.curselection())

        movies = self.moviesDB.search_movie(peli)
        id_peli = movies[0].getID()
        movie = self.moviesDB.get_movie(id_peli)
        title = movie['title']
        year = movie['year']
        rating = movie['rating']
        directors = movie['directors']
        casting = movie['cast']
        plot = movie['plot']
        sentence = ""
        for cas in casting[0:5]:
            sentence += str(f'{cas}, ')
        generos = movie['genres']
        genres = ""
        for gen in generos:
            genres += str(f'{gen}, ')
        info = f"""
Título: {title}\n
Año: {year}\n
Valoración: {rating}\n
Director: {directors[0]}\n
Actores: {sentence}\n
Géneros: {genres}\n
Resumen: {plot[0]}"""
        return info


if __name__ == "__main__":
    imdb = IMDBdataBase()

# From https://stackoverflow.com/questions/62692920/search-items-in-treeview-in-tkinter-python
import tkinter as tk
from tkinter import ttk


def add():
    value = add_entry.get()
    values.append(value)
    tree.insert("", tk.END, values=(f'#{len(values)}', value, 'more', 'moar'))


def search():
    query = search_entry.get()
    selections = []
    for child in tree.get_children():
        # low case the entire dictionary entry
        if query.lower() in tree.item(child)['values'].lower():   # compare strings in  lower cases.
            print(tree.item(child)['values'])
            selections.append(child)
    print('search completed')
    tree.selection_set(selections)


values = []

root = tk.Tk()
root.title("Medicine database")

lb1 = tk.Label(root, text="Search:")
lb1.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)
search_entry = tk.Entry(root, width=15)
search_entry.grid(row=0, column=1, padx=10, pady=10, sticky=tk.E, rowspan=1)
btn = tk.Button(root, text="search", width=10, command=search)
btn.grid(row=0, column=0, padx=10, pady=10, rowspan=2)

add_lb = tk.Label(root, text="add:")
add_lb.grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)
add_entry = tk.Entry(root, width=15)
add_entry.grid(row=1, column=1, padx=10, pady=10, sticky=tk.E, rowspan=1)
btn1 = tk.Button(root, text="add", width=10, command=add)
btn1.grid(row=1, column=0, padx=10, pady=10, rowspan=2)

# treeview
tree = ttk.Treeview(root, height=25)
tree["columns"] = ("one", "two", "three", "four")
tree.column("one", width=120)
tree.column("two", width=160)
tree.column("three", width=130)
tree.column("four", width=160)
tree.heading("one", text="Numer seryjny leku")
tree.heading("two", text="Nazwa Leku")
tree.heading("three", text="Ampułki/Tabletki")
tree.heading("four", text="Data ważności")
tree["show"] = "headings"
tree.grid(row=0, column=2, rowspan=6, pady=20)

root.geometry("840x580")


if __name__ == '__main__':

    root.mainloop()

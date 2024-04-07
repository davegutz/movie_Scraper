import tkinter as tk
from tkinter import ttk


def ignore_articles(text):
    articles = ['the', 'a', 'an', 'la', "l'", 'le', 'les', 'el', 'lo', 'las', 'los']
    for article in articles:
        if text.lower().startswith(article + ' '):
            return text[len(article)+1:].strip()
    return text


def title_sort(tree, column):
    data = [(ignore_articles(tree.set(child, column)), child) for child in tree.get_children('')]
    data.sort()
    for index, (_, child) in enumerate(data):
        tree.move(child, '', index)


def main():
    root = tk.Tk()
    root.title("Sort Treeview Example")

    tree = ttk.Treeview(root)
    tree['columns'] = ('num', 'title',)
    tree.heading("#0", text="ID")
    tree.heading("num", text="Num")
    tree.heading("title", text="Title")
    title_column = 1

    data = [("1", "The Apple"),
            ("2", "An Orange"),
            ("3", "Banana"),
            ("4", "A Mango"),
            ("5", "Les Miserables"),
            ("6", "El Lobo"),
            ("7", "L' Enfant")]

    for item in data:
        print(f"{item=}")
        tree.insert('', 'end', iid=item[0], values=item)

    tree.grid(column=0, row=0, sticky='nsew')
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=1)

    sort_button = tk.Button(root, text="Sort", command=lambda: title_sort(tree, title_column))
    sort_button.grid(column=0, row=1)

    title_sort(tree, title_column)
    root.mainloop()


if __name__ == "__main__":
    main()

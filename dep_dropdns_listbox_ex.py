from tkinter import *
from tkinter import ttk
root = Tk()
root.title('Codemy.com')
root.geometry("500x400")

# Create list of sizes
sizes = ["Small", "Medium", "Large"]
small_colors = ["Red", "Green", "Blue", "Black"]
medium_colors = ["Red", "Green"]
large_colors = ["Blue", "Black"]


def pick_color(_e):
    if my_combo.get() == "Small":
        color_combo.config(values=small_colors)
        color_combo.current(0)
    if my_combo.get() == "Medium":
        color_combo.config(values=medium_colors)
        color_combo.current(0)
    if my_combo.get() == "Large":
        color_combo.config(values=large_colors)
        color_combo.current(0)


# Create a drop box
my_combo = ttk.Combobox(root, values=sizes)
my_combo.current(0)
my_combo.pack(pady=20)

# Bind the combobox
my_combo.bind("<<ComboboxSelected>>", pick_color)

# Color Combo box
color_combo = ttk.Combobox(root, values=[" "])
color_combo.current(0)
color_combo.pack(pady=20)

# Frame
my_frame = Frame(root)
my_frame.pack(pady=50)

# List boxes
my_list1 = Listbox(my_frame)
my_list2 = Listbox(my_frame)
my_list1.grid(row=0, column=0)
my_list2.grid(row=0, column=1, padx=20)


def list_color(_e):
    my_list2.delete(0, END)
    if my_list1.get(ANCHOR) == "Small":
        for item in small_colors:
            my_list2.insert(END, item)
    if my_list1.get(ANCHOR) == "Medium":
        for item in medium_colors:
            my_list2.insert(END, item)
    if my_list1.get(ANCHOR) == "Large":
        for item in large_colors:
            my_list2.insert(END, item)


# Add items
for item_ in sizes:
    my_list1.insert(END, item_)

# Bind the Lisbox
my_list1.bind("<<ListboxSelect>>", list_color)

root.mainloop()

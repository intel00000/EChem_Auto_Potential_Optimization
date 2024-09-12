import tkinter as tk
from tkinter import ttk

# A non-blocking messagebox using TopLevel
def non_blocking_messagebox(title, message) -> None:
    top = tk.Toplevel()
    top.title(title)

    label = ttk.Label(top, text=message)
    label.pack(padx=20, pady=20)

    button = ttk.Button(top, text="OK", command=top.destroy)
    button.pack(pady=10)

    # set the message at the center of the parent window
    top.geometry(f"+{top.winfo_screenwidth()//2}+{top.winfo_screenheight()//2}")

    top.attributes("-topmost", True)

# Example usage in the main loop
def example_function():
    non_blocking_messagebox("Info", "This is a non-blocking message box!")
    # Main loop continues here
    print("Main loop continues...")

root = tk.Tk()
example_function()
root.mainloop()
import tkinter as tk
from tkinter import ttk
import logging
from helper_functions import resource_path


def non_blocking_messagebox(
    parent, title, message, icon_path=resource_path("icons-red.ico")
):
    """Create a non-blocking message box."""
    try:
        top = tk.Toplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)
        label = ttk.Label(top, text=message)
        label.grid(row=0, column=0, padx=10, pady=10)

        button = ttk.Button(top, text="OK", command=top.destroy)
        button.grid(row=1, column=0, padx=10, pady=10)
        top.attributes("-topmost", True)
        top.grab_release()
        top.update_idletasks()
        top.wait_visibility()
        top.geometry(
            f"+{top.winfo_screenwidth()//2 - top.winfo_width()//2}+{top.winfo_screenheight()//2 - top.winfo_height()//2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking message box: {e}")


def non_blocking_custom_messagebox(
    parent, title, message, buttons, callback, icon_path=resource_path("icons-red.ico")
):
    """Create a non-blocking custom message box with multiple buttons."""
    try:
        top = tk.Toplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)
        label = ttk.Label(top, text=message)
        label.grid(row=0, column=0, columnspan=len(buttons), padx=10, pady=10)

        def handle_click(response):
            top.destroy()
            callback(response)

        for i, button_text in enumerate(buttons):
            ttk.Button(
                top,
                text=button_text,
                command=lambda response=button_text: handle_click(response),
            ).grid(row=1, column=i, padx=10, pady=10)

        top.attributes("-topmost", True)
        top.grab_release()
        top.update_idletasks()
        top.wait_visibility()
        top.geometry(
            f"+{top.winfo_screenwidth()//2 - top.winfo_width()//2}+{top.winfo_screenheight()//2 - top.winfo_height()//2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking custom message box: {e}")


def non_blocking_checklist(parent, title, items, callback, icon_path=None):
    """Create a non-blocking checklist dialog without a scroll bar."""
    try:
        top = tk.Toplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)

        # Label for the checklist
        label = ttk.Label(top, text="Checklist:")
        label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

        # Frame to hold the checklist items
        checklist_frame = ttk.Frame(top)
        checklist_frame.grid(
            row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew"
        )

        # Add checkboxes for each item
        check_vars = []
        for item in items:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(checklist_frame, text=item, variable=var)
            cb.pack(anchor="center", padx=5, pady=2)
            check_vars.append((item, var))

        # Buttons for confirmation
        def on_ok():
            selected = [item for item, var in check_vars if var.get()]
            top.destroy()
            callback(selected)

        def on_cancel():
            top.destroy()
            callback([])

        ok_button = ttk.Button(top, text="OK", command=on_ok)
        ok_button.grid(row=2, column=0, padx=10, pady=10, sticky="e")
        cancel_button = ttk.Button(top, text="Cancel", command=on_cancel)
        cancel_button.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        top.attributes("-topmost", True)
        top.grab_release()
        top.update_idletasks()
        top.wait_visibility()
        top.geometry(
            f"+{top.winfo_screenwidth()//2 - top.winfo_width()//2}+{top.winfo_screenheight()//2 - top.winfo_height()//2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking checklist: {e}")
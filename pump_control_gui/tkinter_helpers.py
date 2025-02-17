import os
import json
import logging
from helper_functions import resource_path

import tkinter as tk
from tkinter import ttk

default_icon_path = resource_path(os.path.join("icons", "icons-red.ico"))


def non_blocking_messagebox(parent, title, message, icon_path=default_icon_path):
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
            f"+{top.winfo_screenwidth() // 2 - top.winfo_width() // 2}+{top.winfo_screenheight() // 2 - top.winfo_height() // 2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking message box: {e}")


def non_blocking_custom_messagebox(
    parent, title, message, buttons, callback, icon_path=default_icon_path
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
            f"+{top.winfo_screenwidth() // 2 - top.winfo_width() // 2}+{top.winfo_screenheight() // 2 - top.winfo_height() // 2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking custom message box: {e}")


def non_blocking_checklist(
    parent, title, message, items, result_var, icon_path=default_icon_path
):
    """Create a non-blocking checklist dialog without a scroll bar."""
    try:
        top = tk.Toplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)

        # Label for the checklist
        label = ttk.Label(top, text=message)
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

        # OK and Cancel Buttons
        def on_ok():
            selected = [item for item, var in check_vars if var.get()]
            result_var.set(
                ",".join(selected)
            )  # Update the shared variable with the selected items
            top.destroy()

        def on_cancel():
            result_var.set("")  # Set an empty value if canceled
            top.destroy()

        ok_button = ttk.Button(top, text="OK", command=on_ok)
        ok_button.grid(row=2, column=0, padx=10, pady=10, sticky="e")
        cancel_button = ttk.Button(top, text="Cancel", command=on_cancel)
        cancel_button.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        top.protocol("WM_DELETE_WINDOW", on_cancel)
        top.attributes("-topmost", True)
        top.grab_release()
        top.update_idletasks()
        top.wait_visibility()
        top.geometry(
            f"+{top.winfo_screenwidth() // 2 - top.winfo_width() // 2}+{top.winfo_screenheight() // 2 - top.winfo_height() // 2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking checklist: {e}")


def non_blocking_single_select(
    parent, title, items, result_var, icon_path=default_icon_path
):
    """Create a non-blocking single selection dialog using radio buttons."""
    try:
        top = tk.Toplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)

        # Label for the selection
        label = ttk.Label(top, text="Select a controller:")
        label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

        # Frame to hold the radio buttons
        radio_frame = ttk.Frame(top)
        radio_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

        # Create a StringVar to hold the selection internally
        selection_var = tk.StringVar()

        # Add radio buttons for each item
        for item in items:
            rb = ttk.Radiobutton(
                radio_frame, text=item, value=item, variable=selection_var
            )
            rb.pack(anchor="center", padx=5, pady=2)

        # OK and Cancel Buttons
        def on_ok():
            result_var.set(selection_var.get())  # Update the external result_var
            top.destroy()

        def on_cancel():
            result_var.set("")  # Set an empty value if canceled
            top.destroy()

        top.protocol("WM_DELETE_WINDOW", on_cancel)
        ok_button = ttk.Button(top, text="OK", command=on_ok)
        ok_button.grid(row=2, column=0, padx=10, pady=10, sticky="e")
        cancel_button = ttk.Button(top, text="Cancel", command=on_cancel)
        cancel_button.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        top.attributes("-topmost", True)
        top.grab_release()
        top.update_idletasks()
        top.wait_visibility()
        top.geometry(
            f"+{top.winfo_screenwidth() // 2 - top.winfo_width() // 2}+{top.winfo_screenheight() // 2 - top.winfo_height() // 2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking single selection dialog: {e}")


def non_blocking_input_dialog(
    parent, title, fields, result_var, icon_path=default_icon_path
):
    """
    A non-blocking dialog to gather multiple inputs with support for text entry and dropdown.
    """
    try:
        top = tk.Toplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)

        input_vars = {}

        # Create a frame for the form
        form_frame = ttk.Frame(top)
        form_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

        # Generate input fields
        for i, field in enumerate(fields):
            ttk.Label(form_frame, text=f"{field['label']}:").grid(
                row=i, column=0, sticky="e", padx=5, pady=5
            )
            input_var = tk.StringVar()
            input_var.set(field.get("initial_value", ""))

            if field["type"] == "dropdown":
                # Dropdown box
                dropdown = ttk.Combobox(
                    form_frame,
                    textvariable=input_var,
                    values=field["choices"],
                    state="readonly",
                )
                dropdown.grid(row=i, column=1, sticky="w", padx=5, pady=5)
            elif field["type"] == "text":
                # Text entry
                entry = ttk.Entry(form_frame, textvariable=input_var)
                entry.grid(row=i, column=1, sticky="w", padx=5, pady=5)
            input_vars[field["label"]] = input_var

        # OK and Cancel buttons
        def on_ok():
            inputs = {label: var.get() for label, var in input_vars.items()}
            result_var.set(json.dumps(inputs))  # Store inputs as JSON in the result_var
            top.destroy()

        def on_cancel():
            result_var.set("")  # Clear the result_var if canceled
            top.destroy()

        ok_button = ttk.Button(top, text="OK", command=on_ok)
        ok_button.grid(row=1, column=0, padx=10, pady=10, sticky="e")
        cancel_button = ttk.Button(top, text="Cancel", command=on_cancel)
        cancel_button.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        top.protocol("WM_DELETE_WINDOW", on_cancel)
        top.attributes("-topmost", True)
        top.grab_release()
        top.update_idletasks()
        top.wait_visibility()
        top.geometry(
            f"+{top.winfo_screenwidth() // 2 - top.winfo_width() // 2}+{top.winfo_screenheight() // 2 - top.winfo_height() // 2}"
        )
    except Exception as e:
        logging.error(f"Error creating non-blocking input dialog: {e}")

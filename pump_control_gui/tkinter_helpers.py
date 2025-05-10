import os
import json
import logging
from helper_functions import resource_path

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

default_icon_path = resource_path(os.path.join("icons", "icons-red.ico"))


global_pad_x = 2
global_pad_y = 2

global_pad_N = 3
global_pad_S = 3
global_pad_W = 3
global_pad_E = 3

global_height = 24


def combobox(
    parent,
    row,
    column,
    values=[],
    command=None,
    state="normal",
    width=200,
    height=global_height,
    rowspan=1,
    columnspan=1,
    padx=global_pad_x,
    pady=global_pad_y,
    sticky="NSEW",
) -> ctk.CTkComboBox:
    """
    Create a combobox with specified parameters.

    @param parent: The parent widget.
    @param row: The row in the grid where the combobox will be placed.
    @param column: The column in the grid where the combobox will be placed.
    @param values: The list of values for the combobox (default is empty).
    @param command: The function to call when the selection changes.
    @param state: The state of the combobox (default is "normal").
    @param width: The width of the combobox (default is 200).
    @param height: The height of the combobox (default is 20).
    @param rowspan: The number of rows the combobox will span (default is 1).
    @param columnspan: The number of columns the combobox will span (default is 1).
    @param padx: The horizontal padding around the combobox (default is global_pad_x).
    @param pady: The vertical padding around the combobox (default is global_pad_y).
    @param sticky: The sticky option for the combobox (default is "NSEW").

    @return: The created combobox widget.
    """
    combo = ctk.CTkComboBox(
        parent,
        values=values,
        command=command,
        state=state,
        width=width,
        height=height,
    )
    combo.grid(
        row=row,
        rowspan=rowspan,
        column=column,
        columnspan=columnspan,
        padx=padx,
        pady=pady,
        sticky=sticky,
    )
    return combo


def button(
    parent,
    text,
    row,
    column,
    command,
    state="normal",
    width=120,
    height=global_height,
    rowspan=1,
    columnspan=1,
    padx=global_pad_x,
    pady=global_pad_y,
    sticky="NSEW",
) -> ctk.CTkButton:
    """
    Create a button with specified parameters.

    @param parent: The parent widget.
    @param text: The text to display on the button.
    @param row: The row in the grid where the button will be placed.
    @param column: The column in the grid where the button will be placed.
    @param command: The function to call when the button is clicked.
    @param rowspan: The number of rows the button will span (default is 1).
    @param columnspan: The number of columns the button will span (default is 1).
    @param padx: The horizontal padding around the button (default is global_pad_x).
    @param pady: The vertical padding around the button (default is global_pad_y).
    @param sticky: The sticky option for the button (default is "NSEW").

    @return: The created button widget.
    """
    button = ctk.CTkButton(
        parent, text=text, command=command, width=width, height=height, state=state
    )
    button.grid(
        row=row,
        rowspan=rowspan,
        column=column,
        columnspan=columnspan,
        padx=padx,
        pady=pady,
        sticky=sticky,
    )
    return button


def label(
    parent,
    text,
    row,
    column,
    rowspan=1,
    columnspan=1,
    width=0,
    height=global_height,
    padx=global_pad_x,
    pady=global_pad_y,
    sticky="NSEW",
) -> ctk.CTkLabel:
    """
    Create a label with specified parameters.

    @param parent: The parent widget.
    @param text: The text to display on the label.
    @param row: The row in the grid where the label will be placed.
    @param column: The column in the grid where the label will be placed.
    @param rowspan: The number of rows the label will span (default is 1).
    @param columnspan: The number of columns the label will span (default is 1).
    @param padx: The horizontal padding around the label (default is global_pad_x).
    @param pady: The vertical padding around the label (default is global_pad_y).
    @param sticky: The sticky option for the label (default is "NSEW").

    @return: The created label widget.
    """
    label = ctk.CTkLabel(parent, text=text, width=width, height=height)
    label.grid(
        row=row,
        rowspan=rowspan,
        column=column,
        columnspan=columnspan,
        padx=padx,
        pady=pady,
        sticky=sticky,
    )
    return label


def non_blocking_messagebox(parent, title, message, icon_path=default_icon_path):
    """Create a non-blocking message box."""
    try:
        top = ctk.CTkToplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)
        frame = ctk.CTkFrame(top)
        frame.grid(row=0, column=0, ipadx=global_pad_x, ipady=global_pad_y)
        label(
            frame,
            text=message,
            row=0,
            column=0,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NS",
        )
        button(
            frame,
            text="OK",
            row=1,
            column=0,
            command=top.destroy,
            width=60,
            height=global_height,
            sticky="NS",
        )
        # center it on the screen
        top.attributes("-topmost", True)
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
        top = ctk.CTkToplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)
        frame = ctk.CTkFrame(top)
        frame.grid(row=0, column=0, ipadx=global_pad_x, ipady=global_pad_y)
        label(
            frame,
            text=message,
            row=0,
            column=0,
            columnspan=len(buttons),
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NS",
        )

        # Button handlers
        def handle_click(response):
            top.destroy()
            callback(response)

        for i, button_text in enumerate(buttons):
            button(
                frame,
                text=button_text,
                command=lambda response=button_text: handle_click(response),
                row=1,
                column=i,
                width=60,
                height=global_height,
                padx=global_pad_x,
                pady=global_pad_y,
                sticky="NS",
            )

        top.attributes("-topmost", True)
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
        top = ctk.CTkToplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)
        frame = ctk.CTkFrame(top)
        frame.grid(row=0, column=0, ipadx=global_pad_x, ipady=global_pad_y)

        # Label for the checklist
        label(
            frame,
            text=message,
            row=0,
            column=0,
            columnspan=2,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NS",
        )
        # Frame to hold the checklist items
        checklist_frame = ctk.CTkFrame(frame)
        checklist_frame.grid(
            row=1,
            column=0,
            columnspan=2,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # Add checkboxes for each item
        check_vars = []
        for item in items:
            var = tk.BooleanVar()
            cb = ctk.CTkCheckBox(checklist_frame, text=item, variable=var)
            cb.pack(anchor="center", padx=global_pad_x, pady=global_pad_y)
            check_vars.append((item, var))

        # OK and Cancel Buttons
        def on_ok():
            selected = [item for item, var in check_vars if var.get()]
            # Update the shared variable with the selected items
            result_var.set(",".join(selected))
            top.destroy()

        def on_cancel():
            result_var.set("")  # Set an empty value if canceled
            top.destroy()

        button(
            frame,
            text="OK",
            command=on_ok,
            width=60,
            height=global_height,
            row=2,
            column=0,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NS",
        )
        button(
            frame,
            text="Cancel",
            command=on_cancel,
            width=60,
            height=global_height,
            row=2,
            column=1,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NS",
        )

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
        top = ctk.CTkToplevel(parent)
        top.title(title)
        if icon_path:
            top.iconbitmap(icon_path)
        frame = ctk.CTkFrame(top)
        frame.grid(
            row=1,
            column=0,
            columnspan=2,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # Label for the selection
        label(
            frame,
            text="Select a controller:",
            row=0,
            column=0,
            columnspan=2,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NS",
        )

        # Frame to hold the radio buttons
        radio_frame = ctk.CTkFrame(frame)
        radio_frame.grid(
            row=1,
            column=0,
            columnspan=2,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # Create a StringVar to hold the selection internally
        selection_var = ctk.StringVar()

        # Add radio buttons for each item
        for item in items:
            rb = ctk.CTkRadioButton(
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

        button(
            frame,
            "OK",
            2,
            0,
            on_ok,
            width=60,
            sticky="NS",
        )
        button(
            frame,
            "Cancel",
            2,
            1,
            on_cancel,
            width=60,
            sticky="NS",
        )

        top.protocol("WM_DELETE_WINDOW", on_cancel)
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

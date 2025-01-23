import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import pandas as pd
import xml.etree.ElementTree as ET
from helper_func import generate_gsequence
from collections import OrderedDict


global_pad_N = 3
global_pad_S = 3
global_pad_W = 3
global_pad_E = 3

local_pad_x = 2
local_pad_y = 2


class GSequenceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GSequence Generator")

        self.file_history = (
            OrderedDict()
        )  # Files history, key is the file name, value is the list of sheets

        # Main Frame
        self.main_frame = ttk.Labelframe(
            root,
            text="GSequence Generator",
            padding=(global_pad_N, global_pad_E, global_pad_S, global_pad_W),
        )
        self.main_frame.grid(
            row=0, column=0, padx=local_pad_x, pady=local_pad_y, sticky="NSEW"
        )

        current_row = 0  # Row Counter

        # Excel File Selection Frame
        self.file_select_frame = ttk.Labelframe(
            self.main_frame,
            text="Select Excel File",
            padding=(global_pad_N, global_pad_E, global_pad_S, global_pad_W),
        )
        self.file_select_frame.grid(
            row=current_row,
            column=0,
            columnspan=1,
            padx=local_pad_x,
            pady=local_pad_y,
            sticky="NSEW",
        )
        current_row += 1

        self.file_path = tk.StringVar()
        ttk.Label(self.file_select_frame, text="File Path:      ").grid(
            row=0,
            column=0,
            padx=local_pad_x,
            pady=local_pad_y,
            sticky="W",
            columnspan=1,
        )
        self.file_entry = ttk.Combobox(
            self.file_select_frame,
            textvariable=self.file_path,
            values=list(self.file_history.keys()),
            width=40,
        )
        # bind to self.on_file_change
        self.file_entry.bind("<<ComboboxSelected>>", self.update_sheet_dropdown)
        self.file_entry.grid(
            row=0, column=1, padx=local_pad_x, pady=local_pad_y, sticky="EW"
        )
        self.file_browse_button = ttk.Button(
            self.file_select_frame, text="Browse", command=self.browse_file
        )
        self.file_browse_button.grid(
            row=0, column=2, padx=local_pad_x, pady=local_pad_y, sticky="W"
        )

        # Sheet Name Selection Frame
        self.sheet_select_frame = ttk.Labelframe(
            self.main_frame,
            text="Select Sheet:",
            padding=(global_pad_N, global_pad_E, global_pad_S, global_pad_W),
        )
        self.sheet_select_frame.grid(
            row=current_row,
            column=0,
            columnspan=1,
            padx=local_pad_x,
            pady=local_pad_y,
            sticky="NSEW",
        )
        current_row += 1

        self.sheet_name = tk.StringVar(value="")
        ttk.Label(self.sheet_select_frame, text="Sheet Name:").grid(
            row=0,
            column=0,
            padx=local_pad_x,
            pady=local_pad_y,
            sticky="W",
            columnspan=1,
        )
        self.sheet_dropdown = ttk.Combobox(
            self.sheet_select_frame, textvariable=self.sheet_name, width=40
        )
        self.sheet_dropdown.grid(
            row=0, column=1, padx=local_pad_x, pady=local_pad_y, sticky="EW"
        )

        # Convert Button Frame
        self.convert_frame = ttk.Frame(self.main_frame)
        self.convert_frame.grid(
            row=current_row,
            column=0,
            columnspan=1,
            padx=local_pad_x,
            pady=local_pad_y,
            sticky="EW",
        )
        current_row += 1

        self.convert_button = ttk.Button(
            self.convert_frame,
            text="Convert to GSequence",
            command=self.convert_to_gsequence,
        )
        self.convert_button.pack(pady=local_pad_y * 3)

        # Make the main frame expandable
        self.main_frame.columnconfigure(1, weight=1)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if file_path:
            self.file_path.set(file_path)
            self.update_file_history(file_path)
            self.load_sheets(file_path)

    def update_file_history(self, file_path):
        """Update the history of file paths."""
        if file_path not in self.file_history:
            self.file_history[file_path] = []
            # Limit the history to the last 10 entries
            if len(self.file_history) > 10:
                self.file_history.popitem(last=False)
            # Update the combobox values
            self.file_entry["values"] = list(self.file_history.keys())
            self.file_entry.set(file_path)

    def load_sheets(self, file_path):
        try:
            xl = pd.ExcelFile(file_path)
            self.file_history[file_path] = xl.sheet_names
            self.sheet_dropdown["values"] = xl.sheet_names
            if "export_GSequence" in xl.sheet_names:
                self.sheet_name.set("export_GSequence")
            else:
                self.sheet_name.set(str(xl.sheet_names[0]))
        except Exception as e:
            messagebox.showerror("Error", f"Error loading sheets: {e}")

    def update_sheet_dropdown(self, event):
        file_path = self.file_path.get()
        if file_path:
            self.load_sheets(file_path)

    def convert_to_gsequence(self):
        excel_path = self.file_path.get()
        sheet_name = self.sheet_name.get()
        if not excel_path:
            messagebox.showerror("Error", "Please select an Excel file.")
            return
        if not sheet_name:
            messagebox.showerror("Error", "Please select a sheet name.")
            return

        try:
            # Generate GSequence
            new_method_tree = generate_gsequence(
                excel_path, sheet_name, "combined_sequencer_methods.xml"
            )
            if new_method_tree is not None:
                messagebox.showinfo(
                    "Success",
                    "GSequence generated successfully, select a save location.",
                )
                # Save the file
                save_path = filedialog.asksaveasfilename(
                    title="Save GSequence File",
                    defaultextension=".xml",
                    filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
                )
                if save_path:
                    new_method_tree.write(
                        save_path, encoding="utf-8", xml_declaration=True
                    )
                    messagebox.showinfo("Success", f"GSequence saved to {save_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Error generating GSequence: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = GSequenceApp(root)
    root.mainloop()

from calendar import c
import os
import re
import sys
import shutil
import requests

# gui imports
import tkinter as tk
import tkinter_helpers
import customtkinter as ctk
from tkinter import filedialog

from tkinterdnd2 import DND_FILES, TkinterDnD

# Constants
UF2_INFO_FILENAME = "INFO_UF2.TXT"
VARIANT_URL = "https://raw.githubusercontent.com/thonny/thonny/master/data/micropython-variants-uf2.json"


def list_volumes():
    volumes = {}
    if sys.platform.startswith("win"):
        import string
        from ctypes import windll

        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:/"
                uf2_info_path = os.path.join(drive, UF2_INFO_FILENAME)
                if os.path.exists(uf2_info_path):
                    with open(uf2_info_path, "r") as f:
                        uf2_info = f.read()
                        # look for line started with model
                        for line in uf2_info.splitlines():
                            if line.upper().startswith("MODEL"):
                                model = line.split(":")[1].strip()
                                volumes[drive] = model
                                break
            bitmask >>= 1
    else:
        for mount_point in ["/media", "/Volumes"]:
            if os.path.exists(mount_point):
                for entry in os.listdir(mount_point):
                    path = os.path.join(mount_point, entry)
                    if os.path.isdir(path) and os.path.exists(
                        os.path.join(path, UF2_INFO_FILENAME)
                    ):
                        with open(os.path.join(path, UF2_INFO_FILENAME), "r") as f:
                            uf2_info = f.read()
                            # look for line started with model
                            for line in uf2_info.splitlines():
                                if line.upper().startswith("MODEL"):
                                    model = line.split(":")[1].strip()
                                    volumes[model] = path
                                    break
    return volumes


def flash_uf2(uf2_path, target_volume):
    try:
        shutil.copy(uf2_path, os.path.join(target_volume, os.path.basename(uf2_path)))
        return True
    except Exception as e:
        print(f"Error flashing UF2: {e}")
        return False


def download_uf2(url, destination):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(destination, "wb") as f:
            shutil.copyfileobj(response.raw, f)
        return True
    except Exception as e:
        print(f"Error downloading UF2: {e}")
        return False


class TkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class PicoFlasherApp:
    def __init__(self, master):
        self.master = master
        self.master.title(
            "Raspberry Pi Pico Flasher (Drag and drop a UF2 file into the window)"
        )
        self.variants = []
        self.selected_variant = None

        self.main_frame = ctk.CTkFrame(self.master)
        self.main_frame.pack(padx=10, pady=10)
        self.main_frame.drop_target_register(DND_FILES)
        self.main_frame.dnd_bind("<<Drop>>", self.drop)

        tkinter_helpers.label(
            self.main_frame,
            "Device:",
            0,
            0,
        )
        self.device_var = ctk.StringVar(value="Select a device")
        self.device_combobox = tkinter_helpers.combobox(
            self.main_frame,
            0,
            1,
            state="readonly",
            command=self.on_device_selected,
            width=150,
        )
        self.device_combobox.configure(variable=self.device_var)
        self.refresh_button = tkinter_helpers.button(
            self.main_frame,
            "Refresh",
            0,
            2,
            self.refresh_devices,
        )

        tkinter_helpers.label(
            self.main_frame,
            "Variant:",
            1,
            0,
        )
        self.variant_var = ctk.StringVar(value="Select a variant")
        self.variant_dropdown = tkinter_helpers.combobox(
            self.main_frame,
            1,
            1,
            state="readonly",
            command=self.on_variant_selected,
            width=150,
        )
        self.variant_dropdown.configure(variable=self.variant_var)
        self.upload_custom_uf2_button = tkinter_helpers.button(
            self.main_frame,
            "Upload",
            1,
            2,
            self.flash_custom_uf2,
        )

        self.version_label = tkinter_helpers.label(
            self.main_frame,
            "Firmware version:",
            2,
            0,
        )
        self.version_var = ctk.StringVar(value="Select a version")
        self.version_dropdown = tkinter_helpers.combobox(
            self.main_frame,
            2,
            1,
            state="readonly",
            width=150,
        )
        self.version_dropdown.configure(variable=self.version_var)
        self.download_button = tkinter_helpers.button(
            self.main_frame,
            "Flash",
            2,
            2,
            self.download_and_flash_selected,
        )

        self.status_label = tkinter_helpers.label(
            self.main_frame,
            "",
            3,
            0,
            columnspan=3,
        )

        self.refresh_devices()
        self.load_variants()

    def refresh_devices(self):
        current_selection = self.device_var.get()
        self.devices = list_volumes()
        device_list = list(self.devices.keys())
        self.device_combobox.configure(values=device_list)
        if current_selection in device_list:
            self.device_var.set(current_selection)
            self.on_device_selected()
            return
        self.variant_dropdown.configure(values=[])
        self.variant_var.set("Select a variant")
        self.version_dropdown.configure(values=[])
        self.version_var.set("Select a version")
        if self.devices:
            self.device_var.set("Select a device")
            self.status_label.configure(text="Select a device")
        else:
            self.device_var.set("No Pico detected")
            self.status_label.configure(text="No Pico detected in bootloader mode.")

    def on_device_selected(self, event=None):
        selected_device = self.device_var.get()
        if selected_device in self.devices:
            self.status_label.configure(text=f"Selected device: {selected_device}")
            model = self.devices.get(selected_device, "")
            matching_variants = []
            for variant in self.variants:
                # check if the vendor name is in the model name, reorder the variants list to put the matching one first and reupdate the dropdown
                vendor = variant.get("vendor")
                if (
                    vendor
                    and model
                    and re.search(rf"\b{vendor}\b", model, re.IGNORECASE)
                ):
                    matching_variants.append(variant)

            if matching_variants:  # only show the matching ones if we found any
                titles = [
                    v.get("title") or f"{v['vendor']} {v['model']}"
                    for v in matching_variants
                ]
                self.variant_dropdown.configure(values=titles)
                if titles:
                    self.variant_var.set(titles[0])
                    self.select_variant(titles[0])
            else:
                titles = [
                    v.get("title") or f"{v['vendor']} {v['model']}"
                    for v in self.variants
                ]
                self.variant_dropdown.configure(values=titles)
                if titles:
                    self.variant_var.set("Select a variant")
                    self.select_variant("Select a variant")
        else:
            self.status_label.configure(text="Invalid device selected.")

    def load_variants(self):
        try:
            resp = requests.get(VARIANT_URL)
            resp.raise_for_status()
            self.variants = [v for v in resp.json() if v.get("family") == "rp2"]
            titles = [
                v.get("title") or f"{v['vendor']} {v['model']}" for v in self.variants
            ]
            self.variant_dropdown.configure(values=titles)
            if titles:
                self.variant_var.set("Select a variant")
        except Exception as e:
            self.status_label.configure(text=f"Failed to load variants: {e}")

    def on_variant_selected(self, event=None):
        title = self.variant_var.get()
        self.select_variant(title)

    def select_variant(self, title):
        self.selected_variant = next(
            (
                v
                for v in self.variants
                if (v.get("title") or f"{v['vendor']} {v['model']}") == title
            ),
            None,
        )
        downloads = (
            self.selected_variant.get("downloads", []) if self.selected_variant else []
        )
        versions = [d["version"] for d in downloads]
        self.version_dropdown.configure(values=versions)
        if versions:
            self.version_var.set(versions[0])
        else:
            self.version_var.set("Select a version")

    def drop(self, event=None, fd_path=None, confirm=False):
        if event:
            path = event.data.strip().strip("{}")
        elif fd_path:
            path = fd_path.strip().strip("{}")
        else:
            return
        if os.path.isfile(path) and path.lower().endswith(".uf2"):
            if confirm:
                self.status_label.configure(
                    text=f"Flashing {os.path.basename(path)}..."
                )
                self.flash_selected_device(path)
            else:

                def callback(choice):
                    if choice == "Yes":
                        self.drop(event, fd_path, True)

                tkinter_helpers.non_blocking_custom_messagebox(
                    parent=self.master,
                    title="Confirm Flash",
                    message=f"Flash UF2 file '{os.path.basename(path)}' to selected device?",
                    buttons=["Yes", "No"],
                    callback=callback,
                )
                return
        else:
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "Invalid file",
                "Please drop a valid .uf2 file.",
            )

    def flash_selected_device(self, uf2_path):
        target_volume = self.device_var.get()
        if not target_volume:
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "No Device Selected",
                "Please select a device to flash.",
            )
            return
        self.status_label.configure(text="Flashing...")
        success = flash_uf2(uf2_path, target_volume)
        if success:
            self.status_label.configure(text="Flashing completed successfully.")
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "Success",
                f"{os.path.basename(uf2_path)} flashed completed.",
            )
        else:
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "Error",
                "Flashing failed.",
            )
        self.refresh_devices()

    def download_and_flash_selected(self, confirm=False):
        if not self.selected_variant:
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "No Variant Selected",
                "Select a firmware variant before flashing.",
            )
            return
        version = self.version_var.get()
        download = next(
            (
                d
                for d in self.selected_variant.get("downloads", [])
                if d["version"] == version
            ),
            None,
        )
        if not download:
            self.status_label.configure(text="Selected version not found.")
            return
        url = download["url"]
        temp_path = os.path.join(os.getcwd(), "temp.uf2")

        target_volume = self.device_var.get()
        if not target_volume:
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "No Device Selected",
                "Select a device before flashing.",
            )
            return

        if not confirm:

            def callback(choice):
                if choice == "Yes":
                    self.download_and_flash_selected(True)

            tkinter_helpers.non_blocking_custom_messagebox(
                parent=self.master,
                title="Confirm Flash",
                message=f"Download and flash MicroPython {version} to {target_volume}?",
                buttons=["Yes", "No"],
                callback=callback,
            )
            return

        self.status_label.configure(text=f"Downloading {version}...")
        if download_uf2(url, temp_path):
            self.status_label.configure(text=f"Flashing {version}...")
            if flash_uf2(temp_path, target_volume):
                tkinter_helpers.non_blocking_messagebox(
                    self.master,
                    "Success",
                    f"{version} flashed completed.",
                )
            else:
                tkinter_helpers.non_blocking_messagebox(
                    self.master,
                    "Error",
                    "Flashing failed.",
                )
            os.remove(temp_path)
        else:
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "Download failed",
                "Failed to download the firmware, check your internet connection.",
            )

        self.refresh_devices()

    def flash_custom_uf2(self):
        """pop a file dialog to select a uf2 file and flash it to the selected device"""
        # check if a device is selected
        values = self.device_combobox.cget("values")
        if not values:
            tkinter_helpers.non_blocking_messagebox(
                self.master,
                "No Device Selected",
                "Select a device first.",
            )
            return
        uf2_path = filedialog.askopenfilename(
            title="Select a UF2 file",
            filetypes=[("UF2 files", "*.uf2")],
        )
        if uf2_path:
            self.drop(fd_path=uf2_path)


if __name__ == "__main__":
    root = TkDnD()
    app = PicoFlasherApp(root)
    root.mainloop()

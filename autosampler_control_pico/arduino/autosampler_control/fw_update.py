import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests

from tkinterdnd2 import DND_FILES, TkinterDnD

# Constants
UF2_INFO_FILENAME = "INFO_UF2.TXT"
MICROPYTHON_UF2_URL = (
    "https://micropython.org/resources/firmware/rp2-pico-20250415-v1.25.0.uf2"
)


def list_volumes():
    volumes = []
    if sys.platform.startswith("win"):
        import string
        from ctypes import windll

        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:/"
                if os.path.exists(os.path.join(drive, UF2_INFO_FILENAME)):
                    volumes.append(drive)
            bitmask >>= 1
    else:
        for mount_point in ["/media", "/Volumes"]:
            if os.path.exists(mount_point):
                for entry in os.listdir(mount_point):
                    path = os.path.join(mount_point, entry)
                    if os.path.isdir(path) and os.path.exists(
                        os.path.join(path, UF2_INFO_FILENAME)
                    ):
                        volumes.append(path)
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


class PicoFlasherApp:
    def __init__(self, master):
        self.master = master
        master.title("Raspberry Pi Pico Flasher")

        self.variants = []
        self.selected_variant = None

        self.label = tk.Label(master, text="Detected Pico Devices:")
        self.label.pack()

        self.device_listbox = tk.Listbox(master, width=50)
        self.device_listbox.pack()

        self.refresh_button = tk.Button(
            master, text="Refresh Devices", command=self.refresh_devices
        )
        self.refresh_button.pack(pady=5)

        self.variant_label = tk.Label(master, text="Select Variant:")
        self.variant_label.pack()
        self.variant_var = tk.StringVar()
        self.variant_dropdown = ttk.Combobox(
            master, textvariable=self.variant_var, state="readonly"
        )
        self.variant_dropdown.pack()
        self.variant_dropdown.bind("<<ComboboxSelected>>", self.on_variant_selected)

        self.version_label = tk.Label(master, text="Select Firmware Version:")
        self.version_label.pack()
        self.version_var = tk.StringVar()
        self.version_dropdown = ttk.Combobox(
            master, textvariable=self.version_var, state="readonly"
        )
        self.version_dropdown.pack()

        self.dnd_label = tk.Label(
            master,
            text="Drag and drop a UF2 file here",
            bg="lightgray",
            width=50,
            height=5,
        )
        self.dnd_label.pack(pady=10)
        self.dnd_label.drop_target_register(DND_FILES)
        self.dnd_label.dnd_bind("<<Drop>>", self.drop)

        self.download_button = tk.Button(
            master,
            text="Download and Flash Selected Firmware",
            command=self.download_and_flash_selected,
        )
        self.download_button.pack(pady=5)

        self.status_label = tk.Label(master, text="", fg="blue")
        self.status_label.pack()

        self.refresh_devices()
        self.load_variants()

    def refresh_devices(self):
        self.device_listbox.delete(0, tk.END)
        self.devices = list_volumes()
        for device in self.devices:
            self.device_listbox.insert(tk.END, device)
        if not self.devices:
            self.status_label.config(
                text="No Pico devices detected in bootloader mode."
            )
        else:
            self.status_label.config(text="")

    def load_variants(self):
        url = "https://raw.githubusercontent.com/thonny/thonny/master/data/micropython-variants-uf2.json"
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            self.variants = [v for v in resp.json() if v.get("family") == "rp2"]
            titles = [
                v.get("title") or f"{v['vendor']} {v['model']}" for v in self.variants
            ]
            self.variant_dropdown["values"] = titles
            if titles:
                self.variant_var.set(titles[0])
                self.select_variant(titles[0])
        except Exception as e:
            self.status_label.config(text=f"Failed to load variants: {e}")

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
        self.version_dropdown["values"] = versions
        if versions:
            self.version_var.set(versions[0])

    def drop(self, event):
        path = event.data.strip().strip("{}")
        if os.path.isfile(path) and path.lower().endswith(".uf2"):
            if messagebox.askyesno(
                "Confirm Flash",
                f"Flash UF2 file '{os.path.basename(path)}' to selected device?",
            ):
                self.flash_selected_device(path)
        else:
            messagebox.showwarning("Invalid file", "Please drop a valid .uf2 file.")

    def flash_selected_device(self, uf2_path):
        selection = self.device_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No Device Selected", "Please select a device to flash."
            )
            return
        target_volume = self.device_listbox.get(selection[0])
        self.status_label.config(text="Flashing...")
        success = flash_uf2(uf2_path, target_volume)
        if success:
            self.status_label.config(text="Flashing completed successfully.")
        else:
            self.status_label.config(text="Flashing failed.")

    def download_and_flash_selected(self):
        if not self.selected_variant:
            messagebox.showerror("No Variant", "Please select a firmware variant.")
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
            self.status_label.config(text="Selected version not found.")
            return
        url = download["url"]
        temp_path = os.path.join(os.getcwd(), "temp.uf2")

        selection = self.device_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No Device Selected", "Please select a device to flash."
            )
            return
        target_volume = self.device_listbox.get(selection[0])

        if not messagebox.askyesno(
            "Confirm Flash",
            f"Download and flash MicroPython {version} to {target_volume}?",
        ):
            return

        self.status_label.config(text=f"Downloading {version}...")
        if download_uf2(url, temp_path):
            self.status_label.config(text=f"Flashing {version}...")
            if flash_uf2(temp_path, target_volume):
                self.status_label.config(text=f"{version} flashed successfully.")
            else:
                self.status_label.config(text="Flashing failed.")
            os.remove(temp_path)
        else:
            self.status_label.config(text="Download failed.")


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = PicoFlasherApp(root)
    root.mainloop()

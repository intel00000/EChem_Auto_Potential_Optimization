import customtkinter


class PicoControllerRpi(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title("Pico Controller RPi")
        self.geometry("400x150")

        self.button = customtkinter.CTkButton(
            self, text="my button", command=self.button_callbck
        )
        self.button.pack(padx=20, pady=20)

    def button_callbck(self):
        print("button clicked")


app = PicoControllerRpi()
app.mainloop()

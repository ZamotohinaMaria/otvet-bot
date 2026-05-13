from tkinter import END, Text
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class LabeledEntry(ttk.Frame):
    def __init__(self, master, label: str, show: str | None = None):
        super().__init__(master)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text=label).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.entry = ttk.Entry(self, show=show or "")
        self.entry.grid(row=0, column=1, sticky="ew")

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str) -> None:
        self.entry.delete(0, END)
        self.entry.insert(0, value)

    def set_readonly(self, readonly: bool) -> None:
        self.entry.configure(state="readonly" if readonly else "normal")


class JsonText(ScrolledText):
    def __init__(self, master, **kwargs):
        defaults = {
            "height": 14,
            "wrap": "word",
            "font": ("Consolas", 10),
        }
        defaults.update(kwargs)
        super().__init__(master, **defaults)

    def get_all(self) -> str:
        return self.get("1.0", END).strip()

    def set_all(self, value: str) -> None:
        self.delete("1.0", END)
        self.insert("1.0", value)


class ReadOnlyLog(ScrolledText):
    def __init__(self, master, **kwargs):
        defaults = {
            "height": 14,
            "wrap": "word",
            "font": ("Consolas", 10),
            "state": "disabled",
        }
        defaults.update(kwargs)
        super().__init__(master, **defaults)

    def append(self, text: str) -> None:
        self.configure(state="normal")
        self.insert("end", text + "\n")
        self.see("end")
        self.configure(state="disabled")

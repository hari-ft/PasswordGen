import ctypes
import json
import math
import secrets
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

try:
    import winreg
except ImportError:
    winreg = None


MIN_LENGTH = 4
MAX_LENGTH = 256
DEFAULT_LENGTH = 16
HISTORY_LIMIT = 20
CLIPBOARD_CLEAR_MS = 30_000
REGENERATE_DELAY_MS = 150
THEME_POLL_MS = 3_000
SETTINGS_FILE = Path.home() / ".password_generator_settings.json"

CHARACTER_SETS = {
    "uppercase": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "lowercase": "abcdefghijklmnopqrstuvwxyz",
    "numbers": "0123456789",
}
DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"
LOOK_ALIKE_CHARACTERS = "Il1O0o"
MASK = "•" * 12

PALETTES = {
    "light": {
        "bg": "#f4f6fa",
        "card": "#ffffff",
        "text": "#182230",
        "heading": "#14213d",
        "muted": "#596579",
        "border": "#d8dee9",
        "field": "#ffffff",
        "button": "#e9edf4",
        "button_active": "#dce3ee",
        "accent": "#2f6fed",
        "accent_active": "#2559c9",
        "accent_text": "#ffffff",
        "select": "#cfe0ff",
        "select_text": "#14213d",
        "error": "#c62828",
    },
    "dark": {
        "bg": "#14171c",
        "card": "#1d2128",
        "text": "#e6e9ef",
        "heading": "#f2f4f8",
        "muted": "#9aa4b5",
        "border": "#343a45",
        "field": "#262b33",
        "button": "#2b313b",
        "button_active": "#363d49",
        "accent": "#4c8dff",
        "accent_active": "#3b78e6",
        "accent_text": "#ffffff",
        "select": "#2f4f86",
        "select_text": "#ffffff",
        "error": "#ff6b6b",
    },
}

# (minimum bits of entropy, label, bar colour), strongest first.
STRENGTH_LEVELS = (
    (128, "Very strong", "#1b9e5a"),
    (80, "Strong", "#2fb36b"),
    (60, "Good", "#e0a100"),
    (40, "Fair", "#f07b1d"),
    (0, "Weak", "#d93a3a"),
)


def make_password(length, character_sets):
    """Return a random password containing at least one character from each set."""
    characters = [secrets.choice(character_set) for character_set in character_sets]
    alphabet = "".join(dict.fromkeys("".join(character_sets)))
    characters.extend(secrets.choice(alphabet) for _ in range(length - len(characters)))
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def entropy_bits(length, character_sets):
    alphabet_size = len(set("".join(character_sets)))
    return length * math.log2(alphabet_size) if alphabet_size > 1 else 0.0


def strength_label(bits):
    for minimum, label, _colour in STRENGTH_LEVELS:
        if bits >= minimum:
            return label
    return STRENGTH_LEVELS[-1][1]


def progressbar_style(label):
    return f"{label.replace(' ', '')}.Horizontal.TProgressbar"


def enable_high_dpi():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def windows_prefers_dark():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def set_dark_title_bar(window, dark):
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


def create_icon(master):
    """Draw a 32x32 padlock for the window icon."""
    icon = tk.PhotoImage(master=master, width=32, height=32)
    icon.put("#2f6fed", to=(10, 2, 22, 6))
    icon.put("#2f6fed", to=(8, 4, 12, 15))
    icon.put("#2f6fed", to=(20, 4, 24, 15))
    icon.put("#2f6fed", to=(4, 14, 28, 31))
    icon.put("#ffffff", to=(14, 19, 18, 23))
    icon.put("#ffffff", to=(15, 23, 17, 27))
    return icon


class PasswordGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Password Generator")
        self.icon = create_icon(root)
        self.root.iconphoto(True, self.icon)
        self.scale = root.winfo_fpixels("1i") / 96

        self.history = []
        self.length_var = tk.StringVar(value=str(DEFAULT_LENGTH))
        self.slider_var = tk.DoubleVar(value=DEFAULT_LENGTH)
        self.uppercase_var = tk.BooleanVar(value=True)
        self.lowercase_var = tk.BooleanVar(value=True)
        self.numbers_var = tk.BooleanVar(value=True)
        self.symbols_var = tk.BooleanVar(value=True)
        self.avoid_look_alike_var = tk.BooleanVar(value=False)
        self.hide_var = tk.BooleanVar(value=False)
        self.symbols_text = tk.StringVar(value=DEFAULT_SYMBOLS)
        self.password_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.strength_var = tk.StringVar()

        self._timers = {}
        self._copied_password = None
        self._message_is_error = False
        self.dark = windows_prefers_dark()
        self.style = ttk.Style(root)
        self.style.theme_use("clam")

        self._load_settings()
        self._build_ui()
        self._apply_theme()
        self._apply_visibility()
        self._bind_shortcuts()
        self._fit_window()

        for variable in (
            self.length_var,
            self.uppercase_var,
            self.lowercase_var,
            self.numbers_var,
            self.symbols_var,
            self.avoid_look_alike_var,
            self.symbols_text,
        ):
            variable.trace_add("write", self._on_setting_changed)
        self.hide_var.trace_add("write", lambda *_: self._apply_visibility())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, lambda: set_dark_title_bar(self.root, self.dark))
        if winreg is not None:
            self.root.after(THEME_POLL_MS, self._poll_theme)

        self._regenerate()

    def _px(self, pixels):
        return round(pixels * self.scale)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=(20, 14))
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Password Generator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Create a strong password with the character types you choose.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        options = ttk.Frame(outer, style="Card.TFrame", padding=12)
        options.pack(fill="x")
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Password length", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.length_entry = ttk.Spinbox(
            options,
            textvariable=self.length_var,
            from_=MIN_LENGTH,
            to=MAX_LENGTH,
            width=6,
            justify="center",
        )
        self.length_entry.grid(row=1, column=0, sticky="w", pady=(6, 10))
        ttk.Scale(
            options,
            from_=MIN_LENGTH,
            to=MAX_LENGTH,
            variable=self.slider_var,
            command=self._sync_entry_from_slider,
        ).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(6, 10))

        ttk.Label(options, text="Character types", style="Section.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        checks = ttk.Frame(options, style="Card.TFrame")
        checks.grid(row=3, column=0, columnspan=2, sticky="w")
        for text, variable in (
            ("Uppercase (A–Z)", self.uppercase_var),
            ("Lowercase (a–z)", self.lowercase_var),
            ("Numbers (0–9)", self.numbers_var),
            ("Symbols", self.symbols_var),
        ):
            ttk.Checkbutton(checks, text=text, variable=variable).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(
            options,
            text="Avoid look-alike characters (I, l, 1, O, 0, o)",
            variable=self.avoid_look_alike_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Label(options, text="Allowed symbols", style="Card.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 3)
        )
        self.symbols_entry = ttk.Entry(options, textvariable=self.symbols_text)
        self.symbols_entry.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Label(
            options,
            text="Used when Symbols is on. Spaces are ignored.",
            style="Muted.TLabel",
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(3, 0))
        ttk.Label(options, text="Note (optional)", style="Card.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(8, 3)
        )
        ttk.Entry(options, textvariable=self.note_var).grid(row=9, column=0, columnspan=2, sticky="ew")

        settings_row = ttk.Frame(options, style="Card.TFrame")
        settings_row.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(settings_row, text="Save settings", command=self.save_settings).pack(side="right")
        self.save_status = ttk.Label(settings_row, style="Muted.TLabel")
        self.save_status.pack(side="right", padx=(0, 10))

        ttk.Button(
            outer,
            text="Generate password",
            style="Accent.TButton",
            command=self.generate_password,
        ).pack(fill="x", pady=(10, 8))

        result = ttk.Frame(outer, style="Card.TFrame", padding=12)
        result.pack(fill="x")
        result_heading = ttk.Frame(result, style="Card.TFrame")
        result_heading.pack(fill="x", pady=(0, 5))
        ttk.Label(result_heading, text="Your password", style="Section.TLabel").pack(side="left")
        ttk.Checkbutton(result_heading, text="Hide passwords", variable=self.hide_var).pack(side="right")

        password_row = ttk.Frame(result, style="Card.TFrame")
        password_row.pack(fill="x")
        self.password_entry = ttk.Entry(
            password_row,
            textvariable=self.password_var,
            state="readonly",
            font=("Consolas", 12),
        )
        self.password_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.copy_button = ttk.Button(password_row, text="Copy", width=10, command=self.copy_generated)
        self.copy_button.pack(side="left", padx=(8, 0))

        strength_row = ttk.Frame(result, style="Card.TFrame")
        strength_row.pack(fill="x", pady=(8, 0))
        self.strength_bar = ttk.Progressbar(strength_row, maximum=128, length=self._px(160))
        self.strength_bar.pack(side="left")
        ttk.Label(strength_row, textvariable=self.strength_var, style="Card.TLabel").pack(
            side="left", padx=(10, 0)
        )
        self.message_label = ttk.Label(result, style="Muted.TLabel")
        self.message_label.pack(anchor="w", pady=(4, 0))

        history_frame = ttk.Frame(outer, style="Card.TFrame", padding=12)
        history_frame.pack(fill="both", expand=True, pady=(10, 0))
        history_heading = ttk.Frame(history_frame, style="Card.TFrame")
        history_heading.pack(fill="x", pady=(0, 5))
        ttk.Label(history_heading, text="Recent passwords", style="Section.TLabel").pack(side="left")
        self.copy_selected_button = ttk.Button(
            history_heading, text="Copy selected", width=13, command=self.copy_selected
        )
        self.copy_selected_button.pack(side="right")
        ttk.Button(history_heading, text="Clear", command=self.clear_history).pack(side="right", padx=(0, 8))

        list_frame = ttk.Frame(history_frame, style="Card.TFrame")
        list_frame.pack(fill="both", expand=True)
        self.history_tree = ttk.Treeview(
            list_frame,
            columns=("password", "note", "time"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        for column, heading, width, stretch in (
            ("password", "Password", 280, True),
            ("note", "Note", 150, True),
            ("time", "Time", 85, False),
        ):
            self.history_tree.heading(column, text=heading, anchor="w")
            self.history_tree.column(column, width=self._px(width), minwidth=self._px(60), stretch=stretch)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.history_tree.pack(side="left", fill="both", expand=True)
        self.history_tree.bind("<Double-Button-1>", lambda _event: self.copy_selected())
        self.history_tree.bind("<Delete>", lambda _event: self.delete_selected())
        ttk.Label(
            history_frame,
            text="History stays in memory and is cleared when you close the app.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        ttk.Label(
            outer,
            text="Enter: generate  ·  Ctrl+C: copy  ·  Ctrl+S: save settings  ·  Delete: remove from history",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 0))

    def _fit_window(self):
        self.root.update_idletasks()
        # Leave room for the taskbar and title bar so the window never extends off screen.
        max_height = self.root.winfo_screenheight() - self._px(100)
        width = max(self.root.winfo_reqwidth(), self._px(600))
        height = self.root.winfo_reqheight()
        start_height = min(height + self._px(80), max_height) - round(self.root.winfo_fpixels("1.5c"))
        self.root.minsize(width, min(height, start_height))
        self.root.geometry(f"{width}x{start_height}+{self._px(40)}+{self._px(20)}")

    def _apply_theme(self):
        p = PALETTES["dark" if self.dark else "light"]
        style = self.style
        self.root.configure(bg=p["bg"])

        style.configure(
            ".",
            background=p["bg"],
            foreground=p["text"],
            font=("Segoe UI", 10),
            bordercolor=p["border"],
            lightcolor=p["field"],
            darkcolor=p["field"],
            troughcolor=p["border"],
            fieldbackground=p["field"],
            insertcolor=p["text"],
            selectbackground=p["select"],
            selectforeground=p["select_text"],
            arrowcolor=p["text"],
            focuscolor=p["accent"],
        )
        style.configure("TFrame", background=p["bg"])
        style.configure("Card.TFrame", background=p["card"])
        style.configure("TLabel", background=p["bg"], foreground=p["text"])
        style.configure("Card.TLabel", background=p["card"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["card"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("Error.TLabel", background=p["card"], foreground=p["error"], font=("Segoe UI", 9))
        style.configure("Hint.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=p["bg"], foreground=p["heading"], font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=p["bg"], foreground=p["muted"])
        style.configure(
            "Section.TLabel", background=p["card"], foreground=p["heading"], font=("Segoe UI", 11, "bold")
        )

        style.configure(
            "TCheckbutton",
            background=p["card"],
            foreground=p["text"],
            indicatorbackground=p["field"],
            indicatorforeground=p["accent"],
            upperbordercolor=p["border"],
            lowerbordercolor=p["border"],
        )
        style.map(
            "TCheckbutton",
            background=[("active", p["card"])],
            indicatorbackground=[("pressed", p["button_active"]), ("active", p["field"])],
        )

        style.configure(
            "TButton",
            background=p["button"],
            foreground=p["text"],
            bordercolor=p["border"],
            lightcolor=p["button"],
            darkcolor=p["button"],
            padding=(10, 4),
        )
        button_states = [("pressed", p["button_active"]), ("active", p["button_active"])]
        style.map("TButton", background=button_states, lightcolor=button_states, darkcolor=button_states)
        style.configure(
            "Accent.TButton",
            background=p["accent"],
            foreground=p["accent_text"],
            bordercolor=p["accent"],
            lightcolor=p["accent"],
            darkcolor=p["accent"],
            font=("Segoe UI", 11, "bold"),
            padding=(14, 8),
        )
        accent_states = [("pressed", p["accent_active"]), ("active", p["accent_active"])]
        style.map(
            "Accent.TButton",
            background=accent_states,
            lightcolor=accent_states,
            darkcolor=accent_states,
            bordercolor=accent_states,
        )

        for name in ("TEntry", "TSpinbox"):
            style.configure(
                name,
                fieldbackground=p["field"],
                foreground=p["text"],
                background=p["button"],
                bordercolor=p["border"],
                lightcolor=p["field"],
                darkcolor=p["field"],
            )
            style.map(
                name,
                fieldbackground=[("readonly", p["field"])],
                bordercolor=[("focus", p["accent"])],
                lightcolor=[("focus", p["accent"])],
            )

        style.configure(
            "Horizontal.TScale",
            background=p["accent"],
            troughcolor=p["border"],
            bordercolor=p["card"],
            lightcolor=p["accent"],
            darkcolor=p["accent"],
        )
        style.map("Horizontal.TScale", background=[("active", p["accent_active"])])
        for name in ("TScrollbar", "Vertical.TScrollbar"):
            style.configure(
                name,
                background=p["button"],
                troughcolor=p["field"],
                bordercolor=p["border"],
                lightcolor=p["button"],
                darkcolor=p["button"],
                arrowcolor=p["muted"],
            )
            style.map(name, background=[("active", p["button_active"])])

        # Keep a reference: Tk deletes a named font once its Python object is garbage collected.
        self.row_font = tkfont.Font(root=self.root, family="Consolas", size=10)
        style.configure(
            "Treeview",
            background=p["field"],
            fieldbackground=p["field"],
            foreground=p["text"],
            bordercolor=p["border"],
            font=self.row_font,
            rowheight=self.row_font.metrics("linespace") + self._px(6),
        )
        style.map("Treeview", background=[("selected", p["select"])], foreground=[("selected", p["select_text"])])
        style.configure(
            "Treeview.Heading",
            background=p["button"],
            foreground=p["text"],
            bordercolor=p["border"],
            lightcolor=p["button"],
            darkcolor=p["button"],
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview.Heading", background=[("active", p["button_active"])])

        for _minimum, label, colour in STRENGTH_LEVELS:
            style.configure(
                progressbar_style(label),
                background=colour,
                troughcolor=p["border"],
                bordercolor=p["card"],
                lightcolor=colour,
                darkcolor=colour,
            )

    def _poll_theme(self):
        dark = windows_prefers_dark()
        if dark != self.dark:
            self.dark = dark
            self._apply_theme()
            set_dark_title_bar(self.root, dark)
        self.root.after(THEME_POLL_MS, self._poll_theme)

    def _load_settings(self):
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(settings, dict):
            return

        length = settings.get("length")
        if isinstance(length, int) and not isinstance(length, bool) and MIN_LENGTH <= length <= MAX_LENGTH:
            self.length_var.set(str(length))
            self.slider_var.set(length)
        for key, variable in (
            ("uppercase", self.uppercase_var),
            ("lowercase", self.lowercase_var),
            ("numbers", self.numbers_var),
            ("symbols", self.symbols_var),
            ("avoid_look_alike", self.avoid_look_alike_var),
            ("hide_passwords", self.hide_var),
        ):
            if isinstance(settings.get(key), bool):
                variable.set(settings[key])
        if isinstance(settings.get("allowed_symbols"), str):
            self.symbols_text.set(settings["allowed_symbols"])

    def save_settings(self):
        length = self._read_length()
        if length is None:
            self._show_save_status(f"Length must be {MIN_LENGTH}–{MAX_LENGTH}.", error=True)
            self.length_entry.focus_set()
            return

        settings = {
            "length": length,
            "uppercase": self.uppercase_var.get(),
            "lowercase": self.lowercase_var.get(),
            "numbers": self.numbers_var.get(),
            "symbols": self.symbols_var.get(),
            "allowed_symbols": self.symbols_text.get(),
            "avoid_look_alike": self.avoid_look_alike_var.get(),
            "hide_passwords": self.hide_var.get(),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except OSError as error:
            self._show_save_status(f"Could not save: {error.strerror or error}", error=True)
            return
        self._show_save_status("Saved ✓")

    def _show_save_status(self, text, error=False):
        self.save_status.configure(text=text, style="Error.TLabel" if error else "Muted.TLabel")
        self._schedule("save_status", 4000 if error else 2500, lambda: self.save_status.configure(text=""))

    def _read_length(self):
        try:
            length = int(self.length_var.get())
        except ValueError:
            return None
        return length if MIN_LENGTH <= length <= MAX_LENGTH else None

    def _read_options(self):
        """Return (length, character_sets, error_message, widget_to_fix)."""
        length = self._read_length()
        if length is None:
            return None, None, f"Length must be a whole number from {MIN_LENGTH} to {MAX_LENGTH}.", self.length_entry

        excluded = set(LOOK_ALIKE_CHARACTERS) if self.avoid_look_alike_var.get() else set()

        def usable(characters):
            return "".join(c for c in dict.fromkeys(characters) if c not in excluded and not c.isspace())

        selected_sets = [
            usable(CHARACTER_SETS[name])
            for name, variable in (
                ("uppercase", self.uppercase_var),
                ("lowercase", self.lowercase_var),
                ("numbers", self.numbers_var),
            )
            if variable.get()
        ]
        if self.symbols_var.get():
            symbols = usable(self.symbols_text.get())
            if not symbols:
                return None, None, "Enter at least one allowed symbol, or turn off Symbols.", self.symbols_entry
            selected_sets.append(symbols)

        if not selected_sets:
            return None, None, "Select at least one character type.", None
        if length < len(selected_sets):
            message = f"The selected character types need a length of at least {len(selected_sets)}."
            return None, None, message, self.length_entry
        return length, selected_sets, None, None

    def _regenerate(self):
        """Show a fresh password for the current options. Returns (ok, widget_to_fix)."""
        length, selected_sets, error, widget = self._read_options()
        if error:
            self.password_var.set("")
            self.strength_bar.configure(value=0)
            self.strength_var.set("")
            self._show_message(error, error=True)
            return False, widget

        bits = entropy_bits(length, selected_sets)
        label = strength_label(bits)
        self.password_var.set(make_password(length, selected_sets))
        self.strength_bar.configure(value=min(bits, 128), style=progressbar_style(label))
        self.strength_var.set(f"{label}  ·  {round(bits)} bits")
        if self._message_is_error:
            self._show_message("")
        return True, None

    def generate_password(self):
        self._cancel("regenerate")
        ok, widget = self._regenerate()
        if ok:
            self._record(self.password_var.get())
        elif widget is not None:
            widget.focus_set()

    def _on_setting_changed(self, *_args):
        self._sync_slider_from_entry()
        self._schedule("regenerate", REGENERATE_DELAY_MS, self._regenerate)

    def _sync_entry_from_slider(self, value):
        self.length_var.set(str(round(float(value))))

    def _sync_slider_from_entry(self):
        length = self._read_length()
        if length is not None:
            self.slider_var.set(length)

    def _record(self, password):
        if self.history and self.history[0]["password"] == password:
            return
        self.history.insert(
            0,
            {
                "password": password,
                "note": self.note_var.get().strip(),
                "time": datetime.now().strftime("%I:%M %p").lstrip("0"),
            },
        )
        del self.history[HISTORY_LIMIT:]
        self._refresh_history()

    def _refresh_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        hide = self.hide_var.get()
        for index, item in enumerate(self.history):
            shown = MASK if hide else item["password"]
            self.history_tree.insert("", "end", iid=str(index), values=(shown, item["note"], item["time"]))

    def _selected_index(self):
        selection = self.history_tree.selection()
        return int(selection[0]) if selection else None

    def delete_selected(self):
        index = self._selected_index()
        if index is not None:
            del self.history[index]
            self._refresh_history()

    def clear_history(self):
        self.history.clear()
        self._refresh_history()

    def _apply_visibility(self):
        self.password_entry.configure(show="•" if self.hide_var.get() else "")
        self._refresh_history()

    def copy_generated(self):
        password = self.password_var.get()
        if password:
            self._record(password)
            self._copy_to_clipboard(password, self.copy_button, "Copy")

    def copy_selected(self):
        index = self._selected_index()
        if index is not None:
            self._copy_to_clipboard(self.history[index]["password"], self.copy_selected_button, "Copy selected")

    def _copy_to_clipboard(self, password, button, label):
        self.root.clipboard_clear()
        self.root.clipboard_append(password)
        self.root.update()
        self._copied_password = password

        button.configure(text="Copied ✓")
        self._schedule(f"button:{label}", 1500, lambda: button.configure(text=label))
        self._show_message(f"Copied. The clipboard will be cleared in {CLIPBOARD_CLEAR_MS // 1000} seconds.")
        self._schedule("clipboard", CLIPBOARD_CLEAR_MS, self._clear_clipboard)

    def _clear_clipboard(self):
        self._cancel("clipboard")
        try:
            still_ours = self.root.clipboard_get() == self._copied_password
        except tk.TclError:
            still_ours = False
        if still_ours:
            self.root.clipboard_clear()
            self.root.update()
            self._show_message("Clipboard cleared.", fade_ms=2500)
        self._copied_password = None

    def _bind_shortcuts(self):
        self.root.bind("<Return>", lambda _event: self.generate_password())
        self.root.bind("<KP_Enter>", lambda _event: self.generate_password())
        self.root.bind("<Control-c>", self._on_copy_shortcut)
        self.root.bind("<Control-C>", self._on_copy_shortcut)
        self.root.bind("<Control-s>", lambda _event: self.save_settings())
        self.root.bind("<Control-S>", lambda _event: self.save_settings())

    def _on_copy_shortcut(self, event):
        # Editable text fields keep their normal copy behaviour.
        if isinstance(event.widget, ttk.Entry) and event.widget is not self.password_entry:
            return
        if event.widget is self.history_tree and self.history_tree.selection():
            self.copy_selected()
        else:
            self.copy_generated()

    def _show_message(self, text, error=False, fade_ms=None):
        self.message_label.configure(text=text, style="Error.TLabel" if error else "Muted.TLabel")
        self._message_is_error = error
        self._cancel("message")
        if fade_ms:
            self._schedule("message", fade_ms, lambda: self._show_message(""))

    def _schedule(self, name, delay_ms, callback):
        self._cancel(name)

        def run():
            self._timers.pop(name, None)
            callback()

        self._timers[name] = self.root.after(delay_ms, run)

    def _cancel(self, name):
        timer = self._timers.pop(name, None)
        if timer is not None:
            self.root.after_cancel(timer)

    def _on_close(self):
        if self._copied_password is not None:
            self._clear_clipboard()
        self.root.destroy()


def main():
    enable_high_dpi()
    root = tk.Tk()
    PasswordGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

# Shared widget components and ThemeEngine

# ThemeEngine reads directly from SettingsManager rather than from CTk's appearance mode
# Avoids async race conditions when colors change.

from __future__ import annotations
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable
import customtkinter as ctk

if TYPE_CHECKING:
    from .settings_manager import SettingsManager

# Accent color: mutated at runtime by the Settings page when the user picks a new one.
ACCENT   = "#00b4d8"
ACCENT_H = "#0096c7"

# These legacy constants are dark-mode values kept for code that still imports them directly.
# Prefer ThemeEngine methods for anything theme-aware.
SURFACE  = "#161b22"
CARD     = "#1c2128"
BORDER   = "#30363d"
TEXT_DIM = "#6b7280"


class ThemeEngine:
    # Main source for all UI colors.

    # Call ThemeEngine.init(settings) once at startup. All color methods
    # read from the live settings dict so values stay current without reloads.

    # For instant color updates without a full rebuild, register a callback
    # via on_color_change() and call notify_color_change() after saving changes.

    # color keys in settings follow the pattern dark_<slot> / light_<slot>,
    #covering surface, sidebar, card, border, text, text_dim, log_bg, log_bar, and log_panel.

    _s: "SettingsManager | None" = None
    _color_change_callbacks: list = []

    @classmethod
    def init(cls, settings: "SettingsManager") -> None:
        cls._s = settings

    @classmethod
    def on_color_change(cls, callback: Callable[[], None]) -> None:
        if callback not in cls._color_change_callbacks:
            cls._color_change_callbacks.append(callback)

    @classmethod
    def remove_color_callback(cls, callback: Callable[[], None]) -> None:
        if callback in cls._color_change_callbacks:
            cls._color_change_callbacks.remove(callback)

    @classmethod
    def notify_color_change(cls) -> None:
        for callback in cls._color_change_callbacks[:]:  # copy so callbacks can remove themselves
            try:
                callback()
            except Exception:
                pass  # widget may have been destroyed

    @classmethod
    def _is_light(cls) -> bool:
        if cls._s is None:
            return False
        mode = str(cls._s["appearance_mode"]).lower()
        if mode == "system":
            # only fall back to CTk for "system", acceptable at startup before first rebuild
            return ctk.get_appearance_mode().lower() == "light"
        return mode == "light"

    @classmethod
    def _get(cls, key_light: str, key_dark: str) -> str:
        if cls._s is None:
            return "#ffffff" if key_light.startswith("light") else "#000000"
        return str(cls._s[key_light if cls._is_light() else key_dark])

    # Color accessors
    # One per slot

    @classmethod
    def surface(cls) -> str: return cls._get("light_surface", "dark_surface")

    @classmethod
    def sidebar(cls) -> str: return cls._get("light_sidebar", "dark_sidebar")

    @classmethod
    def card(cls) -> str: return cls._get("light_card", "dark_card")

    @classmethod
    def border(cls) -> str: return cls._get("light_border", "dark_border")

    @classmethod
    def text(cls) -> str: return cls._get("light_text", "dark_text")

    @classmethod
    def text_dim(cls) -> str: return cls._get("light_text_dim", "dark_text_dim")

    @classmethod
    def log_bg(cls) -> str:
        # Background of the text area inside the log panel.
        return cls._get("light_log_bg", "dark_log_bg")

    @classmethod
    def log_panel(cls) -> str:
        # Background of the outer log wrapper frame.
        return cls._get("light_log_panel", "dark_log_panel")

    @classmethod
    def log_bar(cls) -> str: return cls._get("light_log_bar", "dark_log_bar")

    @classmethod
    def sash(cls) -> str:
        return cls.border()  # sash uses the border color, works fine in both modes

    @classmethod
    def log_bar_fg(cls) -> str: return cls.text_dim()

    # CTk two-tuple helpers (light_value, dark_value).
    # CTk widgets accept these and update themselves automatically on mode change.

    @classmethod
    def ctk_surface(cls) -> tuple[str, str]:
        if cls._s is None: return ("#ebebeb", "#161b22")
        return (str(cls._s["light_surface"]), str(cls._s["dark_surface"]))

    @classmethod
    def ctk_card(cls) -> tuple[str, str]:
        if cls._s is None: return ("#ffffff", "#1c2128")
        return (str(cls._s["light_card"]), str(cls._s["dark_card"]))

    @classmethod
    def ctk_sidebar(cls) -> tuple[str, str]:
        if cls._s is None: return ("#f3f4f6", "#1c2128")
        return (str(cls._s["light_sidebar"]), str(cls._s["dark_sidebar"]))

    @classmethod
    def ctk_border(cls) -> tuple[str, str]:
        if cls._s is None: return ("#d1d5db", "#30363d")
        return (str(cls._s["light_border"]), str(cls._s["dark_border"]))

    @classmethod
    def ctk_text_dim(cls) -> tuple[str, str]:
        if cls._s is None: return ("#6b7280", "#6b7280")
        return (str(cls._s["light_text_dim"]), str(cls._s["dark_text_dim"]))

    @classmethod
    def ctk_nav_txt(cls) -> tuple[str, str]:
        if cls._s is None: return ("#1f2937", "#e2e8f0")
        return (str(cls._s["light_text"]), str(cls._s["dark_text"]))

    @classmethod
    def ctk_nav_act(cls) -> tuple[str, str]:
        # Active nav item gets a slightly different shade from the sidebar bg
        if cls._s is None: return ("#d1d5db", "#21262d")
        return (str(cls._s["light_border"]), "#21262d")

    @classmethod
    def ctk_nav_hov(cls) -> tuple[str, str]:
        if cls._s is None: return ("#e5e7eb", "#21262d")
        return (str(cls._s["light_border"]), "#21262d")

    @classmethod
    def log_level_colors(cls) -> dict[str, str]:
        if cls._is_light():
            return {
                "DEBUG":    cls.text_dim(),
                "INFO":     cls.text(),
                "WARNING":  "#b45309",
                "ERROR":    "#dc2626",
                "CRITICAL": "#991b1b",
            }
        return {
            "DEBUG":    cls.text_dim(),
            "INFO":     cls.text(),
            "WARNING":  "#fbbf24",
            "ERROR":    "#f87171",
            "CRITICAL": "#ef4444",
        }


# Thin wrappers kept for backward compatibility
def theme_surface()    -> str: return ThemeEngine.surface()
def theme_card()       -> str: return ThemeEngine.card()
def theme_border()     -> str: return ThemeEngine.border()
def theme_text_dim()   -> str: return ThemeEngine.text_dim()
def theme_sash()       -> str: return ThemeEngine.sash()
def theme_log_bg()     -> str: return ThemeEngine.log_bg()
def theme_log_bar_bg() -> str: return ThemeEngine.log_bar()
def theme_log_bar_fg() -> str: return ThemeEngine.log_bar_fg()


class PathSelector(ctk.CTkFrame):
    # Labelled path entry with a Browse button.

    def __init__(self, parent, label, mode="folder", filetypes=None, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self._mode      = mode
        self._filetypes = filetypes or [("All files", "*.*")]
        self._var       = tk.StringVar()
        self._var.trace_add("write", lambda *_: on_change and on_change(self._var.get()))
        ctk.CTkLabel(self, text=label,
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 4))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkEntry(row, textvariable=self._var,
                     placeholder_text="No path selected…").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Browse", width=80, command=self._browse,
                      fg_color=ACCENT, hover_color=ACCENT_H).pack(side="left", padx=(8, 0))

    @property
    def path(self): return self._var.get()

    @path.setter
    def path(self, v): self._var.set(v)

    def _browse(self):
        if self._mode == "folder":
            r = filedialog.askdirectory(title="Select Folder")
        else:
            r = filedialog.askopenfilename(title="Select File", filetypes=self._filetypes)
        if r:
            self._var.set(r)


class SectionCard(ctk.CTkFrame):
    # A titled card container for grouping related controls.

    def __init__(self, parent, title, **kwargs):
        super().__init__(parent, fg_color=ThemeEngine.ctk_card(),
                         corner_radius=10, border_width=1,
                         border_color=ThemeEngine.ctk_border(), **kwargs)
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(hdr, text=title.upper(),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=ACCENT).pack(anchor="w")
        ctk.CTkFrame(self, height=1, fg_color=ThemeEngine.ctk_border()).pack(
            fill="x", padx=16, pady=(8, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=16, pady=12)


class ProgressCard(ctk.CTkFrame):
    # Progress bar with a status label and elapsed time counter.

    def __init__(self, parent):
        super().__init__(parent, fg_color=ThemeEngine.ctk_card(),
                         corner_radius=10, border_width=1,
                         border_color=ThemeEngine.ctk_border())
        self._status_var  = tk.StringVar(value="Idle")
        self._elapsed_var = tk.StringVar(value="")
        self._start_time: float = 0

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(row, textvariable=self._status_var,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(row, textvariable=self._elapsed_var,
                     font=ctk.CTkFont(size=11),
                     text_color=ThemeEngine.ctk_text_dim()).pack(side="right")
        self._bar = ctk.CTkProgressBar(self, mode="indeterminate", progress_color=ACCENT)
        self._bar.pack(fill="x", padx=16, pady=(0, 12))
        self._bar.set(0)
        self._running  = False
        self._after_id = None

    def start(self, message="Running…"):
        import time
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        self._start_time = time.time()
        self._status_var.set(message)
        self._bar.configure(mode="indeterminate")
        self._bar.start()
        self._running = True
        self._tick()

    def set_progress(self, value, message=None):
        self._bar.configure(mode="determinate")
        self._bar.stop()
        self._bar.set(value)
        if message:
            self._status_var.set(message)

    def stop(self, message="Done"):
        import time
        self._running = False
        self._bar.stop()
        self._bar.configure(mode="determinate")
        self._bar.set(1.0)
        self._status_var.set(message)
        self._elapsed_var.set(f"Completed in {time.time() - self._start_time:.1f}s")

    def reset(self):
        self._running = False
        self._bar.stop()
        self._bar.configure(mode="determinate")
        self._bar.set(0)
        self._status_var.set("Idle")
        self._elapsed_var.set("")

    def _tick(self):
        import time
        if self._running:
            self._elapsed_var.set(f"{time.time() - self._start_time:.0f}s elapsed")
            self._after_id = self.after(500, self._tick)
        else:
            self._after_id = None


class StatBadge(ctk.CTkFrame):
    # Small numerical stat tile used on the Home dashboard.

    def __init__(self, parent, label, value="-"):
        super().__init__(parent, fg_color=ThemeEngine.ctk_card(),
                         corner_radius=10, border_width=1,
                         border_color=ThemeEngine.ctk_border())
        self._value_var = tk.StringVar(value=value)
        ctk.CTkLabel(self, textvariable=self._value_var,
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=ACCENT).pack(pady=(16, 2))
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=11),
                     text_color=ThemeEngine.ctk_text_dim()).pack(pady=(0, 14))

    def set(self, value): self._value_var.set(value)


class LabeledSlider(ctk.CTkFrame):
    # Slider with a label, live value readout, and min/max annotations.

    def __init__(self, parent, label, from_, to, initial,
                 step=1.0, fmt="{:.0f}", on_change=None):
        super().__init__(parent, fg_color="transparent")
        self._fmt = fmt
        self._on_change = on_change
        self._value_var = tk.StringVar(value=fmt.format(initial))

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=label, font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(hdr, textvariable=self._value_var,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=ACCENT).pack(side="right")

        self._slider = ctk.CTkSlider(
            self, from_=from_, to=to,
            number_of_steps=max(1, int((to - from_) / step)),
            command=self._on_slide, progress_color=ACCENT,
        )
        self._slider.set(initial)
        self._slider.pack(fill="x", pady=(4, 0))

        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.pack(fill="x")
        lo = int(from_) if step >= 1 else from_
        hi = int(to)    if step >= 1 else to
        ctk.CTkLabel(ftr, text=str(lo), font=ctk.CTkFont(size=10),
                     text_color=ThemeEngine.ctk_text_dim()).pack(side="left")
        ctk.CTkLabel(ftr, text=str(hi), font=ctk.CTkFont(size=10),
                     text_color=ThemeEngine.ctk_text_dim()).pack(side="right")

    def _on_slide(self, value):
        self._value_var.set(self._fmt.format(value))
        if self._on_change:
            self._on_change(value)

    @property
    def value(self): return self._slider.get()

    def set(self, value):
        self._slider.set(value)
        self._value_var.set(self._fmt.format(value))

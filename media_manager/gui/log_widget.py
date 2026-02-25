# Thread-safe logging backend (LogStore) and the scrollable panel that displays it (LogPanel).

from __future__ import annotations
import logging
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from .widgets import ACCENT, ThemeEngine

if TYPE_CHECKING:
    from .settings_manager import SettingsManager

LOG_TITLE_H: int = 34  # height of the title bar in pixels


class QueueHandler(logging.Handler):
    # Pushes log records into a queue so a GUI thread can drain them safely.
    def __init__(self, q):
        super().__init__()
        self._queue = q

    def emit(self, record):
        self._queue.put_nowait(record)


class LogStore:
    #Owns the queue, the handler, and a rolling in-memory buffer of formatted lines.

    # Attach it to the root logger once at startup; any panel can replay or drain it.

    def __init__(self, max_lines=2000):
        self._queue: queue.Queue[logging.LogRecord] = queue.Queue()
        self.handler = QueueHandler(self._queue)
        self.handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S"))
        self.handler.setLevel(logging.INFO)
        self.buffer: list[tuple[str, str]] = []
        self.max_lines = max_lines

    def attach(self):
        root = logging.getLogger()
        if self.handler not in root.handlers:
            root.addHandler(self.handler)

    def detach(self):
        logging.getLogger().removeHandler(self.handler)

    def set_level(self, level):
        self.handler.setLevel(level)

    def drain(self) -> list[tuple[str, str]]:
        # Pull all queued records out, format them, and return as (message, tag) pairs.
        new = []
        try:
            while True:
                record = self._queue.get_nowait()
                msg = self.handler.format(record)
                tag = record.levelname if record.levelname in ThemeEngine.log_level_colors() else "INFO"
                self.buffer.append((msg, tag))
                new.append((msg, tag))
        except queue.Empty:
            pass
        if len(self.buffer) > self.max_lines:
            self.buffer = self.buffer[-self.max_lines:]
        return new

    def replay(self):
        # Return the full buffer
        # Useful when a new panel needs to show past messages.
        return list(self.buffer)

    def clear_buffer(self):
        self.buffer.clear()


class LogPanel(ctk.CTkFrame):
    # Scrollable log display panel backed by a shared LogStore.

    # Polls the store every 120ms on the GUI thread so it never blocks.
    # Supports docking, popping out, minimizing, maximizing, search highlighting, and level filtering.

    _POLL_MS = 120

    def __init__(self, parent, settings, log_store, *,
                 on_dock_request=None, on_minimize=None,
                 on_maximize=None, on_restore=None, is_popup=False):
        super().__init__(parent, fg_color="transparent")
        self._settings        = settings
        self._store           = log_store
        self._on_dock_request = on_dock_request
        self._on_minimize     = on_minimize
        self._on_maximize     = on_maximize
        self._on_restore      = on_restore
        self._is_popup        = is_popup
        self._paused          = False
        self._poll_id         = None
        self._level_var       = tk.StringVar(value=settings.get("log_level", "INFO"))
        self._build_ui()
        self._replay_history()
        self._schedule_poll()
        # Recolors plain tk widgets when CTk fires an appearance mode change
        self.bind("<<AppearanceModeChanged>>", lambda _e: self.refresh_colors(), add=True)

    def destroy(self):
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        super().destroy()

    # public API

    def clear(self):
        self._store.clear_buffer()
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")

    def export(self):
        path = filedialog.asksaveasfilename(
            title="Export Log", defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt")])
        if path:
            Path(path).write_text(self._textbox.get("1.0", "end"), encoding="utf-8")

    def set_minimized(self, minimized):
        self._show_body(not minimized)
        if not self._is_popup:
            self._min_btn.configure(text="▭" if minimized else "─")

    def set_maximized(self, maximized):
        if not self._is_popup:
            self._max_btn.configure(text="❐" if maximized else "□")

    def refresh_colors(self):
        # Re-imports ThemeEngine and reapply colors
        # Called after any appearance change

        import media_manager.gui.widgets as _wid
        _TE = _wid.ThemeEngine
        bar_bg   = _TE.log_bar()
        bar_fg   = _TE.log_bar_fg()
        log_bg   = _TE.log_bg()
        panel_bg = _TE.log_panel()
        colors   = _TE.log_level_colors()
        try:
            self.configure(fg_color=panel_bg)
            self._title_bar.configure(bg=bar_bg)
            for child in self._title_bar.winfo_children():
                try:
                    child.configure(bg=bar_bg, fg=bar_fg)
                except tk.TclError:
                    pass
            self._textbox.configure(fg_color=log_bg)
            tb = self._textbox._textbox
            for level, color in colors.items():
                tb.tag_configure(level, foreground=color)
        except Exception:
            pass

    def refresh_font_size(self):
        size = int(self._settings.get("log_font_size", 12))
        try:
            self._textbox.configure(font=ctk.CTkFont(family="Courier New", size=size))
        except Exception:
            pass

    # UI construction

    def _build_ui(self):
        self._build_title_bar()
        self._build_toolbar()
        self._build_search()
        self._build_textbox()

    def _build_title_bar(self):
        bar_bg = ThemeEngine.log_bar()
        bar_fg = ThemeEngine.log_bar_fg()
        bar = tk.Frame(self, bg=bar_bg, height=LOG_TITLE_H)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        self._title_bar = bar

        tk.Label(bar, text="⠿", bg=bar_bg, fg="#4b5563",
                 font=("Helvetica", 13), cursor="fleur").pack(side="left", padx=(6, 2))
        tk.Label(bar, text="ACTIVITY LOG", bg=bar_bg, fg=bar_fg,
                 font=("Helvetica", 10, "bold")).pack(side="left", padx=(0, 6))

        _ib = dict(
            relief="flat", bd=0, bg=bar_bg,
            activebackground=ThemeEngine.border(),
            fg="#9ca3af",
            activeforeground=ThemeEngine.text(),
            font=("Helvetica", 11), width=3, cursor="hand2", pady=0,
        )

        if not self._is_popup:
            self._max_btn = tk.Button(bar, text="□", **_ib, command=self._on_max_click)
            self._max_btn.pack(side="right", padx=(0, 4), pady=5)
            self._min_btn = tk.Button(bar, text="─", **_ib, command=self._on_min_click)
            self._min_btn.pack(side="right", padx=(0, 2), pady=5)
            tk.Frame(bar, bg=ThemeEngine.border(), width=1).pack(
                side="right", fill="y", pady=6, padx=4)

        dock_label = "⮐ Embed" if self._is_popup else "⊞ Dock"
        self._dock_btn = tk.Button(
            bar, text=f"{dock_label} ▾",
            relief="flat", bd=0, bg=bar_bg,
            activebackground=ThemeEngine.border(),
            fg="#9ca3af",
            activeforeground=ThemeEngine.text(),
            font=("Helvetica", 10), cursor="hand2", pady=0,
            command=self._show_dock_menu,
        )
        self._dock_btn.pack(side="right", padx=(0, 8), pady=5)

    def _build_toolbar(self):
        self._toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self._toolbar.pack(fill="x", padx=6, pady=(3, 2))
        btn_kw = dict(width=70, height=26, font=ctk.CTkFont(size=11))
        self._level_menu_widget = ctk.CTkOptionMenu(
            self._toolbar, variable=self._level_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            width=100, height=26, command=self._on_level_change)
        self._level_menu_widget.pack(side="right", padx=(4, 0))
        ctk.CTkLabel(self._toolbar, text="Level:",
                     font=ctk.CTkFont(size=11)).pack(side="right")
        ctk.CTkButton(self._toolbar, text="Export",
                      command=self.export, **btn_kw).pack(side="right", padx=(4, 4))
        ctk.CTkButton(self._toolbar, text="Clear",
                      command=self.clear, **btn_kw).pack(side="right", padx=(0, 4))
        self._pause_btn = ctk.CTkButton(self._toolbar, text="⏸ Pause",
                                        command=self._toggle_pause, **btn_kw)
        self._pause_btn.pack(side="right", padx=(0, 8))
        self._on_level_change(self._level_var.get())

    def _build_search(self):
        self._search_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._search_frame.pack(fill="x", padx=6, pady=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._highlight_search())
        ctk.CTkLabel(self._search_frame, text="🔍",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkEntry(self._search_frame, textvariable=self._search_var,
                     placeholder_text="Search log…", height=26).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

    def _build_textbox(self):
        font_size = int(self._settings.get("log_font_size", 12))
        self._textbox = ctk.CTkTextbox(
            self, wrap="none", state="disabled",
            font=ctk.CTkFont(family="Courier New", size=font_size),
            fg_color=ThemeEngine.log_bg(),
        )
        self._textbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        colors = ThemeEngine.log_level_colors()
        for level, color in colors.items():
            self._textbox._textbox.tag_configure(level, foreground=color)
        self._textbox._textbox.tag_configure("SEARCH", background=ThemeEngine.border())

    # body visibility

    def _show_body(self, visible):
        if visible:
            self._toolbar.pack(fill="x", padx=6, pady=(3, 2))
            self._search_frame.pack(fill="x", padx=6, pady=(0, 4))
            self._textbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        else:
            self._textbox.pack_forget()
            self._search_frame.pack_forget()
            self._toolbar.pack_forget()

    # dock menu

    def _show_dock_menu(self):
        menu = tk.Menu(self, tearoff=0,
                       bg=ThemeEngine.card(), fg=ThemeEngine.text(),
                       activebackground=ThemeEngine.border(),
                       activeforeground=ThemeEngine.text(),
                       relief="flat", bd=1, font=("Helvetica", 11))
        if self._is_popup:
            menu.add_command(label="⮐  Embed Back",
                             command=lambda: self._request_dock("embed"))
        else:
            for label, pos in [("▼  Dock Bottom", "bottom"), ("▲  Dock Top", "top"),
                                ("◀  Dock Left", "left"), ("▶  Dock Right", "right")]:
                menu.add_command(label=label, command=lambda p=pos: self._request_dock(p))
            menu.add_separator()
            menu.add_command(label="⧉  Pop Out", command=lambda: self._request_dock("popout"))
        x = self._dock_btn.winfo_rootx()
        y = self._dock_btn.winfo_rooty() + self._dock_btn.winfo_height() + 2
        menu.tk_popup(x, y)

    def _request_dock(self, pos):
        if self._on_dock_request:
            self._on_dock_request(pos)

    # minimize / maximize buttons

    def _on_min_click(self):
        if self._min_btn.cget("text") == "▭":
            if self._on_restore: self._on_restore()
        else:
            if self._on_minimize: self._on_minimize()

    def _on_max_click(self):
        if self._max_btn.cget("text") == "❐":
            if self._on_restore: self._on_restore()
        else:
            if self._on_maximize: self._on_maximize()

    # polling

    def _replay_history(self):
        # Write the buffered history into the textbox when the panel first opens.
        history = self._store.replay()
        if not history:
            return
        self._textbox.configure(state="normal")
        tb = self._textbox._textbox
        for msg, tag in history:
            tb.insert("end", msg + "\n", tag)
        if self._settings.get("log_auto_scroll", True):
            self._textbox.see("end")
        self._textbox.configure(state="disabled")

    def _schedule_poll(self):
        try:
            if self.winfo_exists():
                self._poll_id = self.after(self._POLL_MS, self._poll)
        except Exception:
            pass

    def _poll(self):
        self._poll_id = None
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if not self._paused:
            new_items = self._store.drain()
            if new_items:
                self._textbox.configure(state="normal")
                tb = self._textbox._textbox
                for msg, tag in new_items:
                    tb.insert("end", msg + "\n", tag)
                if self._settings.get("log_auto_scroll", True):
                    self._textbox.see("end")
                self._textbox.configure(state="disabled")
        self._schedule_poll()

    def _on_level_change(self, level_str):
        self._store.set_level(getattr(logging, level_str, logging.INFO))
        self._settings["log_level"] = level_str
        self._settings.save()

    def _toggle_pause(self):
        self._paused = not self._paused
        self._pause_btn.configure(text="▶ Resume" if self._paused else "⏸ Pause")

    def _highlight_search(self):
        tb = self._textbox._textbox
        tb.tag_remove("SEARCH", "1.0", "end")
        term = self._search_var.get().strip()
        if not term:
            return
        start = "1.0"
        while True:
            pos = tb.search(term, start, nocase=True, stopindex="end")
            if not pos:
                break
            end_pos = f"{pos}+{len(term)}c"
            tb.tag_add("SEARCH", pos, end_pos)
            start = end_pos

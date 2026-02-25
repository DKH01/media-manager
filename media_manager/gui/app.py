# Main application window
# Sidebar, page routing, log panel docking/resizing.

from __future__ import annotations
import importlib
import logging
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from .log_widget import LogPanel, LogStore, LOG_TITLE_H
from .settings_manager import SettingsManager
from .widgets import ACCENT, ThemeEngine

logger = logging.getLogger(__name__)

_SIDEBAR_W = 220
_NAV_H = 44
_SASH_W = 6
_MIN_LOG = LOG_TITLE_H + 10  # minimum log height, just the title bar with some breathing room
_MIN_CONTENT = 160  # minimum content area so it's still usable

_NAV_ITEMS: list[tuple[str, str]] = [
    ("home", "⌂  Home"),
    ("file_ops", "⚙  File Operations"),
    ("duplicates", "⧉  Duplicates"),
    ("video_converter", "▣  Video Converter"),
    ("settings", "⊙  Settings"),
]


class App(ctk.CTk):
    # Root application window.

    def __init__(self) -> None:
        super().__init__()
        self._settings = SettingsManager()
        ThemeEngine.init(self._settings)

        # Push the saved ffmpeg path into the utils module so all subprocess
        # calls pick it up immediately, even before the settings page opens.
        from media_manager.utils import set_ffmpeg_path
        set_ffmpeg_path(self._settings.get("ffmpeg_path", ""))

        ThemeEngine.on_color_change(self._on_colors_changed)
        self._color_update_pending = False

        # paths to persistent tk widgets, stored to find them reliably even after module reloads
        self._workspace_path = ""
        self._content_path = ""
        self._sash_path = ""
        self._log_wrapper_path = ""

        # seed module-level ACCENT immediately so widgets built in _build_layout use it
        import media_manager.gui.widgets as _wid
        _saved_accent = self._settings.get("accent_color", "#00b4d8")
        _wid.ACCENT = _saved_accent
        _wid.ACCENT_H = _saved_accent

        self._current_page: str = "home"
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}

        self._log_dock = self._resolve_startup_dock()
        self._log_h = int(self._settings.get("log_h", 210))
        self._log_w = int(self._settings.get("log_w", 320))
        self._log_minimized = bool(self._settings.get("log_minimized", False))
        self._log_maximized = False
        self._log_popup: ctk.CTkToplevel | None = None
        self._log_popup_panel: LogPanel | None = None
        self._log_size_before_minmax: int = 0
        self._initial_size_set: bool = False

        self._sash_drag_start_xy: int = 0
        self._sash_drag_start_size: int = 0
        self._layout_after_id: str | None = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_window()
        ctk.set_appearance_mode(self._settings["appearance_mode"])
        ctk.set_default_color_theme("blue")
        self._build_layout()
        self.bind("<<AppearanceModeChanged>>",
                  lambda _e: self.after(25, self._apply_tk_frame_colors), add=True)
        self._navigate("home")

    def _resolve_startup_dock(self) -> str:
        default = self._settings.get("log_default_dock", "bottom")
        if not self._settings.get("log_remember_dock", True):
            return default
        saved = self._settings.get("log_dock", "bottom")
        if saved == "popout":
            # can't restore a popped-out window on launch, fall back to default
            self._settings["log_dock"] = default
            self._settings.save()
            return default
        return saved

    def _configure_window(self) -> None:
        self.title("Media Manager")
        self.geometry("1280x820")
        self.minsize(900, 600)
        ico = Path(__file__).parent / "icon.ico"
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

    def _build_layout(self) -> None:
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        is_light = str(self._settings["appearance_mode"]).lower() == "light"
        if is_light:
            surface_color = str(self._settings["light_surface"])
            sidebar_color = str(self._settings["light_sidebar"])
            border_color = str(self._settings["light_border"])
            log_panel_color = str(self._settings["light_log_panel"])
        else:
            surface_color = str(self._settings["dark_surface"])
            sidebar_color = str(self._settings["dark_sidebar"])
            border_color = str(self._settings["dark_border"])
            log_panel_color = str(self._settings["dark_log_panel"])

        self._sidebar = ctk.CTkFrame(self, width=_SIDEBAR_W,
                                     fg_color=sidebar_color, corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_propagate(False)
        self._sidebar.columnconfigure(0, weight=1)
        self._sidebar.rowconfigure(99, weight=1)
        self._build_sidebar()

        self._workspace = tk.Frame(self, bg=surface_color)
        self._workspace.grid(row=0, column=1, sticky="nsew")

        self._log_store = LogStore(max_lines=int(self._settings.get("log_max_lines", 2000)))
        self._log_store.attach()
        logging.getLogger().setLevel(logging.DEBUG)

        self._content = tk.Frame(self._workspace, bg=surface_color)
        self._content.rowconfigure(0, weight=1)
        self._content.columnconfigure(0, weight=1)

        self._sash = tk.Frame(self._workspace, bg=border_color, cursor="sb_v_double_arrow")
        self._sash.bind("<Button-1>", self._on_sash_press)
        self._sash.bind("<B1-Motion>", self._on_sash_drag)
        self._sash.bind("<ButtonRelease-1>", self._on_sash_release)
        self._sash.bind("<Enter>", lambda _e: self._sash.configure(bg=ACCENT))
        self._sash.bind("<Leave>", lambda _e: self._update_sash_color())

        self._log_wrapper = tk.Frame(self._workspace, bg=log_panel_color)
        self._log_panel = self._make_log_panel(self._log_wrapper)
        self._log_panel.pack(fill="both", expand=True)

        self._store_widget_paths()
        self._build_pages()
        self.update_idletasks()
        self._workspace.bind("<Configure>", self._on_workspace_configure)
        self._apply_layout()

        if not self._settings.get("log_show_on_start", True):
            self._minimize_log()
        elif self._log_minimized:
            self._log_panel.set_minimized(True)

    def _update_sash_color(self) -> None:
        is_light = str(self._settings["appearance_mode"]).lower() == "light"
        color = str(self._settings["light_border"] if is_light else self._settings["dark_border"])
        try:
            self._sash.configure(bg=color)
        except Exception:
            pass

    def _build_sidebar(self) -> None:
        for w in self._sidebar.winfo_children():
            w.destroy()
        self._nav_buttons.clear()

        # re-import to get the freshest ThemeEngine after any reload
        import media_manager.gui.widgets as _w
        accent = _w.ACCENT
        _TE = _w.ThemeEngine

        brand = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(20, 4))
        ctk.CTkLabel(brand, text="Media",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=accent).pack(side="left")
        ctk.CTkLabel(brand, text="Manager",
                     font=ctk.CTkFont(size=22)).pack(side="left")

        ctk.CTkFrame(self._sidebar, height=1,
                     fg_color=_TE.ctk_border()).grid(
            row=1, column=0, sticky="ew", padx=16, pady=(4, 12))

        for i, (page_id, label) in enumerate(_NAV_ITEMS, 2):
            btn = ctk.CTkButton(
                self._sidebar, text=label, anchor="w",
                height=_NAV_H, corner_radius=8,
                fg_color="transparent",
                hover_color=_TE.ctk_nav_hov(),
                font=ctk.CTkFont(size=13),
                text_color=_TE.ctk_nav_txt(),
                command=lambda p=page_id: self._navigate(p),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=10, pady=2)
            self._nav_buttons[page_id] = btn

        ctk.CTkFrame(self._sidebar, fg_color="transparent").grid(
            row=99, column=0, sticky="nsew")
        ctk.CTkFrame(self._sidebar, height=1,
                     fg_color=_TE.ctk_border()).grid(
            row=100, column=0, sticky="ew", padx=16, pady=(4, 0))
        meta = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        meta.grid(row=101, column=0, sticky="ew", padx=16, pady=(8, 16))
        ctk.CTkLabel(meta, text="v1.0.0",
                     font=ctk.CTkFont(size=11),
                     text_color=_TE.ctk_text_dim()).pack(side="left")

        # Author info with clickable links
        import webbrowser
        author_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        author_frame.grid(row=102, column=0, sticky="ew", padx=16, pady=(0, 6))

        def _link(parent, text, url, icon=""):
            full = f"{icon}  {text}" if icon else text
            lbl = ctk.CTkLabel(
                parent, text=full,
                font=ctk.CTkFont(size=11),
                text_color=accent,
                cursor="hand2",
            )
            lbl.pack(anchor="w")
            lbl.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
            lbl.bind("<Enter>", lambda _e: lbl.configure(text_color="#0096c7"))
            lbl.bind("<Leave>", lambda _e: lbl.configure(text_color=accent))

        _link(author_frame, "dkh01.com",        "https://dkh01.com",                                    "🌐")
        _link(author_frame, "DKH01",             "https://github.com/DKH01",                             "🐙")
        _link(author_frame, "media-manager",     "https://github.com/DKH01/media-manager/",              "📦")

    def _build_pages(self) -> None:
        from .pages.home import HomePage
        from .pages.file_ops import FileOpsPage
        from .pages.duplicates import DuplicatesPage
        from .pages.conversion import VideoConverterPage
        from .pages.settings import SettingsPage

        page_defs = [
            ("home", HomePage, {"navigate": self._navigate}),
            ("file_ops", FileOpsPage, {}),
            ("duplicates", DuplicatesPage, {}),
            ("video_converter", VideoConverterPage, {}),
            ("settings", SettingsPage, {
                "on_rebuild": self.rebuild_ui,
                "on_reset_all": self._full_reset,
                "on_apply_colors": self.apply_colors_now,
            }),
        ]
        for page_id, cls, extra_kwargs in page_defs:
            wrapper = ctk.CTkFrame(self._content, fg_color="transparent", corner_radius=0)
            wrapper.grid(row=0, column=0, sticky="nsew")
            wrapper.rowconfigure(0, weight=1)
            wrapper.columnconfigure(0, weight=1)
            page = cls(wrapper, self._settings, **extra_kwargs)
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[page_id] = wrapper

    def _make_log_panel(self, parent, is_popup=False) -> LogPanel:
        return LogPanel(
            parent, self._settings, self._log_store,
            on_dock_request=self._request_dock,
            on_minimize=self._minimize_log,
            on_maximize=self._maximize_log,
            on_restore=self._restore_log,
            is_popup=is_popup,
        )

    # color application

    def _store_widget_paths(self) -> None:
        # Save widget paths to find them reliably after module reloads
        self._workspace_path = str(self._workspace) if hasattr(self, "_workspace") and self._workspace else ""
        self._content_path = str(self._content) if hasattr(self, "_content") and self._content else ""
        self._sash_path = str(self._sash) if hasattr(self, "_sash") and self._sash else ""
        self._log_wrapper_path = str(self._log_wrapper) if hasattr(self, "_log_wrapper") and self._log_wrapper else ""
        logger.debug("Stored widget paths: workspace=%s, content=%s, sash=%s, log_wrapper=%s",
                     self._workspace_path, self._content_path, self._sash_path, self._log_wrapper_path)

    def _get_widget_by_path(self, path: str):
        if not path:
            logger.debug("_get_widget_by_path: empty path")
            return None
        try:
            return self.nametowidget(path)
        except Exception as e:
            logger.debug("_get_widget_by_path: failed to find %s: %s", path, e)
            return None

    def _apply_tk_frame_colors(self) -> None:
        # Push the current custom surface colors to all persistent tk.Frames.

        settings = self._settings
        is_light = str(settings["appearance_mode"]).lower() == "light"

        if is_light:
            surf = str(settings["light_surface"])
            sash_color = str(settings["light_border"])
            panel = str(settings["light_log_panel"])
        else:
            surf = str(settings["dark_surface"])
            sash_color = str(settings["dark_border"])
            panel = str(settings["dark_log_panel"])

        logger.debug("_apply_tk_frame_colors: surface=%s", surf)

        for path, color in [
            (self._workspace_path, surf),
            (self._content_path, surf),
        ]:
            widget = self._get_widget_by_path(path)
            if widget:
                try:
                    widget.configure(bg=color)
                except Exception as e:
                    logger.debug("Failed to configure bg: %s", e)

        sash = self._get_widget_by_path(self._sash_path)
        if sash:
            try:
                sash.configure(bg=sash_color)
            except Exception:
                pass

        log_wrapper = self._get_widget_by_path(self._log_wrapper_path)
        if log_wrapper:
            try:
                log_wrapper.configure(bg=panel)
            except Exception:
                pass

        if hasattr(self, "_log_panel") and self._log_panel is not None:
            try:
                if self._log_panel.winfo_exists():
                    self._log_panel.refresh_colors()
            except Exception:
                pass

    def _on_colors_changed(self) -> None:
        # Called by ThemeEngine when any color setting changes.

        # Batches rapid changes to avoid flickering
        # Multiple calls in quick succession collapse into a single update.

        if hasattr(self, "_color_update_pending") and self._color_update_pending:
            return
        self._color_update_pending = True

        def do_update():
            self._color_update_pending = False
            self._apply_tk_frame_colors()
            if hasattr(self, "_sidebar") and self._sidebar is not None:
                try:
                    if self._sidebar.winfo_exists():
                        settings = self._settings
                        is_light = str(settings["appearance_mode"]).lower() == "light"
                        sidebar_color = str(settings["light_sidebar"] if is_light else settings["dark_sidebar"])
                        self._sidebar.configure(fg_color=sidebar_color)
                except Exception as e:
                    logger.debug("Failed to update sidebar color: %s", e)

        self.after(10, do_update)

    def apply_colors_now(self) -> None:
        # Immediately apply current color settings
        # Called by the Settings page.
        logger.debug("apply_colors_now called")
        self._apply_tk_frame_colors()
        if hasattr(self, "_sidebar") and self._sidebar is not None:
            try:
                if self._sidebar.winfo_exists():
                    settings = self._settings
                    is_light = str(settings["appearance_mode"]).lower() == "light"
                    sidebar_color = str(settings["light_sidebar"] if is_light else settings["dark_sidebar"])
                    self._sidebar.configure(fg_color=sidebar_color)
            except Exception as e:
                logger.debug("Failed to apply sidebar color: %s", e)

    # UI rebuild

    def rebuild_ui(self) -> None:
        # Rebuild pages, sidebar, and recolor all frames after any appearance change.

        # The settings dict must be updated before calling this.
        # Save settings page scroll position to restore it after the rebuild

        _scroll_y: float = 0.0
        try:
            sw = self._pages.get("settings")
            if sw:
                for child in sw.winfo_children():
                    if hasattr(child, "_parent_canvas"):
                        _scroll_y = child._parent_canvas.yview()[0]
                        break
        except Exception:
            pass

        import media_manager.gui.pages.home as _home
        import media_manager.gui.pages.file_ops as _file_ops
        import media_manager.gui.pages.duplicates as _dups
        import media_manager.gui.pages.conversion as _vc
        import media_manager.gui.pages.settings as _sett
        import media_manager.gui.widgets as _wid

        saved_accent = _wid.ACCENT
        # clear callbacks before reload, references old class instances
        _wid.ThemeEngine._color_change_callbacks.clear()

        for mod in [_wid, _home, _file_ops, _dups, _vc, _sett]:
            importlib.reload(mod)

        import media_manager.gui.widgets as _wid2
        _wid2.ACCENT = saved_accent
        _wid2.ACCENT_H = saved_accent
        _wid2.ThemeEngine.init(self._settings)
        _wid2.ThemeEngine.on_color_change(self._on_colors_changed)

        self.update_idletasks()

        for wrapper in self._pages.values():
            wrapper.destroy()
        self._pages.clear()
        self._nav_buttons.clear()

        ctk.set_appearance_mode(self._settings["appearance_mode"])

        is_light = str(self._settings["appearance_mode"]).lower() == "light"
        surface_color = str(self._settings["light_surface"] if is_light else self._settings["dark_surface"])
        sidebar_color = str(self._settings["light_sidebar"] if is_light else self._settings["dark_sidebar"])

        if hasattr(self, "_sidebar") and self._sidebar is not None:
            try:
                if self._sidebar.winfo_exists():
                    self._sidebar.configure(fg_color=sidebar_color)
            except Exception:
                pass

        self._build_sidebar()

        # apply surface color before building pages
        for path, color in [
            (self._workspace_path, surface_color),
            (self._content_path, surface_color),
        ]:
            widget = self._get_widget_by_path(path)
            if widget:
                try:
                    widget.configure(bg=color)
                except Exception:
                    pass

        self._build_pages()
        self._navigate(self._current_page or "home")

        try:
            self._log_panel.refresh_font_size()
        except Exception:
            pass

        self.update_idletasks()
        self._apply_layout()
        self.after(25, self._apply_tk_frame_colors)

        if _scroll_y > 0.001:
            def _restore_scroll(y=_scroll_y):
                try:
                    sw = self._pages.get("settings")
                    if sw:
                        for child in sw.winfo_children():
                            if hasattr(child, "_parent_canvas"):
                                child._parent_canvas.yview_moveto(y)
                                break
                except Exception:
                    pass

            self.after(120, _restore_scroll)

        logger.info("UI rebuilt successfully.")

    def _full_reset(self) -> None:
        if self._log_popup is not None:
            try:
                self._log_popup.protocol("WM_DELETE_WINDOW", lambda: None)
                self._log_popup.destroy()
            except Exception:
                pass
            self._log_popup = None
            self._log_popup_panel = None

        self._settings.reset()

        import media_manager.gui.widgets as _w
        _w.ACCENT = self._settings["accent_color"]
        ThemeEngine.init(self._settings)

        self._log_dock = self._resolve_startup_dock()
        self._log_h = int(self._settings.get("log_h", 210))
        self._log_w = int(self._settings.get("log_w", 320))
        self._log_minimized = False
        self._log_maximized = False
        self._initial_size_set = False

        self.rebuild_ui()
        logger.info("All settings reset to factory defaults.")

    # navigation

    def _navigate(self, page_id: str) -> None:
        if page_id not in self._pages:
            logger.warning("Unknown page: %s", page_id)
            return
        self._pages[page_id].tkraise()
        self._current_page = page_id

        import media_manager.gui.widgets as _w
        accent = _w.ACCENT
        _TE = _w.ThemeEngine
        for pid, btn in self._nav_buttons.items():
            btn.configure(
                fg_color=_TE.ctk_nav_act() if pid == page_id else "transparent",
                text_color=accent if pid == page_id else _TE.ctk_nav_txt(),
            )

    # log panel pop-out / embed

    def _popout_log(self) -> None:
        if self._log_popup is not None:
            self._log_popup.lift()
            return
        self._log_minimized = False
        self._log_maximized = False
        self._log_panel.set_minimized(False)
        self._log_panel.set_maximized(False)
        self._log_dock = "popout"
        self._apply_layout()

        popup = ctk.CTkToplevel(self)
        popup.title("Activity Log === Media Manager")
        popup.geometry("760x420")
        popup.minsize(400, 200)
        popup.protocol("WM_DELETE_WINDOW", self._embed_log)
        self._log_popup = popup
        panel = self._make_log_panel(popup, is_popup=True)
        panel.pack(fill="both", expand=True)
        self._log_popup_panel = panel

    def _embed_log(self) -> None:
        if self._log_popup is not None:
            try:
                self._log_popup.destroy()
            except Exception:
                pass
            self._log_popup = None
            self._log_popup_panel = None
        default = self._settings.get("log_default_dock", "bottom")
        self._log_dock = default
        self._settings["log_dock"] = default
        self._settings.save()
        self._apply_layout()

    # minimize / maximize / restore

    def _minimize_log(self) -> None:
        if self._log_dock == "popout":
            return
        if not self._log_maximized:
            self._log_size_before_minmax = self._log_size_for(self._log_dock)
        self._log_minimized = True
        self._log_maximized = False
        self._set_log_size(self._log_dock, LOG_TITLE_H)
        self._log_panel.set_minimized(True)
        self._log_panel.set_maximized(False)
        self._apply_layout()
        self._save_log_size()

    def _maximize_log(self) -> None:
        if self._log_dock == "popout":
            return
        if not self._log_minimized:
            self._log_size_before_minmax = self._log_size_for(self._log_dock)
        ws = self._workspace
        dock = self._log_dock
        if dock in ("bottom", "top"):
            max_size = max(ws.winfo_height() - _SASH_W - _MIN_CONTENT, _MIN_LOG)
        else:
            max_size = max(ws.winfo_width() - _SASH_W - _MIN_CONTENT, _MIN_LOG)
        self._log_minimized = False
        self._log_maximized = True
        self._set_log_size(dock, max_size)
        self._log_panel.set_minimized(False)
        self._log_panel.set_maximized(True)
        self._apply_layout()
        self._save_log_size()

    def _restore_log(self) -> None:
        if self._log_dock == "popout":
            return
        if self._log_size_before_minmax:
            restore = self._log_size_before_minmax
        else:
            ws = self._workspace
            pct = int(self._settings.get("log_default_size_pct", 25)) / 100
            if self._log_dock in ("bottom", "top"):
                restore = max(_MIN_LOG, int(ws.winfo_height() * pct))
            else:
                restore = max(_MIN_LOG, int(ws.winfo_width() * pct))
        self._log_minimized = False
        self._log_maximized = False
        self._set_log_size(self._log_dock, restore)
        self._log_panel.set_minimized(False)
        self._log_panel.set_maximized(False)
        self._apply_layout()
        self._save_log_size()

    # dock control

    def _request_dock(self, pos: str) -> None:
        if pos == "embed":
            self._embed_log()
        elif pos == "popout":
            self._popout_log()
        elif pos in ("bottom", "top", "left", "right"):
            self._change_dock(pos)

    def _change_dock(self, new_pos: str) -> None:
        if new_pos == self._log_dock:
            return
        self._log_minimized = False
        self._log_maximized = False
        self._log_panel.set_minimized(False)
        self._log_panel.set_maximized(False)
        self._log_dock = new_pos
        self._settings["log_dock"] = new_pos
        self._settings.save()
        self._apply_layout()

    # layout engine

    def _on_workspace_configure(self, _event) -> None:
        # debounce: cancel any pending relayout and schedule a fresh one
        if self._layout_after_id is not None:
            try:
                self.after_cancel(self._layout_after_id)
            except Exception:
                pass
        self._layout_after_id = self.after(30, self._apply_layout)

    def _apply_layout(self) -> None:
        self._layout_after_id = None
        ws = self._workspace
        wh = ws.winfo_height()
        ww = ws.winfo_width()
        if wh < 2 or ww < 2:
            # window not ready yet
            self._layout_after_id = self.after(20, self._apply_layout)
            return

        if not self._initial_size_set:
            self._initial_size_set = True
            pct = int(self._settings.get("log_default_size_pct", 25)) / 100
            if not self._settings.get("log_remember_dock", True):
                self._log_h = max(_MIN_LOG, int(wh * pct))
                self._log_w = max(_MIN_LOG, int(ww * pct))
            else:
                self._log_h = max(_MIN_LOG, min(self._log_h, wh - _SASH_W - _MIN_CONTENT))
                self._log_w = max(_MIN_LOG, min(self._log_w, ww - _SASH_W - _MIN_CONTENT))

        dock = self._log_dock
        self._content.place_forget()
        self._sash.place_forget()
        self._log_wrapper.place_forget()

        if dock == "popout":
            self._content.place(x=0, y=0, width=ww, height=wh)
            return

        if dock in ("bottom", "top"):
            log_size = max(_MIN_LOG, min(self._log_h, wh - _SASH_W - _MIN_CONTENT))
            self._log_h = log_size
            content_sz = wh - _SASH_W - log_size
            self._sash.configure(cursor="sb_v_double_arrow")
            if dock == "bottom":
                self._content.place(x=0, y=0, width=ww, height=content_sz)
                self._sash.place(x=0, y=content_sz, width=ww, height=_SASH_W)
                self._log_wrapper.place(x=0, y=content_sz + _SASH_W, width=ww, height=log_size)
            else:
                self._log_wrapper.place(x=0, y=0, width=ww, height=log_size)
                self._sash.place(x=0, y=log_size, width=ww, height=_SASH_W)
                self._content.place(x=0, y=log_size + _SASH_W, width=ww, height=content_sz)
        else:
            log_size = max(_MIN_LOG, min(self._log_w, ww - _SASH_W - _MIN_CONTENT))
            self._log_w = log_size
            content_sz = ww - _SASH_W - log_size
            self._sash.configure(cursor="sb_h_double_arrow")
            if dock == "right":
                self._content.place(x=0, y=0, width=content_sz, height=wh)
                self._sash.place(x=content_sz, y=0, width=_SASH_W, height=wh)
                self._log_wrapper.place(x=content_sz + _SASH_W, y=0, width=log_size, height=wh)
            else:
                self._log_wrapper.place(x=0, y=0, width=log_size, height=wh)
                self._sash.place(x=log_size, y=0, width=_SASH_W, height=wh)
                self._content.place(x=log_size + _SASH_W, y=0, width=content_sz, height=wh)

    # size helpers

    def _log_size_for(self, dock):
        return self._log_h if dock in ("bottom", "top") else self._log_w

    def _set_log_size(self, dock, size):
        if dock in ("bottom", "top"):
            self._log_h = size
        else:
            self._log_w = size

    def _save_log_size(self) -> None:
        if not self._settings.get("log_remember_dock", True):
            return
        self._settings.update({
            "log_h": self._log_h, "log_w": self._log_w,
            "log_minimized": self._log_minimized, "log_dock": self._log_dock,
        })
        self._settings.save()

    # sash dragging

    def _on_sash_press(self, event) -> None:
        dock = self._log_dock
        self._sash_drag_start_xy = event.y_root if dock in ("bottom", "top") else event.x_root
        self._sash_drag_start_size = self._log_size_for(dock)

    def _on_sash_drag(self, event) -> None:
        dock = self._log_dock
        wh = self._workspace.winfo_height()
        ww = self._workspace.winfo_width()
        if dock in ("bottom", "top"):
            delta = event.y_root - self._sash_drag_start_xy
            max_size = wh - _SASH_W - _MIN_CONTENT
            new_size = self._sash_drag_start_size + (delta if dock == "top" else -delta)
        else:
            delta = event.x_root - self._sash_drag_start_xy
            max_size = ww - _SASH_W - _MIN_CONTENT
            new_size = self._sash_drag_start_size + (delta if dock == "left" else -delta)
        new_size = max(_MIN_LOG, min(new_size, max_size))
        self._set_log_size(dock, new_size)
        if self._log_minimized or self._log_maximized:
            self._log_minimized = False
            self._log_maximized = False
            self._log_panel.set_minimized(False)
            self._log_panel.set_maximized(False)
        self._apply_layout()

    def _on_sash_release(self, _event) -> None:
        self._save_log_size()

    # shutdown

    def _on_close(self) -> None:
        if self._log_popup is not None:
            try:
                self._log_popup.protocol("WM_DELETE_WINDOW", lambda: None)
                self._log_popup.destroy()
            except Exception:
                pass
            self._log_popup = None
            self._log_popup_panel = None
        if self._log_dock == "popout":
            self._log_dock = self._settings.get("log_default_dock", "bottom")
        self._save_log_size()
        self.destroy()


def launch() -> None:
    App().mainloop()
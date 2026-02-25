# Home / Dashboard page
# Quick stats, shortcut cards, and dependency status.

from __future__ import annotations

import tkinter as tk
from typing import Callable, TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from ..settings_manager import SettingsManager


class HomePage(ctk.CTkScrollableFrame):
    # Landing page with overview stats and navigation shortcuts.

    def __init__(self, parent: tk.Widget, settings: "SettingsManager",
                 navigate: Callable[[str], None]) -> None:
        super().__init__(parent, fg_color="transparent")
        self._settings = settings
        self._navigate = navigate
        self._stats: dict = {}
        self._build()

    def update_stat(self, key: str, value: str) -> None:
        if key in self._stats:
            self._stats[key].set(value)

    def _build(self) -> None:
        # always re-import to pick up the freshest ThemeEngine/ACCENT
        # after any module reload triggered by a theme or color change
        import media_manager.gui.widgets as _w
        _TE    = _w.ThemeEngine
        accent = _w.ACCENT

        # two-tuples so CTk auto-updates if mode changes without a full rebuild
        c_card   = _TE.ctk_card()
        c_border = _TE.ctk_border()
        c_dim    = _TE.ctk_text_dim()

        # hero banner
        hero = ctk.CTkFrame(self, fg_color=c_card, corner_radius=14,
                             border_width=1, border_color=c_border)
        hero.pack(fill="x", padx=20, pady=(20, 10))

        inner = ctk.CTkFrame(hero, fg_color="transparent")
        inner.pack(padx=24, pady=20, fill="x")

        ctk.CTkLabel(inner, text="Media Manager",
                     font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(inner,
                     text="Rename · Convert · Deduplicate · Compress: all in one place.",
                     font=ctk.CTkFont(size=13), text_color=c_dim).pack(anchor="w", pady=(2, 6))

        # Author / links row
        import webbrowser
        links_row = ctk.CTkFrame(inner, fg_color="transparent")
        links_row.pack(anchor="w", pady=(0, 10))

        def _hero_link(text, url):
            lbl = ctk.CTkLabel(links_row, text=text,
                               font=ctk.CTkFont(size=11),
                               text_color=accent, cursor="hand2")
            lbl.pack(side="left", padx=(0, 14))
            lbl.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
            lbl.bind("<Enter>", lambda _e: lbl.configure(text_color="#0096c7"))
            lbl.bind("<Leave>", lambda _e: lbl.configure(text_color=accent))

        _hero_link("🌐  dkh01.com",          "https://dkh01.com")
        _hero_link("🐙  github.com/DKH01",   "https://github.com/DKH01")
        _hero_link("📦  media-manager repo", "https://github.com/DKH01/media-manager/")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(anchor="w")
        ctk.CTkButton(
            btn_row, text="Open File Operations ->",
            command=lambda: self._navigate("file_ops"),
            fg_color=accent, hover_color="#0096c7",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Detect Duplicates ->",
            command=lambda: self._navigate("duplicates"),
            fg_color="transparent", border_color=accent, border_width=1,
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        # stat badges
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=8)
        stats_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="stat")

        stat_defs = [
            ("files_processed",  "Files Processed"),
            ("duplicates_found", "Duplicates Found"),
            ("space_saved",      "Space Freed"),
            ("conversions_done", "Conversions Done"),
        ]
        for col, (key, label) in enumerate(stat_defs):
            badge = _w.StatBadge(stats_frame, label, "0")
            badge.grid(row=0, column=col, padx=5, sticky="nsew")
            self._stats[key] = badge

        # quick action shortcuts
        self._section("QUICK ACTIONS", c_dim)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(4, 12))
        actions.columnconfigure((0, 1, 2), weight=1, uniform="qa")

        quick = [
            ("🖼  Rename Images", "file_ops", "Batch-rename JPG/BMP/TIFF -> PNG"),
            ("🎬  Convert GIFs", "file_ops", "Convert .gif files to web-ready MP4"),
            ("🔍  Find Duplicates", "duplicates", "SHA-256 or perceptual video hashing"),
            ("📐  Multi-Resolution", "video_converter","Export a video at multiple sizes"),
            ("🔧  Fix MP4 Compat.", "file_ops", "Enforce even pixel dimensions"),
            ("⚙️  Settings", "settings", "Thresholds, workers, appearance"),
        ]
        for i, (title, page, subtitle) in enumerate(quick):
            col, row = i % 3, i // 3
            card = ctk.CTkFrame(actions, fg_color=c_card, corner_radius=10,
                                 border_width=1, border_color=c_border, cursor="hand2")
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            _nav = lambda e, p=page: self._navigate(p)
            card.bind("<Button-1>", _nav)

            inner_card = ctk.CTkFrame(card, fg_color="transparent")
            inner_card.pack(padx=14, pady=12, fill="both")
            inner_card.bind("<Button-1>", _nav)

            title_lbl = ctk.CTkLabel(inner_card, text=title,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         justify="left", cursor="hand2")
            title_lbl.pack(anchor="w")
            title_lbl.bind("<Button-1>", _nav)

            sub_lbl = ctk.CTkLabel(inner_card, text=subtitle,
                         font=ctk.CTkFont(size=11),
                         text_color=c_dim, justify="left",
                         wraplength=200, cursor="hand2")
            sub_lbl.pack(anchor="w", pady=(2, 0))
            sub_lbl.bind("<Button-1>", _nav)

        # dependency status
        self._section("SYSTEM STATUS", c_dim)
        status_card = ctk.CTkFrame(self, fg_color=c_card, corner_radius=10,
                                    border_width=1, border_color=c_border)
        status_card.pack(fill="x", padx=20, pady=(0, 20))
        inner_s = ctk.CTkFrame(status_card, fg_color="transparent")
        inner_s.pack(padx=16, pady=12, fill="x")

        for label, check_fn in [
            ("ffmpeg",       self._check_ffmpeg),
            ("OpenCV",       self._check_cv2),
            ("MoviePy",      self._check_moviepy),
            ("scikit-image", self._check_skimage),
        ]:
            ok, version = check_fn()
            row_f = ctk.CTkFrame(inner_s, fg_color="transparent")
            row_f.pack(fill="x", pady=2)
            color = accent if ok else "#f87171"
            icon  = "✔" if ok else "✘"
            ctk.CTkLabel(row_f, text=f"{icon}  {label}",
                         font=ctk.CTkFont(size=12), text_color=color).pack(side="left")
            ctk.CTkLabel(row_f, text=version,
                         font=ctk.CTkFont(size=11), text_color=c_dim).pack(side="right")

    def _section(self, title: str, c_dim=None) -> None:
        if c_dim is None:
            import media_manager.gui.widgets as _w
            c_dim = _w.ThemeEngine.ctk_text_dim()
        ctk.CTkLabel(self, text=title,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=c_dim).pack(anchor="w", padx=20, pady=(10, 2))

    # dependency checks
    # each returns (ok, version_string)

    @staticmethod
    def _check_ffmpeg() -> tuple[bool, str]:
        from media_manager.utils import verify_ffmpeg
        return verify_ffmpeg()

    @staticmethod
    def _check_cv2() -> tuple[bool, str]:
        try:
            import cv2
            return True, cv2.__version__
        except ImportError:
            return False, "not installed"

    @staticmethod
    def _check_moviepy() -> tuple[bool, str]:
        try:
            import moviepy
            return True, getattr(moviepy, "__version__", "installed")
        except ImportError:
            return False, "not installed"

    @staticmethod
    def _check_skimage() -> tuple[bool, str]:
        try:
            import skimage
            return True, skimage.__version__
        except ImportError:
            return False, "not installed (SSIM comparison unavailable)"
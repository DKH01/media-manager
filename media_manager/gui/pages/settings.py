# Settings page
# Appearance, color presets, and every other tunable.

# All changes are saved to disk immediately (Theme/accent/color changes)
# call on_rebuild which triggers App.rebuild_ui()
# The settings dict is updated first so ThemeEngine reads the right values during the rebuild.

from __future__ import annotations
import logging
import tkinter as tk
import uuid
from tkinter import colorchooser, messagebox
from typing import TYPE_CHECKING, Callable
import customtkinter as ctk
from ..widgets import ACCENT, ThemeEngine, SectionCard, LabeledSlider

if TYPE_CHECKING:
    from ..settings_manager import SettingsManager
    from ..settings_manager import DEFAULTS as SM_DEFAULTS

logger = logging.getLogger(__name__)

_ACCENT_PRESETS = [
    ("#00b4d8", "Cyan"),  ("#3b82f6", "Blue"),  ("#8b5cf6", "Purple"),
    ("#ec4899", "Pink"),  ("#10b981", "Green"),  ("#f59e0b", "Amber"),
    ("#ef4444", "Red"),   ("#f97316", "Orange"),
]

_DARK_color_SLOTS = [
    ("dark_surface",   "Workspace background"),
    ("dark_sidebar",   "Sidebar"),
    ("dark_card",      "Cards / panels"),
    ("dark_border",    "Borders & dividers"),
    ("dark_text",      "Primary text"),
    ("dark_text_dim",  "Secondary text"),
    ("dark_log_panel", "Activity log workspace background"),
    ("dark_log_bg",    "Activity log text background"),
    ("dark_log_bar",   "Activity log title bar"),
]
_LIGHT_color_SLOTS = [
    ("light_surface",   "Workspace background"),
    ("light_sidebar",   "Sidebar"),
    ("light_card",      "Cards / panels"),
    ("light_border",    "Borders & dividers"),
    ("light_text",      "Primary text"),
    ("light_text_dim",  "Secondary text"),
    ("light_log_panel", "Activity log workspace background"),
    ("light_log_bg",    "Activity log text background"),
    ("light_log_bar",   "Activity log title bar"),
]

_ALL_color_KEYS = [k for k, _ in _DARK_color_SLOTS + _LIGHT_color_SLOTS]


def _current_accent():
    import media_manager.gui.widgets as _w
    return _w.ACCENT


class SettingsPage(ctk.CTkScrollableFrame):
    # Full settings editor
    # Every change is saved to disk immediately.

    def __init__(self, parent, settings: "SettingsManager",
                 on_rebuild: Callable[[], None] | None = None,
                 on_reset_all: Callable[[], None] | None = None,
                 on_apply_colors: Callable[[], None] | None = None):
        super().__init__(parent, fg_color="transparent")
        self._settings        = settings
        self._on_rebuild      = on_rebuild
        self._on_reset_all    = on_reset_all
        self._on_apply_colors = on_apply_colors
        self._vars: dict[str, tk.Variable] = {}
        self._accent_var      = tk.StringVar(value=settings["accent_color"])
        self._swatch_buttons: list[ctk.CTkButton] = []
        self._color_swatches: dict[str, ctk.CTkFrame] = {}
        self._build()

    def _build(self):
        pad = dict(fill="x", padx=20, pady=6)
        TEXT_DIM = ThemeEngine.ctk_text_dim()

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(20, 4))
        ctk.CTkLabel(hdr, text="Settings",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkButton(hdr, text="↺  Reset to Defaults",
                      fg_color="#374151", hover_color="#4b5563",
                      width=150, command=self._reset).pack(side="right")
        ctk.CTkLabel(self, text="All changes are saved automatically as you make them.",
                     font=ctk.CTkFont(size=13),
                     text_color=TEXT_DIM).pack(anchor="w", padx=20, pady=(0, 12))

        # appearance: theme + accent color
        app_card = SectionCard(self, "Appearance")
        app_card.pack(**pad)

        theme_row = ctk.CTkFrame(app_card.body, fg_color="transparent")
        theme_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(theme_row, text="Theme", font=ctk.CTkFont(size=12),
                     width=160, anchor="w").pack(side="left")
        self._theme_var = tk.StringVar(value=self._settings["appearance_mode"])
        _theme_values = self._theme_dropdown_values()
        self._theme_dropdown = ctk.CTkOptionMenu(
            theme_row, variable=self._theme_var,
            values=_theme_values, width=200,
            command=self._on_theme_change,
        )
        self._theme_dropdown.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(app_card.body, text="Accent Color",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(0, 6))
        swatch_row = ctk.CTkFrame(app_card.body, fg_color="transparent")
        swatch_row.pack(anchor="w", pady=(0, 8))
        self._swatch_buttons.clear()
        for hex_color, name in _ACCENT_PRESETS:
            btn = ctk.CTkButton(
                swatch_row, text="", width=34, height=34, corner_radius=8,
                fg_color=hex_color, hover_color=hex_color,
                border_width=3, border_color=ThemeEngine.ctk_border(),
                command=lambda c=hex_color: self._set_accent(c),
            )
            btn.pack(side="left", padx=3)
            self._swatch_buttons.append(btn)

        custom_row = ctk.CTkFrame(app_card.body, fg_color="transparent")
        custom_row.pack(anchor="w", pady=(0, 4))
        self._preview_swatch = ctk.CTkFrame(
            custom_row, width=34, height=34, corner_radius=8,
            fg_color=self._settings["accent_color"])
        self._preview_swatch.pack(side="left", padx=(0, 8))
        self._preview_swatch.pack_propagate(False)
        self._accent_entry = ctk.CTkEntry(custom_row, textvariable=self._accent_var,
                                          width=100, placeholder_text="#00b4d8")
        self._accent_entry.pack(side="left", padx=(0, 8))
        self._accent_entry.bind("<Return>",   lambda e: self._set_accent(self._accent_var.get()))
        self._accent_entry.bind("<FocusOut>", lambda e: self._set_accent(self._accent_var.get()))
        ctk.CTkButton(custom_row, text="Pick…", width=80, height=34,
                      fg_color="#374151", hover_color="#4b5563",
                      command=self._pick_accent).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(app_card.body,
                     text="Accent and theme changes rebuild the UI immediately, no restart needed.",
                     font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(anchor="w", pady=(2, 0))
        self._update_swatch_borders(self._settings["accent_color"])

        self._build_advanced_appearance(pad, TEXT_DIM)

        # general settings
        gen_card = SectionCard(self, "General")
        gen_card.pack(**pad)
        self._add_bool(gen_card.body, "auto_nested",
                       "Always include sub-folders without prompting (AUTO_NESTED)")
        self._add_slider(gen_card.body, "max_filename_length", "Max filename length",
                         from_=80, to=255, step=1)
        self._add_slider(gen_card.body, "default_max_workers", "Default thread workers",
                         from_=1, to=32, step=1)

        # perceptual hashing
        phash_card = SectionCard(self, "Perceptual Hashing (pHash)")
        phash_card.pack(**pad)
        ctk.CTkLabel(phash_card.body,
                     text="pHash compares videos frame-by-frame using grayscale thumbnails.\n"
                          "Lower thresholds = stricter matching (fewer false positives).",
                     font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(anchor="w", pady=(0, 8))
        self._add_slider(phash_card.body, "phash_base_threshold",
                         "Match threshold (Hamming distance ≤ this = match)", from_=0, to=16, step=1)
        self._add_slider(phash_card.body, "phash_gray_zone",
                         "Gray-zone range (needs deeper analysis)", from_=0, to=8, step=1)
        self._add_slider(phash_card.body, "phash_frame_samples",
                         "Frames sampled per video", from_=4, to=64, step=2)

        # quality scoring
        score_card = SectionCard(self, "Duplicate Quality Scoring")
        score_card.pack(**pad)
        ctk.CTkLabel(score_card.body,
                     text="Weights determine which copy is kept as 'best'. They should sum to 1.0.",
                     font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(anchor="w", pady=(0, 8))
        self._add_slider(score_card.body, "score_weight_resolution", "Resolution weight",
                         from_=0.0, to=1.0, step=0.05, fmt="{:.2f}")
        self._add_slider(score_card.body, "score_weight_bitrate", "Bitrate weight",
                         from_=0.0, to=1.0, step=0.05, fmt="{:.2f}")
        self._add_slider(score_card.body, "score_weight_duration", "Duration weight",
                         from_=0.0, to=1.0, step=0.05, fmt="{:.2f}")

        # duplicate handling defaults
        dup_card = SectionCard(self, "Duplicate Handling Defaults")
        dup_card.pack(**pad)
        self._add_option(dup_card.body, "duplicate_action", "Default action", ["move", "delete"])
        self._add_bool(dup_card.body, "create_placeholders",
                       "Create blank placeholder files by default")
        self._add_bool(dup_card.body, "use_threading",
                       "Use multi-threading for hash computation by default")
        self._add_bool(dup_card.body, "use_best_video",
                       "Keep highest-quality version when auto-resolving duplicates")

        # video conversion defaults
        vid_card = SectionCard(self, "Video Conversion Defaults")
        vid_card.pack(**pad)
        self._add_option(vid_card.body, "video_encode_preset", "ffmpeg encoding preset",
                         ["ultrafast","superfast","veryfast","faster",
                          "fast","medium","slow","slower","veryslow"])
        self._add_option(vid_card.body, "audio_bitrate", "Audio bitrate",
                         ["64k","96k","128k","192k","256k","320k"])
        self._add_slider(vid_card.body, "gif_retry_count",
                         "GIF conversion retry count (on MemoryError)", from_=0, to=10, step=1)

        # ffmpeg / dependencies
        dep_card = SectionCard(self, "Dependencies - ffmpeg")
        dep_card.pack(**pad)
        self._build_ffmpeg_section(dep_card.body, TEXT_DIM)

        # logging
        log_card = SectionCard(self, "Logging")
        log_card.pack(**pad)
        self._add_option(log_card.body, "log_level", "Log level",
                         ["DEBUG", "INFO", "WARNING", "ERROR"])
        self._add_bool(log_card.body, "log_to_file", "Also write log to a file")
        self._add_entry(log_card.body, "log_file_path", "Log file path")

        # terminal / activity log panel
        term_card = SectionCard(self, "Terminal / Activity Log")
        term_card.pack(**pad)
        ctk.CTkLabel(term_card.body,
                     text="Controls how the Activity Log terminal panel behaves.\n"
                          "Changes to dock/size settings take effect on the next launch.",
                     font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(anchor="w", pady=(0, 10))
        self._add_bool(term_card.body, "log_remember_dock",
                       "Remember dock position and size between sessions")
        self._add_bool(term_card.body, "log_show_on_start",
                       "Show terminal panel when the app starts")
        self._add_option(term_card.body, "log_default_dock", "Default dock position",
                         ["bottom", "top", "left", "right"])
        self._add_slider(term_card.body, "log_default_size_pct",
                         "Default terminal size (% of workspace)",
                         from_=10, to=75, step=5, fmt="{:.0f}%")
        self._add_bool(term_card.body, "log_auto_scroll",
                       "Auto-scroll to newest log entry as messages arrive")
        self._add_slider(term_card.body, "log_max_lines",
                         "Maximum lines kept in memory", from_=100, to=10000, step=100)
        self._add_slider(term_card.body, "log_font_size",
                         "Terminal font size (pt)", from_=8, to=24, step=1)
        if "log_font_size" in self._vars:
            self._vars["log_font_size"].trace_add(
                "write", lambda *_: self._try_refresh_log_font())

        # nuclear option
        # wipes everything
        reset_card = SectionCard(self, "⚠  Reset Everything")
        reset_card.pack(**pad)
        ctk.CTkLabel(reset_card.body,
                     text="This resets ALL settings to their factory defaults, closes any\n"
                          "detached log windows, and rebuilds the entire UI.",
                     font=ctk.CTkFont(size=12), text_color="#f87171",
                     justify="left").pack(anchor="w", pady=(0, 12))
        ctk.CTkButton(reset_card.body,
                      text="🔄  Reset Everything to Factory Defaults",
                      font=ctk.CTkFont(size=13, weight="bold"), height=42,
                      fg_color="#7f1d1d", hover_color="#991b1b",
                      command=self._confirm_full_reset).pack(fill="x")

        ctk.CTkFrame(self, fg_color="transparent", height=20).pack()

    # advanced appearance
    # color presets

    #  ffmpeg dependency section

    def _build_ffmpeg_section(self, parent: ctk.CTkFrame, TEXT_DIM) -> None:
        # Build the ffmpeg path selector, test button, and status display.
        ctk.CTkLabel(
            parent,
            text=(
                "Leave the path empty to use whichever 'ffmpeg' is on your system PATH.\n"
                "Set an explicit path if you have a portable or non-PATH installation."
            ),
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        # path entry row
        path_row = ctk.CTkFrame(parent, fg_color="transparent")
        path_row.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(path_row, text="ffmpeg executable:",
                     font=ctk.CTkFont(size=12), width=160, anchor="w").pack(side="left")

        self._ffmpeg_path_var = tk.StringVar(value=self._settings.get("ffmpeg_path", ""))
        path_entry = ctk.CTkEntry(
            path_row,
            textvariable=self._ffmpeg_path_var,
            placeholder_text="e.g. /usr/local/bin/ffmpeg  (empty = use PATH)",
            width=340,
        )
        path_entry.pack(side="left", padx=(8, 6))
        path_entry.bind("<FocusOut>", lambda _e: self._apply_ffmpeg_path())
        path_entry.bind("<Return>",   lambda _e: self._apply_ffmpeg_path())

        ctk.CTkButton(
            path_row, text="Browse…", width=80, height=32,
            fg_color="#374151", hover_color="#4b5563",
            command=self._browse_ffmpeg,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            path_row, text="Clear", width=60, height=32,
            fg_color="#374151", hover_color="#4b5563",
            command=self._clear_ffmpeg_path,
        ).pack(side="left")

        # test / status row
        test_row = ctk.CTkFrame(parent, fg_color="transparent")
        test_row.pack(fill="x", pady=(0, 4))

        self._ffmpeg_status_var = tk.StringVar(value="")
        self._ffmpeg_status_lbl = ctk.CTkLabel(
            test_row,
            textvariable=self._ffmpeg_status_var,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM,
            anchor="w",
        )
        self._ffmpeg_status_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            test_row, text="▶ Test", width=80, height=28,
            fg_color=_current_accent(), hover_color="#0096c7",
            font=ctk.CTkFont(size=11),
            command=self._test_ffmpeg,
        ).pack(side="right")

        # show current status immediately on open
        self._test_ffmpeg(silent=True)

    def _browse_ffmpeg(self) -> None:
        from tkinter import filedialog
        import sys
        filetypes = (
            [("Executable", "*.exe"), ("All files", "*.*")]
            if sys.platform == "win32"
            else [("All files", "*.*")]
        )
        path = filedialog.askopenfilename(
            title="Locate ffmpeg executable",
            filetypes=filetypes,
        )
        if path:
            self._ffmpeg_path_var.set(path)
            self._apply_ffmpeg_path()

    def _clear_ffmpeg_path(self) -> None:
        self._ffmpeg_path_var.set("")
        self._apply_ffmpeg_path()

    def _apply_ffmpeg_path(self) -> None:
        # Persist the path and push it into the running utils module immediately.
        from media_manager.utils import set_ffmpeg_path
        path = self._ffmpeg_path_var.get().strip()
        self._settings["ffmpeg_path"] = path
        self._settings.save()
        set_ffmpeg_path(path)
        logger.info("ffmpeg path updated: %r", path or "<system PATH>")

    def _test_ffmpeg(self, silent: bool = False) -> None:
        # Run a quick version check and update the status label.
        from media_manager.utils import verify_ffmpeg
        path = self._ffmpeg_path_var.get().strip()
        ok, msg = verify_ffmpeg(path)
        display = f"✔  ffmpeg {msg}" if ok else f"✘  {msg}"
        color   = _current_accent() if ok else "#f87171"
        self._ffmpeg_status_var.set(display)
        try:
            self._ffmpeg_status_lbl.configure(text_color=color)
        except Exception:
            pass
        if not silent:
            logger.info("ffmpeg test: %s", display)

    _CUSTOM_BLANK: dict[str, str] = {
        "dark_surface":   "#1a1a1a", "dark_sidebar":   "#222222",
        "dark_card":      "#2a2a2a", "dark_border":    "#3a3a3a",
        "dark_text":      "#eeeeee", "dark_text_dim":  "#888888",
        "dark_log_bg":    "#111111", "dark_log_panel": "#111111",
        "dark_log_bar":   "#111111",
        "light_surface":  "#f0f0f0", "light_sidebar":  "#e8e8e8",
        "light_card":     "#ffffff", "light_border":   "#cccccc",
        "light_text":     "#1a1a1a", "light_text_dim": "#777777",
        "light_log_bg":   "#f9f9f9", "light_log_panel":"#e8e8e8",
        "light_log_bar":  "#e8e8e8",
    }

    # these three entries show a color editor panel instead of applying immediately
    _EDITOR_ENTRIES = ("Default", "Dark Theme", "Light Theme")

    def _build_advanced_appearance(self, pad: dict, TEXT_DIM) -> None:
        # Build the color preset selector.

        # "Default", "Dark Theme", and "Light Theme" are always the last entries
        # in the dropdown, picking them shows a color editor.
        # Named presets just apply their colors and keep the editors hidden.

        # The dropdown selection is persisted via _preset_display_name so it survives a full UI rebuild.

        adv_card = SectionCard(self, "Advanced Appearance: color Presets")
        adv_card.pack(**pad)

        ctk.CTkLabel(
            adv_card.body,
            text="Switch between named presets, or pick Default / Dark Theme / Light Theme\n"
                 "from the dropdown to edit individual color slots directly.",
            font=ctk.CTkFont(size=11), text_color=TEXT_DIM, justify="left",
        ).pack(anchor="w", pady=(0, 12))

        sel_bar = ctk.CTkFrame(adv_card.body, fg_color="transparent")
        sel_bar.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(sel_bar, text="Active Preset:",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 10))

        dropdown_values = self._preset_dropdown_values()
        saved_display = self._settings.get(
            "_preset_display_name", self._get_active_preset_name()
        )
        if saved_display not in dropdown_values:
            saved_display = "Default"

        self._preset_select_var = tk.StringVar(value=saved_display)
        self._preset_dropdown = ctk.CTkOptionMenu(
            sel_bar,
            variable=self._preset_select_var,
            values=dropdown_values,
            width=220,
            command=self._on_preset_select,
        )
        self._preset_dropdown.pack(side="left", padx=(0, 12))

        self._adv_delete_btn = ctk.CTkButton(
            sel_bar, text="Delete",
            width=80, height=30,
            fg_color="#7f1d1d", hover_color="#991b1b",
            font=ctk.CTkFont(size=11),
            command=self._delete_preset,
        )
        _is_custom = saved_display not in self._EDITOR_ENTRIES
        if _is_custom:
            self._adv_delete_btn.pack(side="left")

        # three editor panels
        # shown/hidden depending on what's selected
        self._custom_work: dict[str, tk.StringVar] = {}

        self._color_panel_blank = ctk.CTkFrame(adv_card.body, fg_color="transparent")
        ctk.CTkLabel(
            self._color_panel_blank,
            text="Freely pick any colors. These won't affect the live UI until\n"
                 "you save them as a named preset.",
            font=ctk.CTkFont(size=11), text_color=TEXT_DIM, justify="left",
        ).pack(anchor="w", pady=(8, 6))
        for key, label in _DARK_color_SLOTS:
            self._color_row_blank(self._color_panel_blank, key, label)

        self._color_panel_dark  = ctk.CTkFrame(adv_card.body, fg_color="transparent")
        self._color_panel_light = ctk.CTkFrame(adv_card.body, fg_color="transparent")
        for key, label in _DARK_color_SLOTS:
            self._color_row(self._color_panel_dark, key, label)
        for key, label in _LIGHT_color_SLOTS:
            self._color_row(self._color_panel_light, key, label)

        # restore whichever panel was visible before the last rebuild
        if saved_display == "Default":
            self._color_panel_blank.pack(fill="x", pady=(10, 0))
        elif saved_display == "Dark Theme":
            self._color_panel_dark.pack(fill="x", pady=(10, 0))
        elif saved_display == "Light Theme":
            self._color_panel_light.pack(fill="x", pady=(10, 0))
        else:
            # named preset
            # show dark panel so user can see what's applied
            self._color_panel_dark.pack(fill="x", pady=(10, 0))

        self._adv_btn_bar = ctk.CTkFrame(adv_card.body, fg_color="transparent")
        self._adv_btn_bar.pack(fill="x", pady=(16, 0))
        self._rebuild_adv_btn_bar(saved_display)

    def _theme_dropdown_values(self) -> list[str]:
        base = ["dark", "light", "system"]
        preset_names = [p["name"] for p in self._get_presets()]
        return base + preset_names

    def _preset_dropdown_values(self) -> list[str]:
        # Build the ordered preset list:
        # Default
        # [saved]
        # Dark Theme
        # Light Theme.
        presets = self._get_presets()
        return (
            ["Default"]
            + [p["name"] for p in presets]
            + ["Dark Theme", "Light Theme"]
        )

    def _refresh_theme_dropdown(self) -> None:
        try:
            self._theme_dropdown.configure(values=self._theme_dropdown_values())
        except Exception:
            pass

    def _refresh_preset_dropdown(self) -> None:
        values = self._preset_dropdown_values()
        active_name = self._get_active_preset_name()
        if active_name not in values:
            active_name = "Default"
        try:
            self._preset_dropdown.configure(values=values)
            self._preset_select_var.set(active_name)
        except Exception:
            pass

    def _rebuild_adv_btn_bar(self, active_name: str) -> None:
        for child in self._adv_btn_bar.winfo_children():
            child.destroy()

        is_custom = active_name not in self._EDITOR_ENTRIES

        ctk.CTkButton(
            self._adv_btn_bar, text="Reset to Preset",
            width=150, height=32,
            fg_color="#374151", hover_color="#4b5563",
            font=ctk.CTkFont(size=12),
            command=self._reset_colors_to_preset,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            self._adv_btn_bar, text="Save as New Preset…",
            width=170, height=32,
            fg_color=ACCENT, hover_color="#0096c7",
            font=ctk.CTkFont(size=12),
            command=self._save_new_preset,
        ).pack(side="left", padx=(0, 8))

        if is_custom:
            ctk.CTkButton(
                self._adv_btn_bar,
                text=f'Save Over\t"{active_name}"',
                width=200, height=32,
                fg_color="#1d4ed8", hover_color="#1e40af",
                font=ctk.CTkFont(size=12),
                command=self._save_over_preset,
            ).pack(side="left")

    # color row helpers

    def _color_row(self, parent, key: str, label: str):
        # One editable row: swatch + hex entry + color picker button.
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)

        current = str(self._settings[key])
        swatch = ctk.CTkFrame(row, width=26, height=26, corner_radius=6, fg_color=current)
        swatch.pack(side="left", padx=(0, 6))
        swatch.pack_propagate(False)
        self._color_swatches[key] = swatch

        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                     width=170, anchor="w").pack(side="left")

        var = tk.StringVar(value=current)
        entry = ctk.CTkEntry(row, textvariable=var, width=80, font=ctk.CTkFont(size=11))
        entry.pack(side="left", padx=(0, 4))
        entry.bind("<Return>",   lambda e, k=key, v=var: self._set_color(k, v.get()))
        entry.bind("<FocusOut>", lambda e, k=key, v=var: self._set_color(k, v.get()))

        ctk.CTkButton(row, text="…", width=28, height=26,
                      fg_color="#374151", hover_color="#4b5563",
                      command=lambda k=key, v=var, s=swatch: self._pick_color(k, v, s)
                      ).pack(side="left")

    def _color_row_blank(self, parent, key: str, label: str):
        # Blank-canvas row
        # Writes to self._custom_work, not live settings.
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)

        blank_val = self._CUSTOM_BLANK.get(key, "#808080")
        swatch = ctk.CTkFrame(row, width=26, height=26, corner_radius=6, fg_color=blank_val)
        swatch.pack(side="left", padx=(0, 6))
        swatch.pack_propagate(False)

        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                     width=170, anchor="w").pack(side="left")

        var = tk.StringVar(value=blank_val)
        self._custom_work[key] = var

        entry = ctk.CTkEntry(row, textvariable=var, width=80, font=ctk.CTkFont(size=11))
        entry.pack(side="left", padx=(0, 4))

        def _apply(k=key, v=var, s=swatch):
            hex_c = v.get().strip()
            if not hex_c.startswith("#"):
                hex_c = "#" + hex_c
            stripped = hex_c.lstrip("#")
            if len(stripped) not in (3, 6) or not all(
                    c in "0123456789abcdefABCDEF" for c in stripped):
                return
            v.set(hex_c)
            try:
                s.configure(fg_color=hex_c)
            except Exception:
                pass

        entry.bind("<Return>",   lambda e: _apply())
        entry.bind("<FocusOut>", lambda e: _apply())

        ctk.CTkButton(row, text="…", width=28, height=26,
                      fg_color="#374151", hover_color="#4b5563",
                      command=lambda k=key, v=var, s=swatch: self._pick_color_blank(k, v, s),
                      ).pack(side="left")

    def _pick_color_blank(self, key: str, var: tk.StringVar, swatch: ctk.CTkFrame):
        result = colorchooser.askcolor(color=var.get(), title="Choose color")
        if result and result[1]:
            var.set(result[1])
            try:
                swatch.configure(fg_color=result[1])
            except Exception:
                pass

    def _pick_color(self, key: str, var: tk.StringVar, swatch: ctk.CTkFrame):
        result = colorchooser.askcolor(color=var.get(), title="Choose color")
        if result and result[1]:
            var.set(result[1])
            self._set_color(key, result[1], swatch)

    def _set_color(self, key: str, hex_color: str, swatch: ctk.CTkFrame | None = None):
        # Validate, save, and apply a color change with immediate visual feedback
        hex_color = hex_color.strip()
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        stripped = hex_color.lstrip("#")
        if len(stripped) not in (3, 6) or not all(
                c in "0123456789abcdefABCDEF" for c in stripped):
            logger.warning("Invalid hex color: %s", hex_color)
            return

        self._settings[key] = hex_color
        self._settings.save()

        if swatch is None:
            swatch = self._color_swatches.get(key)
        if swatch:
            try:
                swatch.configure(fg_color=hex_color)
            except Exception:
                pass

        logger.info("color %s changed to %s", key, hex_color)

        # apply immediately so the workspace updates before the full rebuild lands
        if self._on_apply_colors:
            try:
                self._on_apply_colors()
            except Exception as e:
                logger.debug("Failed to apply colors immediately: %s", e)

        if self._on_rebuild:
            self.after(150, self._on_rebuild)

    # preset name dialog

    def _ask_preset_name(self) -> str | None:
        # Show a styled dialog to collect a preset name. Returns the string or None.
        result: list[str | None] = [None]

        dialog = ctk.CTkToplevel(self)
        dialog.title("Name Your Preset")
        dialog.resizable(False, False)

        root = self.winfo_toplevel()
        root.update_idletasks()
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        dw, dh = 380, 200
        dialog.geometry(f"{dw}x{dh}+{rx + (rw - dw) // 2}+{ry + (rh - dh) // 2}")

        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        dialog.after(50, dialog.lift)
        dialog.after(60, dialog.focus_force)

        hdr = ctk.CTkFrame(dialog, fg_color=ThemeEngine.ctk_card(), corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="💾  Save color Preset",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     ).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(hdr, text="Give this preset a unique, memorable name.",
                     font=ctk.CTkFont(size=11),
                     text_color=ThemeEngine.ctk_text_dim(),
                     ).pack(anchor="w", padx=18, pady=(0, 14))

        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=10)

        name_var = tk.StringVar()
        entry = ctk.CTkEntry(
            body, textvariable=name_var,
            placeholder_text="e.g.  Midnight Blue, Warm Sand…",
            font=ctk.CTkFont(size=13), height=38,
            border_color=ThemeEngine.ctk_border(),
        )
        entry.pack(fill="x")
        dialog.after(70, entry.focus_set)

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(12, 0))

        def _confirm():
            result[0] = name_var.get().strip()
            dialog.destroy()

        def _cancel():
            dialog.destroy()

        entry.bind("<Return>",  lambda _: _confirm())
        entry.bind("<Escape>",  lambda _: _cancel())
        dialog.protocol("WM_DELETE_WINDOW", _cancel)

        ctk.CTkButton(btn_row, text="Save Preset",
                      fg_color=ACCENT, hover_color="#0096c7",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      height=36, command=_confirm,
                      ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color="#374151", hover_color="#4b5563",
                      font=ctk.CTkFont(size=13),
                      height=36, command=_cancel,
                      ).pack(side="left", fill="x", expand=True)

        dialog.wait_window()
        return result[0]

    # preset data helpers

    def _get_presets(self) -> list[dict]:
        # Return the saved custom presets as a plain list.
        raw = self._settings["color_presets"]
        if isinstance(raw, str):
            import json as _json
            try:
                return _json.loads(raw) if raw else []
            except Exception:
                return []
        return list(raw) if raw else []

    def _get_active_preset_name(self) -> str:
        pid = self._settings.get("active_color_preset", "default")
        if not pid or pid == "default":
            return "Default"
        for p in self._get_presets():
            if p.get("id") == pid:
                return p["name"]
        return "Default"

    def _snapshot_current_colors(self) -> dict:
        return {k: str(self._settings[k]) for k in _ALL_color_KEYS}

    def _apply_preset_colors(self, preset_id: str) -> None:
        # Load a preset's colors into live settings (doesn't save or rebuild).
        from ..settings_manager import DEFAULTS
        if preset_id == "default":
            for k in _ALL_color_KEYS:
                self._settings[k] = DEFAULTS[k]
            self._settings["active_color_preset"] = "default"
        else:
            for p in self._get_presets():
                if p.get("id") == preset_id:
                    for k in _ALL_color_KEYS:
                        if k in p:
                            self._settings[k] = p[k]
                    self._settings["active_color_preset"] = preset_id
                    break

    # preset callbacks

    def _on_preset_select(self, name: str) -> None:
        # Handle dropdown selection.

        # Editor entries (Default, Dark Theme, Light Theme) reveal color panels.
        # Named presets apply their colors immediately and trigger a rebuild.

        self._settings["_preset_display_name"] = name
        self._settings.save()

        try:
            self._color_panel_blank.pack_forget()
            self._color_panel_dark.pack_forget()
            self._color_panel_light.pack_forget()
        except Exception:
            pass

        is_custom = name not in self._EDITOR_ENTRIES
        try:
            if is_custom:
                self._adv_delete_btn.pack(side="left")
            else:
                self._adv_delete_btn.pack_forget()
        except Exception:
            pass

        if name == "Default":
            self._color_panel_blank.pack(fill="x", pady=(10, 0), before=self._adv_btn_bar)
        elif name == "Dark Theme":
            self._color_panel_dark.pack(fill="x", pady=(10, 0), before=self._adv_btn_bar)
        elif name == "Light Theme":
            self._color_panel_light.pack(fill="x", pady=(10, 0), before=self._adv_btn_bar)
        else:
            for p in self._get_presets():
                if p["name"] == name:
                    self._apply_preset_colors(p["id"])
                    break
            self._settings.save()
            logger.info("Applied preset colors: %s", name)
            self._color_panel_dark.pack(fill="x", pady=(10, 0), before=self._adv_btn_bar)
            if self._on_apply_colors:
                try:
                    self._on_apply_colors()
                except Exception:
                    pass
            if self._on_rebuild:
                self.after(100, self._on_rebuild)

        try:
            self._rebuild_adv_btn_bar(name)
        except Exception:
            pass

    def _save_new_preset(self) -> None:
        name = self._ask_preset_name()
        if not name or not name.strip():
            return
        name = name.strip()

        existing_names = [p["name"] for p in self._get_presets()]
        if name in existing_names:
            messagebox.showwarning(
                "Name Already Exists",
                f'A preset named "{name}" already exists.\n'
                'Please choose a different name or use "Save Over" to overwrite it.',
                parent=self,
            )
            return

        snapshot = self._snapshot_current_colors()

        # when the blank-canvas editor is open, use those working values and mirror dark_* -> light_*
        # Makes it so the preset is self-consistent
        if self._settings.get("_preset_display_name") == "Default":
            for key, var in self._custom_work.items():
                val = var.get().strip()
                if val:
                    snapshot[key] = val
                    if key.startswith("dark_"):
                        light_key = "light_" + key[5:]
                        if light_key in snapshot:
                            snapshot[light_key] = val

        preset_id = f"custom_{uuid.uuid4().hex[:8]}"
        preset    = {"id": preset_id, "name": name, **snapshot}

        presets = self._get_presets()
        presets.append(preset)
        self._settings["color_presets"]        = presets
        self._settings["active_color_preset"]  = preset_id
        self._settings["_preset_display_name"] = name
        self._settings.save()
        logger.info("Saved new color preset: %s (%s)", name, preset_id)
        self._refresh_preset_dropdown()
        self._refresh_theme_dropdown()
        if self._on_rebuild:
            self.after(50, self._on_rebuild)

    def _save_over_preset(self) -> None:
        pid = self._settings.get("active_color_preset", "default")
        if not pid or pid == "default":
            return
        presets  = self._get_presets()
        snapshot = self._snapshot_current_colors()
        for p in presets:
            if p.get("id") == pid:
                p.update(snapshot)
                break
        self._settings["color_presets"] = presets
        self._settings.save()
        name = self._get_active_preset_name()
        logger.info("Updated color preset: %s (%s)", name, pid)
        if self._on_rebuild:
            self.after(50, self._on_rebuild)

    def _delete_preset(self) -> None:
        pid = self._settings.get("active_color_preset", "default")
        if not pid or pid == "default":
            return
        name = self._get_active_preset_name()
        confirmed = messagebox.askyesno(
            "Delete Preset",
            f'Delete the color preset "{name}"?\n\nThis cannot be undone.',
            icon="warning", default="no", parent=self,
        )
        if not confirmed:
            return
        presets = [p for p in self._get_presets() if p.get("id") != pid]
        self._settings["color_presets"] = presets
        self._apply_preset_colors("default")
        self._settings["_preset_display_name"] = "Default"
        self._settings.save()
        logger.info("Deleted color preset: %s (%s)", name, pid)
        self._refresh_preset_dropdown()
        self._refresh_theme_dropdown()
        if self._on_apply_colors:
            try:
                self._on_apply_colors()
            except Exception:
                pass
        if self._on_rebuild:
            self.after(100, self._on_rebuild)

    def _reset_colors_to_preset(self) -> None:
        pid = self._settings.get("active_color_preset", "default")
        self._apply_preset_colors(pid if pid else "default")
        self._settings.save()
        logger.info("colors reset to active preset.")
        if self._on_apply_colors:
            try:
                self._on_apply_colors()
            except Exception:
                pass
        if self._on_rebuild:
            self.after(100, self._on_rebuild)

    # widget factories

    def _add_bool(self, parent, key, label):
        var = tk.BooleanVar(value=bool(self._settings[key]))
        self._vars[key] = var
        ctk.CTkSwitch(parent, text=label, variable=var,
                      progress_color=_current_accent(),
                      command=lambda: self._live_update(key, var.get())
                      ).pack(anchor="w", pady=4)

    def _add_slider(self, parent, key, label, from_, to, step=1.0, fmt="{:.0f}"):
        var = tk.DoubleVar(value=float(self._settings[key]))
        self._vars[key] = var
        LabeledSlider(parent, label, from_=from_, to=to,
                      initial=float(self._settings[key]),
                      step=step, fmt=fmt,
                      on_change=lambda v: self._live_update(key, v)
                      ).pack(fill="x", pady=6)

    def _add_option(self, parent, key, label, values, on_change=None):
        var = tk.StringVar(value=str(self._settings[key]))
        self._vars[key] = var
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12),
                     width=220, anchor="w").pack(side="left")
        def _cmd(v):
            self._live_update(key, v)
            if on_change:
                on_change(v)
        ctk.CTkOptionMenu(row, variable=var, values=values,
                          command=_cmd, width=180).pack(side="left", padx=(8, 0))

    def _add_entry(self, parent, key, label):
        var = tk.StringVar(value=str(self._settings[key]))
        self._vars[key] = var
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12),
                     width=160, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        entry.bind("<FocusOut>", lambda e: self._live_update(key, var.get()))
        entry.bind("<Return>",   lambda e: self._live_update(key, var.get()))

    # live update

    def _live_update(self, key, value):
        self._settings[key] = value
        self._settings.save()
        logger.debug("Saved setting: %s = %r", key, value)

    def _try_refresh_log_font(self):
        try:
            root = self.winfo_toplevel()
            if hasattr(root, "_log_panel"):
                root._log_panel.refresh_font_size()
        except Exception:
            pass

    # theme / accent

    def _on_theme_change(self, value: str):
        # Save the new theme/preset and trigger a full rebuild.
        built_in = {"dark", "light", "system"}
        if value in built_in:
            self._settings["appearance_mode"] = value
            self._settings.save()
            logger.info("Theme changed to: %s", value)
        else:
            # must be a named preset
            # apply colors but keep appearance mode
            for p in self._get_presets():
                if p["name"] == value:
                    self._apply_preset_colors(p["id"])
                    self._settings.save()
                    logger.info("Theme preset applied: %s", value)
                    try:
                        self._preset_select_var.set(value)
                    except Exception:
                        pass
                    break
        if self._on_apply_colors:
            try:
                self._on_apply_colors()
            except Exception:
                pass
        if self._on_rebuild:
            self.after(100, self._on_rebuild)

    def _pick_accent(self):
        result = colorchooser.askcolor(color=self._accent_var.get(), title="Choose Accent Color")
        if result and result[1]:
            self._set_accent(result[1])

    def _set_accent(self, hex_color: str):
        hex_color = hex_color.strip()
        if not hex_color:
            return
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        stripped = hex_color.lstrip("#")
        if len(stripped) not in (3, 6) or not all(
                c in "0123456789abcdefABCDEF" for c in stripped):
            logger.warning("Invalid hex color: %s", hex_color)
            return
        self._accent_var.set(hex_color)
        try:
            self._preview_swatch.configure(fg_color=hex_color)
        except Exception:
            pass
        self._update_swatch_borders(hex_color)
        self._settings["accent_color"] = hex_color
        self._settings.save()
        import media_manager.gui.widgets as _w
        _w.ACCENT = hex_color
        logger.info("Accent color changed to %s: rebuilding UI.", hex_color)
        if self._on_rebuild:
            self.after(50, self._on_rebuild)

    def _update_swatch_borders(self, selected: str):
        for btn, (hex_color, _) in zip(self._swatch_buttons, _ACCENT_PRESETS):
            border = "#ffffff" if hex_color.lower() == selected.lower() \
                     else ThemeEngine.ctk_border()
            try:
                btn.configure(border_color=border)
            except Exception:
                pass

    # soft reset

    def _reset(self):
        self._settings.reset()
        import media_manager.gui.widgets as _w
        _w.ACCENT = self._settings["accent_color"]
        logger.info("Settings reset to defaults.")
        if self._on_apply_colors:
            try:
                self._on_apply_colors()
            except Exception:
                pass
        if self._on_rebuild:
            self.after(100, self._on_rebuild)

    def _confirm_full_reset(self):
        confirmed = messagebox.askyesno(
            title="Reset Everything?",
            message=(
                "This will reset ALL settings to factory defaults and fully\n"
                "rebuild the application UI.\n\n"
                "Any customisations (accent color, dock position, thresholds,\n"
                "encoding presets, custom color presets, etc.) will be lost.\n\n"
                "Continue?"
            ),
            icon="warning", default="no",
        )
        if confirmed and self._on_reset_all:
            logger.info("User confirmed full factory reset.")
            self.after(80, self._on_reset_all)
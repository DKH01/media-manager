# Persistent settings
# Reads/writes ~/.media_manager/settings.json.

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SETTINGS_DIR  = Path.home() / ".media_manager"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

# Everything in here is a safe default that works out of the box.
DEFAULTS: dict[str, Any] = {
    # General
    "auto_nested": False,
    "max_filename_length": 220,
    "default_max_workers": 5,
    "appearance_mode": "dark",
    "accent_color": "#00b4d8",
    # ffmpeg
    "ffmpeg_path": "", # empty = use system PATH
    # Hashing
    "phash_base_threshold": 4,
    "phash_gray_zone": 2,
    "phash_frame_samples": 16,
    # Quality scoring weights
    "score_weight_resolution": 0.5,
    "score_weight_bitrate": 0.3,
    "score_weight_duration": 0.2,
    # GIF conversion
    "gif_retry_count": 3,
    # Duplicate handling
    "duplicate_action": "move",
    "create_placeholders": False,
    "use_threading": True,
    "use_best_video": True,
    # Video conversion
    "video_encode_preset": "slow",
    "video_crf_offset": 0,
    "audio_bitrate": "128k",
    # Logging
    "log_level": "INFO",
    "log_to_file": False,
    "log_file_path": str(Path.home() / ".media_manager" / "activity.log"),
    # Terminal panel: user preferences
    "log_remember_dock": True,
    "log_default_dock": "bottom",
    "log_default_size_pct": 25,
    "log_show_on_start": True,
    "log_auto_scroll": True,
    "log_max_lines": 2000,
    "log_font_size": 12,
    # Terminal panel: saved layout state (position, size, collapsed)
    "log_dock": "bottom",
    "log_h": 210,
    "log_w": 320,
    "log_minimized": False,
    # Dark theme colors
    "dark_surface":   "#161b22",
    "dark_sidebar":   "#1c2128",
    "dark_card":      "#1c2128",
    "dark_border":    "#30363d",
    "dark_text":      "#e2e8f0",
    "dark_text_dim":  "#6b7280",
    "dark_log_bg":    "#0d1117",
    "dark_log_panel": "#0d1117",
    "dark_log_bar":   "#0d1117",
    # Light theme colors
    "light_surface":   "#ebebeb",
    "light_sidebar":   "#f3f4f6",
    "light_card":      "#ffffff",
    "light_border":    "#d1d5db",
    "light_text":      "#1f2937",
    "light_text_dim":  "#6b7280",
    "light_log_bg":    "#f8f9fa",
    "light_log_panel": "#e2e5ea",
    "light_log_bar":   "#e2e5ea",
    # Saved color presets: list of dicts with id, name, and all color keys
    "color_presets": [],
    # Which preset is active; "default" means the built-in values above
    "active_color_preset": "default",
}


class SettingsManager:
    def __init__(self):
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._load()

    def __getitem__(self, key):        return self._data.get(key, DEFAULTS.get(key))
    def __setitem__(self, key, value): self._data[key] = value
    def get(self, key, fallback=None): return self._data.get(key, DEFAULTS.get(key, fallback))
    def update(self, mapping):         self._data.update(mapping)
    def all(self):                     return dict(self._data)

    def save(self):
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError as e:
            logger.error("Could not save settings: %s", e)

    def reset(self):
        # Wipes everything back to defaults and save.
        self._data = dict(DEFAULTS)
        self.save()

    def _load(self):
        if not _SETTINGS_FILE.exists():
            return
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            self._data.update(stored)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load settings: %s", e)
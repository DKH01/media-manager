# File Operations page, batch rename/convert/fix with live progress feedback.
# All heavy lifting runs in a background thread to keep the GUI responsive.

from __future__ import annotations

import logging
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import customtkinter as ctk

from ...file_operations import (
    rename_image,
    rename_video,
    convert_gif_to_mp4,
    check_and_fix_mp4_compatibility,
)
from ...utils import collect_files
from ..widgets import (
    ACCENT, ThemeEngine,
    PathSelector, SectionCard, ProgressCard, LabeledSlider,
)

if TYPE_CHECKING:
    from ..settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class FileOpsPage(ctk.CTkScrollableFrame):
    """Batch file operation controls with live progress feedback."""

    def __init__(self, parent: tk.Widget, settings: "SettingsManager") -> None:
        super().__init__(parent, fg_color="transparent")
        self._settings = settings
        self._running  = False
        self._build()

    def _build(self) -> None:
        import media_manager.gui.widgets as _w
        _TE      = _w.ThemeEngine
        TEXT_DIM = _TE.ctk_text_dim()

        ctk.CTkLabel(self, text="File Operations",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(self, text="Rename, convert, and fix media files in bulk.",
                     font=ctk.CTkFont(size=13), text_color=TEXT_DIM).pack(
            anchor="w", padx=20, pady=(0, 16))

        pad = dict(fill="x", padx=20, pady=6)

        # input folder + recursive/time-filter options
        input_card = SectionCard(self, "Input")
        input_card.pack(**pad)
        self._folder_sel = PathSelector(input_card.body, "Source Folder", mode="folder")
        self._folder_sel.pack(fill="x", pady=(0, 10))

        self._nested_var = tk.BooleanVar(value=self._settings["auto_nested"])
        ctk.CTkSwitch(input_card.body, text="Include sub-folders recursively",
                      variable=self._nested_var, progress_color=ACCENT,
                      command=self._on_nested_toggle).pack(anchor="w")

        self._time_filter_frame = ctk.CTkFrame(input_card.body, fg_color="transparent")
        self._time_filter_frame.pack(fill="x")
        self._time_filter_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._time_filter_frame,
                        text="Filter sub-folders by modification time",
                        variable=self._time_filter_var, checkmark_color=ACCENT,
                        command=self._on_time_filter_toggle).pack(anchor="w", pady=(6, 0))
        self._time_hours_frame = ctk.CTkFrame(self._time_filter_frame, fg_color="transparent")
        self._time_slider = LabeledSlider(self._time_hours_frame, "Time window (hours)",
                                          from_=1, to=168, initial=24, step=1)
        self._time_slider.pack(fill="x")
        self._time_hours_frame.pack_forget()  # hidden until the checkbox above is ticked

        # which operations to run
        ops_card = SectionCard(self, "Operations")
        ops_card.pack(**pad)

        self._op_rename_images = tk.BooleanVar(value=False)
        self._op_rename_videos = tk.BooleanVar(value=False)
        self._op_convert_gifs  = tk.BooleanVar(value=False)
        self._op_fix_mp4       = tk.BooleanVar(value=False)

        checks = [
            (self._op_rename_images, "Rename images to PNG", "JPG / BMP / TIFF → PNG"),
            (self._op_rename_videos, "Rename / convert videos to MP4", "AVI / MOV / MKV / WMV -> MP4"),
            (self._op_convert_gifs,  "Convert GIFs to MP4", "Web-compatible H.264 output"),
            (self._op_fix_mp4,       "Fix MP4 compatibility", "Enforce even pixel dimensions"),
        ]
        for var, label, hint in checks:
            row = ctk.CTkFrame(ops_card.body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkCheckBox(row, text=label, variable=var,
                            checkmark_color=ACCENT).pack(side="left")
            ctk.CTkLabel(row, text=hint, font=ctk.CTkFont(size=11),
                         text_color=TEXT_DIM).pack(side="left", padx=(12, 0))

        # video-specific options
        vid_card = SectionCard(self, "Video Options")
        vid_card.pack(**pad)

        action_row = ctk.CTkFrame(vid_card.body, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(action_row, text="Video operation:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 12))
        self._video_action_var = tk.StringVar(value="rename")
        ctk.CTkRadioButton(action_row, text="Rename only (fast)",
                           variable=self._video_action_var, value="rename",
                           fg_color=ACCENT).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(action_row, text="Full re-encode (ffmpeg)",
                           variable=self._video_action_var, value="convert",
                           fg_color=ACCENT).pack(side="left")

        self._delete_orig_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(vid_card.body, text="Delete originals after conversion",
                        variable=self._delete_orig_var, checkmark_color=ACCENT).pack(anchor="w", pady=4)

        self._use_folders_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(vid_card.body,
                        text="Sort MP4-fix outputs into 'original' / 'converted' sub-folders",
                        variable=self._use_folders_var, checkmark_color=ACCENT).pack(anchor="w")

        # performance
        perf_card = SectionCard(self, "Performance")
        perf_card.pack(**pad)
        self._workers_slider = LabeledSlider(
            perf_card.body, "Thread workers",
            from_=1, to=16,
            initial=self._settings["default_max_workers"],
            step=1,
        )
        self._workers_slider.pack(fill="x")

        # progress
        self._progress = ProgressCard(self)
        self._progress.pack(**pad)

        self._run_btn = ctk.CTkButton(
            self, text="▶  Run Operations",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, fg_color=ACCENT, hover_color="#0096c7",
            command=self._start,
        )
        self._run_btn.pack(fill="x", padx=20, pady=(4, 24))

    def _on_nested_toggle(self) -> None:
        pass  # time-filter visibility is independent of the nested toggle

    def _on_time_filter_toggle(self) -> None:
        if self._time_filter_var.get():
            self._time_hours_frame.pack(fill="x", padx=(24, 0))
        else:
            self._time_hours_frame.pack_forget()

    def _start(self) -> None:
        if self._running:
            return

        folder = self._folder_sel.path
        if not folder:
            logger.warning("No source folder selected.")
            return

        ops = {
            "rename_images": self._op_rename_images.get(),
            "rename_videos": self._op_rename_videos.get(),
            "convert_gifs":  self._op_convert_gifs.get(),
            "fix_mp4":       self._op_fix_mp4.get(),
        }
        if not any(ops.values()):
            logger.warning("No operations selected.")
            return

        params = dict(
            folder=folder,
            ops=ops,
            iterate_nested=self._nested_var.get(),
            filter_by_time=self._time_filter_var.get(),
            time_frame_hours=float(self._time_slider.value),
            video_action=self._video_action_var.get(),
            delete_original=self._delete_orig_var.get(),
            use_folders=self._use_folders_var.get(),
            max_workers=int(self._workers_slider.value),
        )

        self._running = True
        self._run_btn.configure(state="disabled", text="Running…")
        self._progress.start("Processing files…")
        threading.Thread(target=self._run, kwargs=params, daemon=True).start()

    def _run(self, *, folder, ops, iterate_nested, filter_by_time, time_frame_hours,
             video_action, delete_original, use_folders, max_workers) -> None:
        failed: list[tuple[str, str]] = []
        try:
            files = collect_files(folder, iterate_nested, filter_by_time, time_frame_hours)
            logger.info("Found %d files to process.", len(files))

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = []
                if ops["rename_images"]:
                    futures += [ex.submit(rename_image, p, failed) for p in files]
                if ops["rename_videos"]:
                    futures += [ex.submit(rename_video, p, failed, video_action) for p in files]
                if ops["convert_gifs"]:
                    futures += [
                        ex.submit(convert_gif_to_mp4, p, failed, delete_original)
                        for p in files if p.lower().endswith(".gif")
                    ]
                if ops["fix_mp4"]:
                    futures += [
                        ex.submit(check_and_fix_mp4_compatibility,
                                  p, failed, delete_original, use_folders)
                        for p in files if p.lower().endswith(".mp4")
                    ]
                for f in futures:
                    f.result()

            logger.info("Batch complete. %d failure(s).", len(failed))
            for name, err in failed:
                logger.error("\tFAIL\t%s, %s", name, err)

            self.after(0, self._on_done, f"Done: {len(failed)} failure(s)")
        except Exception as exc:
            logger.error("Unexpected error: %s", exc)
            self.after(0, self._on_done, f"Error: {exc}")

    def _on_done(self, message: str) -> None:
        self._progress.stop(message)
        self._run_btn.configure(state="normal", text="▶  Run Operations")
        self._running = False

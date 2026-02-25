# Video Converter page
# Export one video to multiple resolution presets.

from __future__ import annotations

import logging
import os
import subprocess
import threading
import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk
from moviepy import VideoFileClip

from ...config import RESOLUTION_PRESETS
from ...utils import get_ffmpeg
from ..widgets import (
    ACCENT, CARD, BORDER, TEXT_DIM,
    PathSelector, SectionCard, ProgressCard,
)

if TYPE_CHECKING:
    from ..settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class VideoConverterPage(ctk.CTkScrollableFrame):
    # Pick a video, choose resolutions, and convert
    # Aspect ratio is always preserved.

    def __init__(self, parent: tk.Widget, settings: "SettingsManager") -> None:
        super().__init__(parent, fg_color="transparent")
        self._settings     = settings
        self._running      = False
        self._preset_vars: dict[str, tk.BooleanVar] = {}
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Video Converter",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(self,
                     text="Export a video to one or more resolution presets while preserving aspect ratio.",
                     font=ctk.CTkFont(size=13), text_color=TEXT_DIM).pack(
            anchor="w", padx=20, pady=(0, 16))

        pad = dict(fill="x", padx=20, pady=6)

        # input / output paths
        io_card = SectionCard(self, "Input & Output")
        io_card.pack(**pad)
        self._input_sel = PathSelector(
            io_card.body, "Source Video File", mode="file",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"),
                       ("All files", "*.*")],
            on_change=self._on_input_change,
        )
        self._input_sel.pack(fill="x", pady=(0, 10))
        self._output_sel = PathSelector(
            io_card.body,
            "Output Folder (optional, defaults to input folder)",
            mode="folder",
        )
        self._output_sel.pack(fill="x")

        # brief metadata readout shown after the user picks a file
        self._info_var = tk.StringVar(value="")
        ctk.CTkLabel(io_card.body, textvariable=self._info_var,
                     font=ctk.CTkFont(family="Courier New", size=11),
                     text_color=TEXT_DIM, justify="left").pack(anchor="w", pady=(8, 0))

        # resolution checkboxes
        preset_card = SectionCard(self, "Target Resolutions")
        preset_card.pack(**pad)

        sel_row = ctk.CTkFrame(preset_card.body, fg_color="transparent")
        sel_row.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(sel_row, text="Select All", width=100, height=28,
                      command=self._select_all).pack(side="left", padx=(0, 8))
        ctk.CTkButton(sel_row, text="Clear All", width=100, height=28,
                      fg_color="#374151", hover_color="#4b5563",
                      command=self._clear_all).pack(side="left", padx=(0, 8))

        # common preset quick-select buttons
        common_row = ctk.CTkFrame(preset_card.body, fg_color="transparent")
        common_row.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(common_row, text="Quick select:",
                     font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(side="left")
        for label, keys in [
            ("Web (720p+1080p)",  {"720p", "1080p"}),
            ("Social (480p+720p)", {"480p", "720p"}),
            ("All HD",            {"720p", "1080p", "2k", "4k"}),
        ]:
            ctk.CTkButton(common_row, text=label, width=140, height=26,
                          fg_color="transparent", border_color=BORDER, border_width=1,
                          font=ctk.CTkFont(size=11),
                          command=lambda ks=keys: self._quick_select(ks)).pack(
                side="left", padx=(8, 0))

        # two-column checkbox grid
        grid = ctk.CTkFrame(preset_card.body, fg_color="transparent")
        grid.pack(fill="x")
        for col in range(2):
            grid.columnconfigure(col, weight=1, uniform="preset_col")

        for i, (key, label, w, h, crf, br) in enumerate(RESOLUTION_PRESETS):
            var = tk.BooleanVar(value=(key in {"1080p", "720p"}))  # sensible default selection
            self._preset_vars[key] = var
            col, row = i % 2, i // 2
            frame = ctk.CTkFrame(grid, fg_color="transparent")
            frame.grid(row=row, column=col, sticky="w", pady=3, padx=4)
            ctk.CTkCheckBox(frame, text=label, variable=var,
                            checkmark_color=ACCENT).pack(side="left")
            note = f"CRF {crf}" if not br else f"{br} kbps"
            ctk.CTkLabel(frame, text=f"  ({note})",
                         font=ctk.CTkFont(size=10), text_color=TEXT_DIM).pack(side="left")

        # encoding options
        enc_card = SectionCard(self, "Encoding Options")
        enc_card.pack(**pad)

        preset_row = ctk.CTkFrame(enc_card.body, fg_color="transparent")
        preset_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(preset_row, text="ffmpeg preset:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 12))
        self._encode_preset_var = tk.StringVar(value=self._settings["video_encode_preset"])
        ctk.CTkOptionMenu(preset_row,
                          variable=self._encode_preset_var,
                          values=["ultrafast", "superfast", "veryfast", "faster",
                                  "fast", "medium", "slow", "slower", "veryslow"],
                          width=130).pack(side="left")
        ctk.CTkLabel(preset_row, text="← slower = smaller file",
                     font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(
            side="left", padx=(12, 0))

        audio_row = ctk.CTkFrame(enc_card.body, fg_color="transparent")
        audio_row.pack(fill="x")
        ctk.CTkLabel(audio_row, text="Audio bitrate:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 12))
        self._audio_var = tk.StringVar(value=self._settings["audio_bitrate"])
        ctk.CTkOptionMenu(audio_row,
                          variable=self._audio_var,
                          values=["64k", "96k", "128k", "192k", "256k", "320k"],
                          width=100).pack(side="left")

        self._delete_orig_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(enc_card.body,
                        text="Delete source file after all conversions succeed",
                        variable=self._delete_orig_var, checkmark_color=ACCENT).pack(
            anchor="w", pady=(10, 0))

        # progress
        self._progress = ProgressCard(self)
        self._progress.pack(**pad)

        self._run_btn = ctk.CTkButton(
            self, text="▶  Convert Video",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, fg_color=ACCENT, hover_color="#0096c7",
            command=self._start,
        )
        self._run_btn.pack(fill="x", padx=20, pady=(4, 24))

        # output file list
        out_card = SectionCard(self, "Output Files")
        out_card.pack(**pad)
        self._out_text = ctk.CTkTextbox(out_card.body, height=120,
                                         font=ctk.CTkFont(family="Courier New", size=11),
                                         state="disabled")
        self._out_text.pack(fill="x")

    def _on_input_change(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            self._info_var.set("")
            return
        try:
            clip  = VideoFileClip(path)
            w, h  = clip.size
            fps   = clip.fps
            dur   = clip.duration
            size  = os.path.getsize(path) / 1024 / 1024
            clip.close()
            self._info_var.set(
                f"\t{w}×{h}\t·\t{fps:.2f} fps\t·\t{dur:.1f}s\t·\t{size:.1f} MB"
            )
        except Exception:
            self._info_var.set("\t(could not read video metadata)")

    def _select_all(self) -> None:
        for var in self._preset_vars.values():
            var.set(True)

    def _clear_all(self) -> None:
        for var in self._preset_vars.values():
            var.set(False)

    def _quick_select(self, keys: set[str]) -> None:
        self._clear_all()
        for k in keys:
            if k in self._preset_vars:
                self._preset_vars[k].set(True)

    def _start(self) -> None:
        if self._running:
            return
        input_path = self._input_sel.path
        if not input_path or not os.path.isfile(input_path):
            logger.warning("No valid source video selected.")
            return
        selected = [p for p in RESOLUTION_PRESETS if self._preset_vars[p[0]].get()]
        if not selected:
            logger.warning("No resolutions selected.")
            return

        output_folder = self._output_sel.path or os.path.dirname(input_path)
        os.makedirs(output_folder, exist_ok=True)

        self._running = True
        self._run_btn.configure(state="disabled", text="Converting…")
        self._progress.start(f"Converting to {len(selected)} resolution(s)…")
        self._out_text.configure(state="normal")
        self._out_text.delete("1.0", "end")
        self._out_text.configure(state="disabled")

        params = dict(
            input_path=input_path,
            output_folder=output_folder,
            selected_presets=selected,
            encode_preset=self._encode_preset_var.get(),
            audio_bitrate=self._audio_var.get(),
            delete_original=self._delete_orig_var.get(),
        )
        threading.Thread(target=self._run, kwargs=params, daemon=True).start()

    def _run(self, *, input_path, output_folder, selected_presets,
             encode_preset, audio_bitrate, delete_original) -> None:
        from moviepy import VideoFileClip

        converted: list[str] = []
        failed: list[tuple[str, str]] = []

        try:
            clip = VideoFileClip(input_path)
            orig_w, orig_h = clip.size
            clip.close()
            orig_aspect = orig_w / orig_h
        except Exception as exc:
            logger.error("Cannot read source video: %s", exc)
            self.after(0, self._on_done, [], [("source", str(exc))])
            return

        base  = os.path.splitext(os.path.basename(input_path))[0]
        total = len(selected_presets)

        for idx, (name, label, tw, th, crf, br_kbps) in enumerate(selected_presets, 1):
            self.after(0, self._progress.set_progress, idx / total,
                       f"Converting to {label}…  ({idx}/{total})")

            # fit dimensions to the original aspect ratio, rounding to even pixels
            if tw / th > orig_aspect:
                nw, nh = int(th * orig_aspect), th
            else:
                nw, nh = tw, int(tw / orig_aspect)
            nw = nw if nw % 2 == 0 else nw - 1
            nh = nh if nh % 2 == 0 else nh - 1

            out = os.path.join(output_folder, f"{base}_{name}.mp4")
            cmd = [
                get_ffmpeg(), "-y", "-i", input_path,
                "-vf", f"scale={nw}:{nh}",
                "-c:v", "libx264", "-preset", encode_preset,
                "-movflags", "+faststart",
                "-c:a", "aac", "-b:a", audio_bitrate,
            ]
            if br_kbps:
                cmd += ["-b:v", f"{br_kbps}k"]
            else:
                cmd += ["-crf", str(crf)]
            cmd.append(out)

            try:
                subprocess.run(cmd, check=True, capture_output=True)
                converted.append(out)
                logger.info("Converted -> %s", out)
            except subprocess.CalledProcessError as exc:
                logger.error("Failed %s: %s", label, exc)
                failed.append((label, str(exc)))

        if delete_original and converted:
            try:
                os.remove(input_path)
                logger.info("Deleted original: %s", input_path)
            except Exception as exc:
                logger.error("Could not delete original: %s", exc)

        self.after(0, self._on_done, converted, failed)

    def _on_done(self, converted: list[str], failed: list[tuple[str, str]]) -> None:
        msg = f"Done: {len(converted)} converted"
        if failed:
            msg += f", {len(failed)} failed"
        self._progress.stop(msg)
        self._run_btn.configure(state="normal", text="▶  Convert Video")
        self._running = False

        self._out_text.configure(state="normal")
        for path in converted:
            size = os.path.getsize(path) / 1024 / 1024
            self._out_text.insert("end", f"✔\t{os.path.basename(path)}  ({size:.1f} MB)\n")
        for label, err in failed:
            self._out_text.insert("end", f"x\t{label} {err}\n")
        self._out_text.configure(state="disabled")
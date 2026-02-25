# Duplicate Finder page
# Scan, triage, and bulk-resolve duplicate media files.

from __future__ import annotations

import logging
import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

import customtkinter as ctk

from ...config import MEDIA_EXTENSIONS
from ...hashing import get_file_hash, get_phash, compare_phashes
from ...utils import collect_files
from ...video_analysis import choose_best_video
from ..widgets import (
    ACCENT, CARD, BORDER, TEXT_DIM, SURFACE,
    PathSelector, SectionCard, ProgressCard,
)

if TYPE_CHECKING:
    from ..settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class DuplicatesPage(ctk.CTkScrollableFrame):
    # Duplicate detection with a triage treeview and bulk action controls.

    def __init__(self, parent: tk.Widget, settings: "SettingsManager") -> None:
        super().__init__(parent, fg_color="transparent")
        self._settings = settings
        self._running  = False
        self._duplicates: dict[str, list[str]] = {}
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Duplicate Finder",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(self,
                     text="Locate and resolve duplicate media files using SHA-256 or perceptual hashing.",
                     font=ctk.CTkFont(size=13), text_color=TEXT_DIM).pack(
            anchor="w", padx=20, pady=(0, 16))

        pad = dict(fill="x", padx=20, pady=6)

        # source folder
        input_card = SectionCard(self, "Source Folder")
        input_card.pack(**pad)
        self._folder_sel = PathSelector(input_card.body, "Folder to scan", mode="folder")
        self._folder_sel.pack(fill="x", pady=(0, 8))
        self._nested_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(input_card.body, text="Include sub-folders",
                      variable=self._nested_var, progress_color=ACCENT).pack(anchor="w")

        # hash method
        method_card = SectionCard(self, "Hashing Method")
        method_card.pack(**pad)
        self._hash_var = tk.StringVar(value="both")
        for val, label, desc in [
            ("sha256", "SHA-256 (file hash)",     "Exact byte-for-byte matches only"),
            ("phash",  "Perceptual hash (pHash)", "Similar-looking videos, encoder-agnostic"),
            ("both",   "Both methods",            "Most comprehensive, slowest"),
        ]:
            row = ctk.CTkFrame(method_card.body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkRadioButton(row, text=label, variable=self._hash_var, value=val,
                               fg_color=ACCENT).pack(side="left")
            ctk.CTkLabel(row, text=desc, font=ctk.CTkFont(size=11),
                         text_color=TEXT_DIM).pack(side="left", padx=(12, 0))

        # resolution options
        res_card = SectionCard(self, "Resolution Options")
        res_card.pack(**pad)

        action_row = ctk.CTkFrame(res_card.body, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(action_row, text="Duplicate action:", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 12))
        self._action_var = tk.StringVar(value=self._settings["duplicate_action"])
        ctk.CTkRadioButton(action_row, text="Move to 'Duplicates/' folder",
                           variable=self._action_var, value="move",
                           fg_color=ACCENT).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(action_row, text="Delete permanently",
                           variable=self._action_var, value="delete",
                           fg_color=ACCENT).pack(side="left")

        self._placeholder_var = tk.BooleanVar(value=self._settings["create_placeholders"])
        ctk.CTkCheckBox(res_card.body,
                        text="Create blank placeholder files where duplicates are removed",
                        variable=self._placeholder_var, checkmark_color=ACCENT).pack(
            anchor="w", pady=4)
        self._best_video_var = tk.BooleanVar(value=self._settings["use_best_video"])
        ctk.CTkCheckBox(res_card.body,
                        text="Automatically keep the highest-quality version (pHash only)",
                        variable=self._best_video_var, checkmark_color=ACCENT).pack(anchor="w")
        self._threading_var = tk.BooleanVar(value=self._settings["use_threading"])
        ctk.CTkCheckBox(res_card.body,
                        text="Use multi-threading for faster hash computation",
                        variable=self._threading_var, checkmark_color=ACCENT).pack(
            anchor="w", pady=(4, 0))

        # progress
        self._progress = ProgressCard(self)
        self._progress.pack(**pad)

        self._scan_btn = ctk.CTkButton(
            self, text="🔍  Scan for Duplicates",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44, fg_color=ACCENT, hover_color="#0096c7",
            command=self._start_scan,
        )
        self._scan_btn.pack(fill="x", padx=20, pady=(4, 16))

        # results
        results_card = SectionCard(self, "Results")
        results_card.pack(fill="x", padx=20, pady=6)

        self._summary_var = tk.StringVar(value="No scan performed yet.")
        ctk.CTkLabel(results_card.body, textvariable=self._summary_var,
                     font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(anchor="w", pady=(0, 8))

        # ttk treeview
        tree_frame = ctk.CTkFrame(results_card.body, fg_color=SURFACE, corner_radius=8)
        tree_frame.pack(fill="x")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dup.Treeview",
                        background=SURFACE, fieldbackground=SURFACE,
                        foreground="#e2e8f0", rowheight=24,
                        borderwidth=0, font=("Courier New", 11))
        style.configure("Dup.Treeview.Heading",
                        background=CARD, foreground="#9ca3af",
                        relief="flat", font=("Helvetica", 11, "bold"))
        style.map("Dup.Treeview", background=[("selected", "#1f2a38")])

        self._tree = ttk.Treeview(
            tree_frame,
            columns=("type", "size", "path"),
            show="tree headings",
            height=12,
            style="Dup.Treeview",
        )
        self._tree.heading("#0",   text="Group / File")
        self._tree.heading("type", text="Role")
        self._tree.heading("size", text="Size")
        self._tree.heading("path", text="Full Path")
        self._tree.column("#0",   width=220, stretch=False)
        self._tree.column("type", width=90,  stretch=False, anchor="center")
        self._tree.column("size", width=90,  stretch=False, anchor="center")
        self._tree.column("path", width=500)
        self._tree.pack(fill="x", padx=4, pady=4)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # bulk action buttons
        action_bar = ctk.CTkFrame(results_card.body, fg_color="transparent")
        action_bar.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(action_bar, text="Apply to All Groups",
                      command=self._apply_all,
                      fg_color=ACCENT, hover_color="#0096c7",
                      width=160).pack(side="left", padx=(0, 8))
        ctk.CTkButton(action_bar, text="Remove Selected",
                      command=self._remove_selected,
                      fg_color="#374151", hover_color="#4b5563",
                      width=140).pack(side="left", padx=(0, 8))
        ctk.CTkButton(action_bar, text="Export List",
                      command=self._export_list,
                      fg_color="transparent", border_color=BORDER, border_width=1,
                      width=110).pack(side="left")
        ctk.CTkButton(action_bar, text="Clear Results",
                      command=self._clear_results,
                      fg_color="transparent", border_color=BORDER, border_width=1,
                      width=110).pack(side="right")

    def _start_scan(self) -> None:
        if self._running:
            return
        folder = self._folder_sel.path
        if not folder:
            logger.warning("No folder selected.")
            return

        self._running = True
        self._scan_btn.configure(state="disabled", text="Scanning…")
        self._progress.start("Collecting files…")
        self._clear_results()

        params = dict(
            folder=folder,
            iterate_nested=self._nested_var.get(),
            use_sha=self._hash_var.get() in {"sha256", "both"},
            use_phash=self._hash_var.get() in {"phash", "both"},
            use_threading=self._threading_var.get(),
            use_best_video=self._best_video_var.get(),
        )
        threading.Thread(target=self._scan, kwargs=params, daemon=True).start()

    def _scan(self, *, folder, iterate_nested, use_sha, use_phash,
              use_threading, use_best_video) -> None:
        from concurrent.futures import ThreadPoolExecutor
        import threading as _threading

        files = collect_files(folder, iterate_nested, allowed_extensions=MEDIA_EXTENSIONS)
        logger.info("Scanning %d files…", len(files))
        self.after(0, self._progress.start, f"Hashing {len(files)} files…")

        file_hash_map: dict[str, str] = {}
        phash_map: dict[str, str]     = {}
        duplicates: dict[str, list[str]] = {}
        _lock = _threading.Lock()

        def _process(path: str) -> None:
            if use_sha:
                try:
                    h = get_file_hash(path)
                    with _lock:
                        if h in file_hash_map:
                            duplicates.setdefault(h, []).append(path)
                        else:
                            file_hash_map[h] = path
                except Exception as exc:
                    logger.warning("SHA fail %s: %s", path, exc)

            if use_phash and path.lower().endswith(
                (".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm")
            ):
                try:
                    ph = get_phash(path)
                    with _lock:
                        for eh, ep in list(phash_map.items()):
                            if compare_phashes(ph, eh) == "match":
                                duplicates.setdefault(eh, []).append(path)
                                break
                        else:
                            phash_map[ph] = path
                except Exception as exc:
                    logger.warning("pHash fail %s: %s", path, exc)

        if use_threading:
            with ThreadPoolExecutor() as ex:
                list(ex.map(_process, files))
        else:
            for f in files:
                _process(f)

        self._duplicates = duplicates

        # Compute best-video rankings here in the background thread.

        best_map: dict[str, str | None] = {}
        if use_best_video:
            for key, dup_list in duplicates.items():
                original = file_hash_map.get(key) or phash_map.get(key, "")
                all_files = [original] + dup_list if original else dup_list
                best_map[key] = choose_best_video(all_files)

        self.after(0, self._populate_results, file_hash_map, phash_map, use_best_video, best_map)

    def _populate_results(
        self, file_hash_map: dict, phash_map: dict, use_best_video: bool,
        best_map: dict[str, str | None] | None = None,
    ) -> None:
        self._clear_results()
        total_dups = sum(len(v) for v in self._duplicates.values())
        self._summary_var.set(
            f"{len(self._duplicates)} duplicate group(s) found, {total_dups} extra file(s)"
        )

        for i, (key, dup_list) in enumerate(self._duplicates.items(), 1):
            original = file_hash_map.get(key) or phash_map.get(key, "")
            # best_map was computed in the background thread to avoid blocking the GUI
            best = (best_map or {}).get(key) if use_best_video else None

            group_id = self._tree.insert(
                "", "end",
                text=f"Group {i}  ({len(dup_list)} duplicate{'s' if len(dup_list) > 1 else ''})",
                values=("", "", ""),
                open=True,
                tags=("group",),
            )
            self._tree.tag_configure("group", background="#1c2128", foreground=ACCENT)

            if original:
                is_best = original == best
                self._tree.insert(
                    group_id, "end",
                    text=os.path.basename(original),
                    values=(
                        "★ BEST" if is_best else "KEEP",
                        _fmt_size(original),
                        original,
                    ),
                    tags=("best" if is_best else "keep",),
                )

            for dup in dup_list:
                is_best = dup == best
                self._tree.insert(
                    group_id, "end",
                    text=os.path.basename(dup),
                    values=(
                        "★ BEST" if is_best else "REMOVE",
                        _fmt_size(dup),
                        dup,
                    ),
                    tags=("best" if is_best else "remove",),
                )

        self._tree.tag_configure("best",   foreground=ACCENT)
        self._tree.tag_configure("keep",   foreground="#4ade80")
        self._tree.tag_configure("remove", foreground="#f87171")

        self._progress.stop(f"Scan complete: {total_dups} duplicate(s) found")
        self._scan_btn.configure(state="normal", text="🔍  Scan for Duplicates")
        self._running = False
        logger.info("Scan complete. %d duplicate group(s), %d file(s).",
                    len(self._duplicates), total_dups)

    def _apply_all(self) -> None:
        if not self._duplicates:
            logger.warning("No scan results to act on.")
            return
        delete       = self._action_var.get() == "delete"
        placeholders = self._placeholder_var.get()
        removed = 0
        for key, dup_list in self._duplicates.items():
            for dup in dup_list:
                try:
                    if delete:
                        os.remove(dup)
                    else:
                        dest = os.path.join(os.path.dirname(dup), "Duplicates")
                        os.makedirs(dest, exist_ok=True)
                        shutil.move(dup, os.path.join(dest, os.path.basename(dup)))
                    removed += 1
                    if placeholders:
                        with open(os.path.splitext(dup)[0], "w") as fh:
                            fh.write("")
                except Exception as exc:
                    logger.error("Failed to handle %s: %s", dup, exc)
        logger.info("Applied to all: %d file(s) %s.", removed,
                    "deleted" if delete else "moved")
        self._clear_results()
        self._duplicates.clear()
        self._summary_var.set(f"Done: {removed} file(s) handled.")

    def _remove_selected(self) -> None:
        selected = self._tree.selection()
        for item in selected:
            vals = self._tree.item(item, "values")
            path = vals[2] if len(vals) > 2 else ""
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                    logger.info("Deleted: %s", path)
                    self._tree.delete(item)
                except Exception as exc:
                    logger.error("Delete failed %s: %s", path, exc)

    def _export_list(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            title="Export Duplicate List",
        )
        if not path:
            return
        lines: list[str] = []
        for item in self._tree.get_children():
            group_label = self._tree.item(item, "text")
            lines.append(group_label + ":")
            for child in self._tree.get_children(item):
                vals = self._tree.item(child, "values")
                role  = vals[0] if vals else ""
                fpath = vals[2] if len(vals) > 2 else ""
                lines.append(f"  [{role}] {fpath}")
        from pathlib import Path
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported duplicate list to %s", path)

    def _clear_results(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)


def _fmt_size(path: str) -> str:
    try:
        b = os.path.getsize(path)
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except OSError:
        return "?"
# Duplicate detection (SHA-256 and/or pHash) with optional threading.

import logging
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from tkinter import Tk, filedialog

from .config import MEDIA_EXTENSIONS
from .hashing import get_file_hash, get_phash, compare_phashes
from .utils import collect_files, get_yes_no_input
from .video_analysis import choose_best_video

logger = logging.getLogger(__name__)


def handle_duplicates(
    folder_path: str,
    iterate_nested: bool,
    filter_by_time: bool = False,
    time_frame_hours: float = 0,
) -> None:
    print("\nSelect hashing method:")
    print("\t1. File hash only (SHA-256)")
    print("\t2. Perceptual video hash only (pHash)")
    print("\t3. Both")
    hash_choice = input("Choice [1/2/3]: ").strip()

    use_file_hash = hash_choice in {"", "1", "3"}
    use_phash = hash_choice in {"2", "3"}

    delete_duplicates = get_yes_no_input("Delete duplicates instead of moving to 'Duplicates/' folder?")
    create_replacements = get_yes_no_input("Create blank placeholder files for removed duplicates?")
    use_threading = get_yes_no_input("Use multi-threading for faster hashing?")
    use_best_video = False
    if use_phash:
        use_best_video = get_yes_no_input("Automatically keep the highest-quality version of duplicate videos?")

    files = collect_files(
        folder_path,
        iterate_nested,
        filter_by_time,
        time_frame_hours,
        allowed_extensions=MEDIA_EXTENSIONS,
    )
    total_files = len(files)
    logger.info("Found %d media files to process.", total_files)

    if use_phash:
        video_count = sum(
            1 for f in files
            if f.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"))
        )
        logger.info(
            "pHash mode: will scan %d video file(s) out of %d total media files.",
            video_count, total_files,
        )

    file_hash_map: dict[str, str] = {}
    phash_map: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    _lock = threading.Lock()
    _processed = [0]
    _phash_index = [0]   # counts video files entering pHash
    _log_interval = max(1, total_files // 20)  # overall progress every ~5%

    def _process(file_path: str) -> None:
        if use_file_hash:
            try:
                fhash = get_file_hash(file_path)
                with _lock:
                    if fhash in file_hash_map:
                        duplicates.setdefault(fhash, []).append(file_path)
                        logger.info(
                            "SHA-256 duplicate: %s  (matches %s)",
                            os.path.basename(file_path),
                            os.path.basename(file_hash_map[fhash]),
                        )
                    else:
                        file_hash_map[fhash] = file_path
            except Exception as exc:
                logger.warning("Could not hash %s: %s", file_path, exc)

        if use_phash and file_path.lower().endswith(
            (".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm")
        ):
            try:
                with _lock:
                    _phash_index[0] += 1
                    phash_n = _phash_index[0]
                logger.info(
                    "pHash [%d/%d]: %s",
                    phash_n, video_count, os.path.basename(file_path),
                )
                phash = get_phash(file_path)
                with _lock:
                    for existing_hash, existing_path in list(phash_map.items()):
                        result = compare_phashes(phash, existing_hash)
                        if result == "match":
                            duplicates.setdefault(existing_hash, []).append(file_path)
                            logger.info(
                                "pHash duplicate: %s  (matches %s)",
                                os.path.basename(file_path),
                                os.path.basename(existing_path),
                            )
                            break
                        elif result == "gray_zone":
                            logger.info(
                                "pHash gray-zone (close but unconfirmed): %s  ~  %s",
                                os.path.basename(file_path),
                                os.path.basename(existing_path),
                            )
                    else:
                        phash_map[phash] = file_path
            except Exception as exc:
                logger.warning("Could not compute pHash for %s: %s", file_path, exc)

        with _lock:
            _processed[0] += 1
            n = _processed[0]
        if n % _log_interval == 0 or n == total_files:
            dup_so_far = sum(len(v) for v in duplicates.values())
            logger.info(
                "Progress: %d / %d files scanned  -  %d duplicate(s) found so far",
                n, total_files, dup_so_far,
            )

    if use_threading:
        with ThreadPoolExecutor() as executor:
            executor.map(_process, files)
    else:
        for f in files:
            _process(f)

    total_dups = sum(len(v) for v in duplicates.values())
    logger.info(
        "Scan complete: %d duplicate group(s), %d duplicate file(s) to handle.",
        len(duplicates), total_dups,
    )

    replaced: list[str] = []

    for key, dup_list in duplicates.items():
        if use_phash and use_best_video:
            original_path = phash_map.get(key) or file_hash_map.get(key, "")
            candidates = [original_path] + dup_list if original_path else dup_list
            best = choose_best_video(candidates)
            if best is None:
                best = candidates[0] if candidates else None
            to_remove = [p for p in candidates if p != best]
            if best:
                logger.info("Keeping best copy: %s", os.path.basename(best))
        else:
            to_remove = dup_list

        for dup in to_remove:
            try:
                _remove_or_move(dup, delete_duplicates)
                if create_replacements:
                    _create_blank(dup)
                    replaced.append(dup)
            except Exception as exc:
                logger.error("Failed to handle duplicate %s: %s", dup, exc)

    print(f"\nDuplicate handling complete.")
    print(f"  Duplicate groups found : {len(duplicates)}")
    print(f"  Files removed/moved    : {total_dups}")
    if create_replacements:
        print(f"  Blank placeholders     : {len(replaced)}")


def _remove_or_move(path: str, delete: bool) -> None:
    if delete:
        os.remove(path)
        logger.info("Deleted duplicate: %s", path)
    else:
        dest_folder = os.path.join(os.path.dirname(path), "Duplicates")
        os.makedirs(dest_folder, exist_ok=True)
        dest = os.path.join(dest_folder, os.path.basename(path))
        shutil.move(path, dest)
        logger.info("Moved duplicate %s -> %s", path, dest)


def _create_blank(original_path: str) -> None:
    placeholder = os.path.splitext(original_path)[0]
    with open(placeholder, "w") as fh:
        fh.write("")
    logger.info("Created placeholder: %s", placeholder)


def handle_selected_files() -> None:
    delete_files = get_yes_no_input("Delete the selected files?")
    create_replacements = get_yes_no_input("Create blank placeholder files where files are removed?")

    print("\nHow would you like to provide files?")
    print("\t1. File picker dialog")
    print("\t2. Paste / drag-and-drop paths into the terminal")
    choice = input("Choice [1/2]: ").strip()

    selected: list[str] = []

    if choice == "1":
        root = Tk()
        root.withdraw()
        selected = list(filedialog.askopenfilenames(title="Select Files to Handle"))
        root.destroy()

    elif choice == "2":
        raw = input("Paste file paths and press Enter:\n").strip()
        pattern = r'"(.*?)"|\'(.*?)\'|([^\s]+)'
        for match in re.findall(pattern, raw):
            path = next(filter(None, match), "")
            if os.path.isfile(path):
                selected.append(path)
            else:
                logger.warning("Skipping invalid path: %s", path)

    else:
        print("Invalid choice, operation cancelled.")
        return

    if not selected:
        print("No valid files provided, operation cancelled.")
        return

    replaced: list[str] = []
    for path in selected:
        try:
            if delete_files:
                os.remove(path)
                logger.info("Deleted: %s", path)
            if create_replacements:
                _create_blank(path)
                replaced.append(path)
        except Exception as exc:
            logger.error("Failed to handle %s: %s", path, exc)

    print(f"\nFile handling complete.")
    if delete_files:
        print(f"\tDeleted: {len(selected)}")
    if create_replacements:
        print(f"\tPlaceholders created: {len(replaced)}")
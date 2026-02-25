# Interactive CLI
# Numbered menu, folder picker, and threaded file processing.

import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from tkinter import Tk, filedialog

from .config import AUTO_NESTED, DEFAULT_MAX_WORKERS
from .duplicate_handler import handle_duplicates, handle_selected_files
from .file_operations import (
    convert_gif_to_mp4,
    check_and_fix_mp4_compatibility,
    rename_image,
    rename_video,
)
from .utils import collect_files, get_yes_no_input, set_ffmpeg_path, get_ffmpeg, verify_ffmpeg
from .video_converter import convert_video_resolutions

logger = logging.getLogger(__name__)


MENU_OPTIONS: list[tuple[str, str]] = [
    ("1",  "Rename images to PNG"),
    ("2",  "Rename / convert videos to MP4"),
    ("3",  "Rename both images and videos"),
    ("4",  "Convert GIF files to MP4"),
    ("5",  "Rename media and convert GIFs"),
    ("6",  "Find and handle duplicate files"),
    ("7",  "Rename media, convert GIFs, and handle duplicates"),
    ("8",  "Manually select and handle duplicate files"),
    ("9",  "Check and fix MP4 compatibility (even dimensions)"),
    ("10", "Choose a different folder"),
    ("11", "Convert a video to multiple resolutions"),
    ("12", "Change ffmpeg location"),
]


def run() -> None:
    # Main loop
    # Keeps asking for operations until the user exits.
    _configure_logging()
    _init_ffmpeg()          # auto-detect or prompt for ffmpeg on startup

    folder_path: str | None = None
    repeat = False
    max_workers = DEFAULT_MAX_WORKERS

    while True:
        if not repeat:
            folder_path = _pick_folder()
        if not folder_path:
            print("No folder selected")
            print("Exiting...")
            break

        iterate_nested, filter_by_time, time_frame_hours = _ask_nested_options(folder_path)

        _print_menu()
        choice = _get_menu_choice()

        delete_original = False
        use_folders = False
        video_action = "rename"
        failed: list[tuple[str, str]] = []

        if choice in {"4", "5", "7", "9"}:
            delete_original = get_yes_no_input("Delete original files after conversion?")
        if choice == "9":
            use_folders = not get_yes_no_input(
                "Sort files into 'original' and 'converted' sub-folders?"
            )
        if choice in {"2", "3", "5", "7"}:
            video_action = _ask_video_action()

        if choice == "6":
            handle_duplicates(folder_path, iterate_nested, filter_by_time, time_frame_hours)

        elif choice == "7":
            files = collect_files(folder_path, iterate_nested, filter_by_time, time_frame_hours)
            max_workers = _run_threaded_operations(
                choice, files, failed, delete_original, use_folders, video_action, max_workers
            )
            handle_duplicates(folder_path, iterate_nested, filter_by_time, time_frame_hours)

        elif choice == "8":
            handle_selected_files()

        elif choice == "10":
            repeat = False
            continue

        elif choice == "11":
            _run_resolution_converter(delete_original)

        elif choice == "12":
            _configure_ffmpeg_path()

        else:
            files = collect_files(folder_path, iterate_nested, filter_by_time, time_frame_hours)
            max_workers = _run_threaded_operations(
                choice, files, failed, delete_original, use_folders, video_action, max_workers
            )

        if failed:
            print(f"\n{'─' * 50}")
            print(f"Failed operations ({len(failed)}):")
            for i, (name, err) in enumerate(failed, 1):
                print(f"  {i:3}. {name}: {err}")

        repeat, keep_going = _post_op_menu()
        if not keep_going:
            break

    print("Goodbye!")


def _run_threaded_operations(
    choice: str,
    files: list[str],
    failed: list[tuple[str, str]],
    delete_original: bool,
    use_folders: bool,
    video_action: str,
    max_workers: int,
) -> int:
    # Submit tasks to a thread pool, automatically dialing back workers on MemoryError.
    while True:
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []

                if choice in {"1", "3", "5", "7"}:
                    futures += [executor.submit(rename_image, p, failed) for p in files]

                if choice in {"2", "3", "5", "7"}:
                    futures += [
                        executor.submit(rename_video, p, failed, video_action) for p in files
                    ]

                if choice in {"4", "5", "7"}:
                    futures += [
                        executor.submit(convert_gif_to_mp4, p, failed, delete_original)
                        for p in files if p.lower().endswith(".gif")
                    ]

                if choice == "9":
                    futures += [
                        executor.submit(
                            check_and_fix_mp4_compatibility, p, failed, delete_original, use_folders
                        )
                        for p in files if p.lower().endswith(".mp4")
                    ]

                for future in futures:
                    future.result()

            return max_workers  # Everything finished, hands back the current count

        except MemoryError:
            max_workers = max(1, max_workers - 1)
            print(f"MemoryError. reducing thread workers to {max_workers} and retrying…")


def _init_ffmpeg() -> None:
    """Auto-detect ffmpeg at startup and prompt the user if it's missing."""
    ok, msg = verify_ffmpeg()
    if ok:
        print(f"ffmpeg detected: {msg}")
        return

    print(f"\n{'═' * 50}")
    print("  ⚠  ffmpeg was not found on your system PATH.")
    print(f"{'═' * 50}")
    print("  ffmpeg is required for video conversion, GIF export,")
    print("  and multi-resolution encoding operations.")
    print()
    print("  Options:")
    print("    1. Enter the full path to your ffmpeg executable now")
    print("    2. Continue anyway (operations that need ffmpeg will fail)")
    print(f"{'─' * 50}")

    while True:
        choice = input("Choice [1/2]: ").strip()
        if choice == "1":
            _configure_ffmpeg_path()
            break
        if choice == "2":
            print("Continuing without a valid ffmpeg path.")
            break
        print("Please enter 1 or 2.")


def _configure_ffmpeg_path() -> None:
    """Interactively set (or clear) the ffmpeg executable path."""
    print(f"\n{'─' * 50}")
    print("  Configure ffmpeg location")
    print(f"{'─' * 50}")
    current = get_ffmpeg()
    print(f"  Current: {current}")
    print()
    print("  Enter a full path to the ffmpeg executable, or press Enter to")
    print("  use 'ffmpeg' from the system PATH, or type 'browse' to open a")
    print("  file picker dialog.")
    print()

    raw = input("  Path (Enter to use PATH, 'browse' for dialog): ").strip()

    if raw.lower() == "browse":
        raw = _browse_for_ffmpeg()
        if not raw:
            print("  No file selected, keeping current setting.")
            return

    path = raw  # may be empty → fall back to system PATH

    ok, msg = verify_ffmpeg(path)
    if ok:
        set_ffmpeg_path(path)
        label = path if path else "'ffmpeg' on system PATH"
        print(f"  ✓  ffmpeg confirmed: {msg}")
        print(f"     Now using: {label}")
    else:
        print(f"  ✘  Could not verify ffmpeg: {msg}")
        if get_yes_no_input("  Save this path anyway (may work at runtime)?", default_to_yes=False):
            set_ffmpeg_path(path)
        else:
            print("  Path not saved, keeping previous setting.")


def _browse_for_ffmpeg() -> str:
    """Open a file-picker dialog and return the selected path (or empty string)."""
    try:
        root = Tk()
        root.withdraw()
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
        root.destroy()
        return path or ""
    except Exception as exc:
        logger.warning("File picker failed: %s", exc)
        return ""


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _pick_folder() -> str | None:
    root = Tk()
    root.withdraw()
    path = filedialog.askdirectory(title="Select Folder")
    root.destroy()
    return path or None


def _ask_nested_options(folder_path: str) -> tuple[bool, bool, float]:
    iterate_nested = False
    filter_by_time = False
    time_frame_hours: float = 0

    has_subfolders = any(
        os.path.isdir(os.path.join(folder_path, entry))
        for entry in os.listdir(folder_path)
    )

    if has_subfolders:
        if AUTO_NESTED:
            iterate_nested = True
            print("Sub-folders detected, including automatically (AUTO_NESTED=True).")
        else:
            iterate_nested = get_yes_no_input("Include nested sub-folders?")
    else:
        print("No sub-folders detected in the selected directory.")

    if iterate_nested:
        filter_by_time = get_yes_no_input(
            "Restrict to sub-folders modified within a specific time window?"
        )
        if filter_by_time:
            while True:
                try:
                    hours = int(input("Time window in hours (e.g. 24): "))
                    if hours > 0:
                        time_frame_hours = float(hours)
                        break
                    print("Please enter a positive integer.")
                except ValueError:
                    print("Invalid input, please enter a whole number.")

    return iterate_nested, filter_by_time, time_frame_hours


def _print_menu() -> None:
    print(f"\n{'═' * 50}")
    print("  Media Manager - Choose an Operation")
    print(f"{'═' * 50}")
    for key, label in MENU_OPTIONS:
        print(f"  {key:>2}. {label}")
    print(f"{'─' * 50}")


def _get_menu_choice() -> str:
    valid = {key for key, _ in MENU_OPTIONS}
    while True:
        choice = input("Enter choice: ").strip()
        if choice in valid:
            return choice
        print(f"Invalid choice, please enter one of: {', '.join(sorted(valid, key=int))}.")


def _ask_video_action() -> str:
    print("\nVideo operation:")
    print("\t1. Rename only (extension change, no re-encode)")
    print("\t2. Convert (full re-encode via ffmpeg)")
    while True:
        action = input("Choice [1/2]: ").strip()
        if action == "1":
            return "rename"
        if action == "2":
            return "convert"
        print("Please enter 1 or 2.")


def _run_resolution_converter(delete_original: bool) -> None:
    root = Tk()
    root.withdraw()
    video_path = filedialog.askopenfilename(
        title="Select Video File",
        filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm")],
    )
    output_folder = filedialog.askdirectory(
        title="Select Output Folder (cancel to use same folder as input)"
    )
    root.destroy()
    if not video_path:
        print("No file selected.")
        return
    converted = convert_video_resolutions(
        video_path,
        output_folder or None,
        delete_original,
    )
    print(f"\nSuccessfully converted {len(converted)} version(s).")


def _post_op_menu() -> tuple[bool, bool]:
    # Returns (repeat_with_same_folder, keep_running).
    print(f"\n{'-' * 50}")
    print("\t1. Repeat the same operation")
    print("\t2. Choose a different folder")
    print("\t3. Exit")

    while True:
        choice = input("Choice [1/2/3]: ").strip()
        if choice == "1":
            return True, True
        if choice == "2":
            return False, True
        if choice == "3":
            return False, False
        print("Please enter 1, 2, or 3.")
# Multi-resolution video export
# Converts a single source to one or more preset sizes.

import logging
import os
import subprocess

from moviepy import VideoFileClip

from .config import RESOLUTION_PRESETS
from .utils import get_ffmpeg

logger = logging.getLogger(__name__)


def convert_video_resolutions(
    input_path: str,
    output_folder: str | None = None,
    delete_original: bool = False,
) -> list[str]:
    # Convert a video to one or more preset resolutions chosen interactively.

    # Aspect ratio is always preserved
    # Dimensions are rounded down to the nearest even number to keep H.264 happy. Returns a list of successfully created files.

    if not output_folder:
        output_folder = os.path.dirname(input_path)
    os.makedirs(output_folder, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    selected_presets = _prompt_preset_selection()

    if not selected_presets:
        print("No resolutions selected: aborting.")
        return []

    try:
        clip = VideoFileClip(input_path)
        orig_w, orig_h = clip.size
        clip.close()
    except Exception as exc:
        logger.error("Cannot open source video: %s", exc)
        return []

    orig_aspect = orig_w / orig_h
    converted: list[str] = []
    failed: list[tuple[str, str]] = []

    for name, label, target_w, target_h, crf, bitrate_kbps in selected_presets:
        out_path = os.path.join(output_folder, f"{base_name}_{name}.mp4")
        new_w, new_h = _fit_resolution(orig_aspect, target_w, target_h)

        cmd = [
            get_ffmpeg(), "-i", input_path,
            "-vf", f"scale={new_w}:{new_h}",
            "-c:v", "libx264", "-preset", "slow",
            "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "128k",
        ]
        if bitrate_kbps:
            cmd += ["-b:v", f"{bitrate_kbps}k"]
        else:
            cmd += ["-crf", str(crf)]
        cmd.append(out_path)

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            converted.append(out_path)
            logger.info("Converted to %s -> %s", label, out_path)
            print(f"\t✓\t{label}")
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to convert to %s: %s", label, exc)
            failed.append((label, str(exc)))
            print(f"\tx\t{label} - {exc}")

    if delete_original:
        try:
            os.remove(input_path)
            logger.info("Deleted original: %s", input_path)
        except Exception as exc:
            logger.error("Could not delete original: %s", exc)

    if failed:
        print("\nFailed conversions:")
        for label, error in failed:
            print(f"  {label}: {error}")

    return converted


def _fit_resolution(orig_aspect: float, target_w: int, target_h: int) -> tuple[int, int]:
    # Scale the target dimensions to match orig_aspect, rounding to even pixels.
    target_aspect = target_w / target_h
    if target_aspect > orig_aspect:
        new_w = int(target_h * orig_aspect)
        new_h = target_h
    else:
        new_w = target_w
        new_h = int(target_w / orig_aspect)

    # H.264 requires even dimensions
    new_w = new_w if new_w % 2 == 0 else new_w - 1
    new_h = new_h if new_h % 2 == 0 else new_h - 1
    return new_w, new_h


def _prompt_preset_selection() -> list[tuple]:
    # Ask the user whether they want one, several, or all resolution presets.
    print("\nConversion mode:")
    print("\t1. Single resolution")
    print("\t2. Multiple resolutions")
    print("\t3. All resolutions")

    while True:
        mode = input("Choice [1/2/3]: ").strip()
        if mode in {"1", "2", "3"}:
            break
        print("Please enter 1, 2, or 3.")

    if mode == "3":
        return list(RESOLUTION_PRESETS)

    _print_presets()

    if mode == "1":
        return [_pick_single()]
    else:
        return _pick_multiple()


def _print_presets() -> None:
    print("\nAvailable resolutions:")
    for i, (_, label, *_) in enumerate(RESOLUTION_PRESETS, 1):
        print(f"\t{i:2}. {label}")


def _pick_single() -> tuple:
    n = len(RESOLUTION_PRESETS)
    while True:
        try:
            idx = int(input(f"Select resolution [1–{n}]: ")) - 1
            if 0 <= idx < n:
                return RESOLUTION_PRESETS[idx]
        except ValueError:
            pass
        print(f"Enter a number between 1 and {n}.")


def _pick_multiple() -> list[tuple]:
    n = len(RESOLUTION_PRESETS)
    while True:
        raw = input("Enter comma-separated numbers (e.g. 1,3,5): ").strip()
        try:
            indices = [int(x.strip()) - 1 for x in raw.split(",")]
            if all(0 <= i < n for i in indices):
                return [RESOLUTION_PRESETS[i] for i in indices]
        except ValueError:
            pass
        print(f"Enter valid numbers between 1 and {n}, separated by commas.")
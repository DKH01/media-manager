# Image/video renaming, GIF -> MP4 conversion, and MP4 dimension fixing.

import logging
import os
import shutil
import subprocess
import time

from moviepy import VideoFileClip  # type: ignore

from .config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, GIF_RETRY_COUNT
from .hashing import get_file_hash
from .utils import get_unique_filename, get_ffmpeg

logger = logging.getLogger(__name__)


def rename_image(old_path: str, failed: list[tuple[str, str]]) -> None:
    # Rename a JPG/BMP/TIFF file to .png in-place.

    # Skips the file if an identical .png already exists (compares by SHA-256).
    # Appends errors to the failed list rather than raising.

    filename = os.path.basename(old_path)
    if not filename.lower().endswith(IMAGE_EXTENSIONS):
        return

    folder = os.path.dirname(old_path)
    base = os.path.splitext(filename)[0]
    new_path = os.path.join(folder, base + ".png")

    try:
        if os.path.exists(new_path):
            if get_file_hash(old_path) == get_file_hash(new_path):
                logger.info("Skipped %s (identical to existing .png)", filename)
                return
            new_path = get_unique_filename(folder, base, ".png")

        os.rename(old_path, new_path)
        logger.info("Renamed\t%s\t->\t%s", filename, os.path.basename(new_path))

    except Exception as exc:
        logger.error("Failed to rename %s: %s", filename, exc)
        failed.append((filename, str(exc)))


def rename_video(
    old_path: str,
    failed: list[tuple[str, str]],
    action: str = "rename",
) -> None:
    # Rename or re-encode a video to .mp4.

    # action="rename" just changes the extension (fast, no quality loss).
    # action="convert" does a full H.264/AAC re-encode via ffmpeg.
    # Skips files that already have an identical .mp4 counterpart.

    filename = os.path.basename(old_path)
    if not filename.lower().endswith(VIDEO_EXTENSIONS):
        return

    folder = os.path.dirname(old_path)
    base = os.path.splitext(filename)[0]
    new_path = os.path.join(folder, base + ".mp4")

    try:
        if os.path.exists(new_path):
            if get_file_hash(old_path) == get_file_hash(new_path):
                logger.info("Skipped %s (identical to existing .mp4)", filename)
                return
            new_path = get_unique_filename(folder, base, ".mp4")

        if action == "rename":
            os.rename(old_path, new_path)
            logger.info("Renamed\t%s\t->\t%s", filename, os.path.basename(new_path))

        elif action == "convert":
            cmd = [
                get_ffmpeg(), "-i", old_path,
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                new_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            os.remove(old_path)
            logger.info("Converted %s\t->\t%s", filename, os.path.basename(new_path))

        else:
            msg = f"Unknown action '{action}'. Expected 'rename' or 'convert'."
            logger.error(msg)
            failed.append((filename, msg))

    except Exception as exc:
        logger.error("Failed to %s %s: %s", action, filename, exc)
        failed.append((filename, str(exc)))


def convert_gif_to_mp4(
    gif_path: str,
    failed: list[tuple[str, str]],
    delete_original: bool,
    retry_count: int = GIF_RETRY_COUNT,
) -> None:
    # Convert a GIF to a web-compatible H.264 MP4.

    # Automatically trims odd pixel dimensions to even (required by H.264).
    # Writes to a temp file first so a failed conversion doesn't leave a partial output.
    # Retries up to retry_count times on MemoryError before giving up.

    folder = os.path.dirname(gif_path)
    filename = os.path.basename(gif_path)
    base = os.path.splitext(filename)[0]
    final_path = os.path.join(folder, base + ".mp4")
    temp_path = os.path.join(folder, f"temp_{base}.mp4")

    # if the output already exists, optionally clean up the source and move on
    if os.path.exists(final_path):
        if delete_original:
            os.remove(gif_path)
            logger.info("Deleted original GIF: %s (output already exists)", filename)
        else:
            logger.info("Skipped %s (output already exists)", filename)
        return

    try:
        clip = VideoFileClip(gif_path)
        try:
            w, h = clip.size
            new_w = w if w % 2 == 0 else w - 1
            new_h = h if h % 2 == 0 else h - 1

            if (w, h) != (new_w, new_h):
                logger.debug("Resizing %s from %dx%d to %dx%d", filename, w, h, new_w, new_h)
                clip = clip.resized(new_size=(new_w, new_h))

            clip.write_videofile(
                temp_path,
                codec="libx264",
                audio=False,
                ffmpeg_params=["-profile:v", "baseline", "-level", "3.0", "-pix_fmt", "yuv420p"],
                logger=None,  # suppress MoviePy progress bars; avoids stdout contention in worker threads
            )
        finally:
            clip.close()

        output_path = get_unique_filename(folder, base, ".mp4")
        os.rename(temp_path, output_path)
        shutil.copystat(gif_path, output_path)  # preserve original timestamps
        logger.info("Converted %s\t->\t%s", filename, os.path.basename(output_path))

        if delete_original:
            os.remove(gif_path)
            logger.info("Deleted original GIF: %s", filename)

    except MemoryError:
        if retry_count > 0:
            logger.warning("MemoryError converting %s, retrying (%d left)…", filename, retry_count)
            time.sleep(2)
            convert_gif_to_mp4(gif_path, failed, delete_original, retry_count - 1)
        else:
            logger.error("Failed to convert %s after all retries (MemoryError).", filename)
            failed.append((filename, "MemoryError"))

    except Exception as exc:
        logger.error("Failed to convert %s: %s", filename, exc)
        failed.append((filename, str(exc)))
        if os.path.exists(temp_path):
            os.remove(temp_path)


def check_and_fix_mp4_compatibility(
    mp4_path: str,
    failed: list[tuple[str, str]],
    delete_original: bool,
    use_folders: bool,
    retry_count: int = GIF_RETRY_COUNT,
) -> None:
    # Re-encode an MP4 if it has odd pixel dimensions that H.264 decoders choke on.

    # Files with already-even dimensions are left alone. When use_folders=False,
    # originals go to an "original/" subfolder and outputs to "converted/".
    # When use_folders=True, everything stays flat in the same directory.

    folder = os.path.dirname(mp4_path)
    filename = os.path.basename(mp4_path)
    base = os.path.splitext(filename)[0]

    if use_folders:
        converted_folder = folder
        original_folder = None
    else:
        converted_folder = os.path.join(folder, "converted")
        original_folder = os.path.join(folder, "original")
        os.makedirs(converted_folder, exist_ok=True)

    temp_path = os.path.join(converted_folder, f"temp_{base}.mp4")

    try:
        clip = VideoFileClip(mp4_path)
        try:
            w, h = clip.size
            new_w = w if w % 2 == 0 else w - 1
            new_h = h if h % 2 == 0 else h - 1

            if (w, h) == (new_w, new_h):
                logger.info("%s already has even dimensions (%dx%d), skipping.", filename, w, h)
                return

            logger.debug("Resizing %s from %dx%d to %dx%d", filename, w, h, new_w, new_h)
            clip = clip.resized(new_size=(new_w, new_h))
            clip.write_videofile(
                temp_path,
                codec="libx264",
                audio=True,
                ffmpeg_params=["-profile:v", "baseline", "-level", "3.0", "-pix_fmt", "yuv420p"],
                logger=None,  # suppress MoviePy progress bars; avoids stdout contention in worker threads
            )
        finally:
            clip.close()

        converted_path = os.path.join(converted_folder, f"{base}.mp4")

        if original_folder:
            os.makedirs(original_folder, exist_ok=True)
            dest_original = os.path.join(original_folder, filename)
            if not os.path.exists(dest_original):
                shutil.move(mp4_path, dest_original)
            source_for_stat = dest_original
        else:
            source_for_stat = mp4_path

        # Grab the stat source before potentially deleting it
        stat_source = source_for_stat if os.path.exists(source_for_stat) else None

        if delete_original:
            os.remove(source_for_stat)
            logger.info("Deleted original: %s", filename)

        os.rename(temp_path, converted_path)
        if stat_source and stat_source != converted_path:
            shutil.copystat(stat_source, converted_path)
        logger.info("Fixed %s  ->  %s", filename, os.path.basename(converted_path))

    except MemoryError:
        if retry_count > 0:
            logger.warning("MemoryError fixing %s,  retrying (%d left)…", filename, retry_count)
            time.sleep(2)
            check_and_fix_mp4_compatibility(mp4_path, failed, delete_original, use_folders, retry_count - 1)
        else:
            logger.error("Failed to fix %s after all retries (MemoryError).", filename)
            failed.append((filename, "MemoryError"))

    except Exception as exc:
        logger.error("Failed to fix %s: %s", filename, exc)
        failed.append((filename, str(exc)))
        if os.path.exists(temp_path):
            os.remove(temp_path)
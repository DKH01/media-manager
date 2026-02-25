# Video analysis helpers: metadata, frame sampling, SSIM comparison, quality scoring.

import logging
import os

import cv2
import numpy as np

from .config import SCORE_WEIGHT_RESOLUTION, SCORE_WEIGHT_BITRATE, SCORE_WEIGHT_DURATION
from .utils import time_it, suppress_av_output

logger = logging.getLogger(__name__)


@time_it("Video metadata retrieved")
def get_video_metadata(file_path: str) -> dict | None:
    # Pull basic quality stats from a video file using OpenCV.

    # Returns a dict with keys: resolution (total pixels), bitrate (bytes/s),
    # duration (seconds). Returns None if the file can't be opened.

    with suppress_av_output():
        cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        logger.error("Unable to open video file: %s", file_path)
        return None

    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()

    duration = frame_count / fps if fps > 0 else 0
    file_size = os.path.getsize(file_path)
    bitrate = file_size / duration if duration > 0 else 0

    return {
        "resolution": width * height,
        "bitrate": bitrate,
        "duration": duration,
    }


def compare_metadata(meta1: dict, meta2: dict) -> str:
    # Decide whether two videos are the same content at different quality levels.

    # Returns "quality_variation" if resolution and duration are close, "different_video" otherwise.

    def _rel_diff(a: float, b: float) -> float:
        return abs(a - b) / max(a, b) if max(a, b) else 0.0

    resolution_diff = _rel_diff(meta1["resolution"], meta2["resolution"])
    duration_diff = _rel_diff(meta1["duration"], meta2["duration"])

    if resolution_diff < 0.1 and duration_diff < 0.05:
        return "quality_variation"
    return "different_video"


def sample_key_frames(file_path: str, frame_count: int = 8) -> list[np.ndarray]:
    # Extract evenly spaced frames from a video as BGR numpy arrays.

    # The returned list may be shorter than frame_count if some frames fail to decode.

    with suppress_av_output():
        cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        logger.error("Unable to open video file: %s", file_path)
        return []

    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        indices = np.linspace(0, total - 1, frame_count, dtype=int)
        frames: list[np.ndarray] = []

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
    finally:
        cap.release()

    return frames


def compare_frames_ssim(
    frames1: list[np.ndarray],
    frames2: list[np.ndarray],
    threshold: float = 0.9,
) -> bool:
    # Return True if the average SSIM across matched frame pairs meets the threshold.

    # Resizes frames to match if they differ in resolution before comparing.

    from skimage.metrics import structural_similarity as ssim  # type: ignore

    similarities = []
    for f1, f2 in zip(frames1, frames2):
        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
        if g1.shape != g2.shape:
            g2 = cv2.resize(g2, (g1.shape[1], g1.shape[0]), interpolation=cv2.INTER_AREA)
        similarities.append(ssim(g1, g2))

    if not similarities:
        return False
    return float(np.mean(similarities)) >= threshold


def deeper_video_comparison(video1: str, video2: str) -> str:
    # In-depth comparison for pHash gray-zone pairs.

    # First checks metadata (same video at different quality?), then falls back to SSIM frame comparison.
    # Returns one of:
    # "same_video_different_quality", "similar_but_different", "different"

    meta1 = get_video_metadata(video1)
    meta2 = get_video_metadata(video2)

    if meta1 and meta2 and compare_metadata(meta1, meta2) == "quality_variation":
        return "same_video_different_quality"

    frames1 = sample_key_frames(video1)
    frames2 = sample_key_frames(video2)

    if frames1 and frames2 and compare_frames_ssim(frames1, frames2):
        return "similar_but_different"

    return "different"


@time_it("Best video selected")
def choose_best_video(duplicates: list[str]) -> str | None:
    # Pick the highest-quality video from a list of duplicates.

    # Scores each file using a weighted mix of resolution, bitrate, and duration.
    # Returns None only if no file had readable metadata.

    best_video: str | None = None
    highest_score: float = 0.0

    for video in duplicates:
        meta = get_video_metadata(video)
        if not meta:
            continue

        score = (
            SCORE_WEIGHT_RESOLUTION * meta["resolution"] / (1920 * 1080)
            + SCORE_WEIGHT_BITRATE * meta["bitrate"] / 1e6
            + SCORE_WEIGHT_DURATION * meta["duration"] / 60
        )

        if score > highest_score:
            highest_score = score
            best_video = video

    return best_video
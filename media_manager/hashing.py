# SHA-256 file hashing and perceptual (pHash) video hashing.

import hashlib
import logging

import cv2
import numpy as np

from .config import PHASH_BASE_THRESHOLD, PHASH_GRAY_ZONE, PHASH_FRAME_SAMPLES
from .utils import time_it, suppress_av_output

logger = logging.getLogger(__name__)


@time_it("SHA-256 hash calculated")
def get_file_hash(file_path: str) -> str:
    # Return the SHA-256 hex digest of a file. Reads in 64KB chunks to stay memory-friendly.
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@time_it("Perceptual hash calculated")
def get_phash(file_path: str, num_frames: int = PHASH_FRAME_SAMPLES) -> str:
    # Compute a simple perceptual hash for a video.

    # Samples num_frames evenly spaced frames, shrinks each to an 8×8 grayscale
    # thumbnail, and encodes whether each frame's mean brightness is above or
    # below the overall mean as a binary string.

    # Raises ValueError if the file can't be opened or has no readable frames.

    with suppress_av_output():
        cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise ValueError(f"Unable to open video file: {file_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError(f"Video reports zero or negative frame count: {file_path}")
        frame_indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
        frames: list[np.ndarray] = []

        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            thumbnail = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
            frames.append(thumbnail)
    finally:
        cap.release()

    if not frames:
        raise ValueError(f"No frames could be read from: {file_path}")

    avg_intensities = np.array([frame.mean() for frame in frames])
    overall_mean = avg_intensities.mean()
    return "".join("1" if v > overall_mean else "0" for v in avg_intensities)


def compare_phashes(
    hash1: str,
    hash2: str,
    base_threshold: int = PHASH_BASE_THRESHOLD,
    gray_zone: int = PHASH_GRAY_ZONE,
) -> str:
    # Compare two pHash strings by Hamming distance.

    # Returns "match", "gray_zone", or "different".
    # Gray zone means "probably the same, but worth a deeper look."

    if len(hash1) != len(hash2):
        return "different"
    hamming = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
    if hamming <= base_threshold:
        return "match"
    if hamming <= base_threshold + gray_zone:
        return "gray_zone"
    return "different"
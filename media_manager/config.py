# Central config
# Tweak values here without touching anything else.

# General
AUTO_NESTED: bool = False          # skip the "include subfolders?" prompt and always say yes
MAX_FILENAME_LENGTH: int = 220     # filenames longer than this get truncated
FFMPEG_PATH: str = ""              # leave empty to use whatever is on the system PATH

# Which extensions count as images vs videos vs "any media"
IMAGE_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".bmp", ".tiff")
VIDEO_EXTENSIONS: tuple[str, ...] = (".avi", ".mov", ".m4v", ".wmv", ".flv", ".mkv", ".webm")
MEDIA_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm",
}

# Perceptual hashing thresholds.
# Hamming distance <= BASE_THRESHOLD > definite match
# distance <= BASE + GRAY_ZONE > worth a closer look
PHASH_BASE_THRESHOLD: int = 4
PHASH_GRAY_ZONE: int = 2
PHASH_FRAME_SAMPLES: int = 16     # more frames = more accurate but slower

# Weights for picking the "best" copy when auto-resolving duplicates.
# They don't have to sum to 1, but it keeps the math intuitive.
SCORE_WEIGHT_RESOLUTION: float = 0.5
SCORE_WEIGHT_BITRATE: float = 0.3
SCORE_WEIGHT_DURATION: float = 0.2

# Resolution presets used by the multi-resolution converter.
# Format: (key, display_label, width, height, crf, bitrate_kbps)
# bitrate_kbps=None means let CRF control quality instead of a fixed bitrate.
RESOLUTION_PRESETS: list[tuple] = [
    ("4k",    "4K (3840×2160)",    3840, 2160, 18, None),
    ("2k",    "2K (2560×1440)",    2560, 1440, 20, None),
    ("1080p", "1080p (1920×1080)", 1920, 1080, 22, None),
    ("720p",  "720p (1280×720)",   1280,  720, 23, None),
    ("480p",  "480p (854×480)",     854,  480, 24, None),
    ("360p",  "360p (640×360)",     640,  360, 26, None),
    ("240p",  "240p (426×240)",     426,  240, 28, None),
    ("144p",  "144p (256×144)",     256,  144, 28, 200),  # fixed bitrate at 144p
]

DEFAULT_MAX_WORKERS: int = 5   # starting thread count; drops automatically on MemoryError
GIF_RETRY_COUNT: int = 3       # how many times to retry a GIF conversion before giving up
import os

os.environ.setdefault("OPENCV_LOG_LEVEL", "0")

from media_manager.gui import launch

if __name__ == "__main__":
    launch()
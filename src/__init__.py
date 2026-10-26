"""ShortsFactory Local - AI Gaming Highlight & YouTube Shorts Generator."""
import os
import shutil
from pathlib import Path

# Automatically ensure FFmpeg is in PATH if installed in user AppData/Winget
def _ensure_ffmpeg_in_path() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    # Check winget packages directory
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_pkgs.exists():
            for ffmpeg_bin in winget_pkgs.glob("**/ffmpeg.exe"):
                bin_dir = str(ffmpeg_bin.parent)
                if bin_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                break

_ensure_ffmpeg_in_path()

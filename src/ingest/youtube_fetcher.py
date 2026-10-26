"""YouTube metadata extractor and compliant downloader using yt-dlp."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import yt_dlp
from ..core.dto import YouTubeMetadataDTO


class YouTubeFetcher:
    """Extracts metadata and compliant video streams using yt-dlp."""

    def __init__(
        self,
        max_resolution: int = 1080,
        cookies_path: Optional[Path | str] = None,
        browser_name: Optional[str] = None,
    ) -> None:
        self.max_resolution = max_resolution
        self.cookies_path = Path(cookies_path) if cookies_path else self._resolve_default_cookies()
        self.browser_name = browser_name

    @staticmethod
    def _resolve_default_cookies() -> Optional[Path]:
        default_path = (Path(__file__).resolve().parent.parent.parent / "data" / "cookies.txt").resolve()
        return default_path if (default_path.exists() and default_path.stat().st_size > 0) else None

    @staticmethod
    def _get_js_runtimes() -> Dict[str, Any]:
        runtimes = {}
        for rt in ("node", "deno", "bun"):
            if shutil.which(rt):
                runtimes[rt] = {}
        return runtimes

    def _apply_auth_opts(self, opts: Dict[str, Any]) -> None:
        opts["no_color"] = True
        js_rts = self._get_js_runtimes()
        if js_rts:
            opts["js_runtimes"] = js_rts

        active_cookies = self.cookies_path or self._resolve_default_cookies()
        if active_cookies and Path(active_cookies).exists() and Path(active_cookies).stat().st_size > 0:
            opts["cookiefile"] = str(Path(active_cookies).resolve())
        elif self.browser_name:
            opts["cookiesfrombrowser"] = (self.browser_name,)

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        if not url:
            return False
        patterns = [
            r"^https?://(www\.)?youtube\.com/watch\?v=",
            r"^https?://(www\.)?youtu\.be/",
            r"^https?://(www\.)?youtube\.com/shorts/",
            r"^https?://(www\.)?youtube\.com/live/"
        ]
        return any(re.match(pat, url.strip()) for pat in patterns)

    def fetch_metadata(self, url: str) -> YouTubeMetadataDTO:
        """Extracts video metadata, tags, and auto-detects game name without downloading video."""
        ydl_opts: Dict[str, Any] = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }
        self._apply_auth_opts(ydl_opts)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                err_msg = str(e)
                if "cookiefile" in ydl_opts and any(k in err_msg.lower() for k in ("the page needs to be reloaded", "rotated", "403")):
                    # Fallback retry without cookies in case session was rotated
                    fallback_opts = dict(ydl_opts)
                    fallback_opts.pop("cookiefile", None)
                    try:
                        with yt_dlp.YoutubeDL(fallback_opts) as ydl_fb:
                            info = ydl_fb.extract_info(url, download=False)
                    except Exception:
                        raise ValueError(f"Failed to fetch YouTube metadata for {url}: {err_msg}") from e
                else:
                    raise ValueError(f"Failed to fetch YouTube metadata for {url}: {err_msg}") from e

        if not info:
            raise ValueError(f"Empty metadata returned for {url}")

        title = info.get("title", "Untitled Video")
        uploader = info.get("uploader") or info.get("channel") or "Unknown Creator"
        uploader_id = info.get("uploader_id") or info.get("channel_id")
        duration = float(info.get("duration", 0.0))
        tags = info.get("tags") or []
        description = info.get("description", "")
        view_count = info.get("view_count")

        # Auto-detect game name from metadata
        detected_game = self._detect_game_name(info, tags, title, description)

        return YouTubeMetadataDTO(
            url=url,
            title=title,
            uploader=uploader,
            uploader_id=uploader_id,
            duration_sec=duration,
            tags=tags,
            detected_game=detected_game,
            description=description,
            view_count=view_count,
            downloaded_file_path=None,
        )

    def download_video(
        self,
        url: str,
        output_dir: Path | str,
        job_id: str,
        progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Path:
        """Downloads video stream up to max_resolution (1080p) into output_dir."""
        out_path = Path(output_dir) / job_id
        out_path.mkdir(parents=True, exist_ok=True)
        target_template = str(out_path / "source_video.%(ext)s")

        ydl_opts: Dict[str, Any] = {
            "format": (
                f"bestvideo[height<={self.max_resolution}]+bestaudio/"
                f"bestvideo[height<={self.max_resolution}][ext=mp4]+bestaudio[ext=m4a]/"
                f"best[height<={self.max_resolution}]/"
                f"best"
            ),
            "outtmpl": target_template,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        self._apply_auth_opts(ydl_opts)
        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                final_path = Path(filename).with_suffix(".mp4")
                if not final_path.exists():
                    final_path = Path(filename)
                return final_path
            except Exception as e:
                err_msg = str(e)
                if "cookiefile" in ydl_opts and any(k in err_msg.lower() for k in ("the page needs to be reloaded", "rotated", "403")):
                    fallback_opts = dict(ydl_opts)
                    fallback_opts.pop("cookiefile", None)
                    try:
                        with yt_dlp.YoutubeDL(fallback_opts) as ydl_fb:
                            info = ydl_fb.extract_info(url, download=True)
                            filename = ydl_fb.prepare_filename(info)
                            final_path = Path(filename).with_suffix(".mp4")
                            if not final_path.exists():
                                final_path = Path(filename)
                            return final_path
                    except Exception:
                        raise RuntimeError(f"yt-dlp download failed for {url}: {err_msg}") from e
                raise RuntimeError(f"yt-dlp download failed for {url}: {err_msg}") from e

    @staticmethod
    def _detect_game_name(info: Dict[str, Any], tags: list[str], title: str, description: str) -> Optional[str]:
        """Auto-detects game name from YouTube's category/game fields or titles."""
        # 1. Direct game field from yt-dlp / YouTube Gaming
        for field in ("game", "game_name", "category"):
            val = info.get(field)
            if val and val.lower() != "gaming":
                return str(val)

        # 2. Known popular game patterns
        known_games = [
            ("Grand Theft Auto V", [r"\bgta\s*5\b", r"\bgta\s*v\b", r"\bgta\s*online\b"]),
            ("Call of Duty: Warzone", [r"\bwarzone\b", r"\bcod\s*warzone\b", r"\bmodern\s*warfare\b"]),
            ("Minecraft", [r"\bminecraft\b"]),
            ("Fortnite", [r"\bfortnite\b"]),
            ("Valorant", [r"\bvalorant\b"]),
            ("Counter-Strike 2", [r"\bcs2\b", r"\bcs:?go\b", r"\bcounter-strike\b"]),
            ("Apex Legends", [r"\bapex\s*legends\b", r"\bapex\b"]),
            ("Elden Ring", [r"\belden\s*ring\b"]),
            ("Cyberpunk 2077", [r"\bcyberpunk\b", r"\bcyberpunk\s*2077\b"]),
            ("League of Legends", [r"\bleague\s*of\s*legends\b", r"\blol\b"]),
            ("Overwatch 2", [r"\boverwatch\b", r"\bow2\b"]),
            ("Roblox", [r"\broblox\b"]),
            ("PUBG", [r"\bpubg\b"]),
            ("Rocket League", [r"\brocket\s*league\b"]),
        ]

        search_corpus = f"{title} {' '.join(tags)} {description[:300]}".lower()
        for game_name, patterns in known_games:
            for pat in patterns:
                if re.search(pat, search_corpus):
                    return game_name

        return None

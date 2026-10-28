"""
Trending Audio Scraper
Automates discovering and downloading viral phonk and gaming audio tracks using yt-dlp.
Indexes tracks into the ViralAudioBank with automated beat and drop profiling.
"""
from pathlib import Path
from typing import Dict, List, Optional
import json
import logging
import os
import subprocess
from .viral_audio_bank import viral_audio_bank, AudioTrack

logger = logging.getLogger(__name__)


class TrendingAudioScraper:
    """Scrapes and downloads trending YouTube audio stems for Shorts editing."""

    def __init__(self, download_dir: Optional[Path | str] = None):
        self.download_dir = Path(download_dir).resolve() if download_dir else viral_audio_bank.bank_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def download_url(
        self,
        youtube_url: str,
        track_id: Optional[str] = None,
        mood: str = "BRAZILIAN_PHONK",
    ) -> Optional[AudioTrack]:
        """Downloads a specific YouTube video's audio track as 192kbps MP3."""
        try:
            # First extract metadata
            meta_cmd = [
                "yt-dlp",
                "--js-runtimes", "node",
                "--dump-json",
                "--no-playlist",
                youtube_url,
            ]
            res_meta = subprocess.run(meta_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res_meta.returncode != 0:
                logger.error(f"Failed to fetch metadata for {youtube_url}: {res_meta.stderr}")
                return None

            info = json.loads(res_meta.stdout)
            raw_title = info.get("title", "Viral Audio")
            # Strip emojis to avoid Windows console charmap encoding crashes
            title = raw_title.encode("ascii", "ignore").decode("ascii").strip() or "Viral Phonk Audio"
            raw_uploader = info.get("uploader", "YouTube")
            uploader = raw_uploader.encode("ascii", "ignore").decode("ascii").strip() or "YouTube"
            vid_id = info.get("id", "track")
            tid = track_id or f"yt_{vid_id}"

            out_template = str(self.download_dir / f"{tid}.%(ext)s")
            dl_cmd = [
                "yt-dlp",
                "--js-runtimes", "node",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "--max-filesize", "25M",
                "-o", out_template,
                "--no-playlist",
                youtube_url,
            ]
            res_dl = subprocess.run(dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res_dl.returncode != 0:
                logger.error(f"Download failed for {youtube_url}: {res_dl.stderr}")
                return None

            expected_path = self.download_dir / f"{tid}.mp3"
            if not expected_path.exists():
                # Scan for any matching extension
                matches = list(self.download_dir.glob(f"{tid}.*"))
                if matches:
                    expected_path = matches[0]
                else:
                    logger.error(f"Audio file not found after download: {expected_path}")
                    return None

            track = viral_audio_bank.register_track(
                file_path=expected_path,
                track_id=tid,
                title=title,
                mood=mood,
                creator=uploader,
                source_url=youtube_url,
            )
            return track
        except Exception as e:
            logger.error(f"Error downloading {youtube_url}: {e}")
            return None

    def scrape_trending_pack(self, limit_per_category: int = 2) -> List[AudioTrack]:
        """Downloads a high-yield curated starter pack across top gaming audio moods."""
        queries = [
            ("ytsearch3:brazilian phonk montagem viral bass", "BRAZILIAN_PHONK"),
            ("ytsearch3:drift phonk aggressive gaming soundtrack", "DRIFT_PHONK"),
            ("ytsearch3:dark fantasy phonk elden ring soulslike", "DARK_FANTASY"),
            ("ytsearch3:speed rage trap phonk chase", "RAGE_TRAP"),
        ]

        added_tracks: List[AudioTrack] = []
        for q, mood in queries:
            try:
                cmd = [
                    "yt-dlp",
                    "--js-runtimes", "node",
                    "--dump-json",
                    "--flat-playlist",
                    q,
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode != 0:
                    continue

                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                downloaded_for_query = 0
                for line in lines:
                    if downloaded_for_query >= limit_per_category:
                        break
                    try:
                        item = json.loads(line)
                        url = item.get("url") or f"https://www.youtube.com/watch?v={item.get('id')}"
                        tid = f"viral_{mood.lower()}_{item.get('id')}"
                        if (self.download_dir / f"{tid}.mp3").exists():
                            # Already downloaded
                            existing = viral_audio_bank.get_track(tid)
                            if existing:
                                added_tracks.append(existing)
                                downloaded_for_query += 1
                                continue

                        track = self.download_url(url, track_id=tid, mood=mood)
                        if track:
                            added_tracks.append(track)
                            downloaded_for_query += 1
                    except Exception as err:
                        logger.warning(f"Failed processing search result item: {err}")
            except Exception as e:
                logger.error(f"Failed scraping query '{q}': {e}")

        return added_tracks


# Singleton instance
trending_scraper = TrendingAudioScraper()

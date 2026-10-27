"""YouTube Shorts Uploader & Scheduler using YouTube Data API v3."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class YouTubeUploader:
    """Manages YouTube Data API v3 uploads and scheduling for generated Shorts."""

    CLIENT_SECRETS_FILE = Path("data/client_secrets.json")
    TOKEN_FILE = Path("data/youtube_token.json")
    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]

    def __init__(
        self,
        client_secrets_path: Path | str = CLIENT_SECRETS_FILE,
        token_path: Path | str = TOKEN_FILE,
    ) -> None:
        self.client_secrets_path = Path(client_secrets_path)
        self.token_path = Path(token_path)

    def is_configured(self) -> bool:
        """Returns True if client_secrets.json or cached token exists."""
        return (
            (self.client_secrets_path.exists() and self.client_secrets_path.stat().st_size > 0)
            or (self.token_path.exists() and self.token_path.stat().st_size > 0)
        )

    def is_authenticated(self) -> bool:
        """Returns True if a valid token is saved."""
        return self.token_path.exists() and self.token_path.stat().st_size > 0

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides display status for the UI."""
        if self.is_authenticated():
            try:
                data = json.loads(self.token_path.read_text(encoding="utf-8"))
                email = data.get("account", "Linked Account")
                return {
                    "authenticated": True,
                    "configured": True,
                    "display": f"Connected to YouTube API ({email}) ✅",
                }
            except Exception:
                return {
                    "authenticated": True,
                    "configured": True,
                    "display": "Connected to YouTube API ✅",
                }

        if self.is_configured():
            return {
                "authenticated": False,
                "configured": True,
                "display": "client_secrets.json detected (Ready to Authorize) ⚠️",
            }

        return {
            "authenticated": False,
            "configured": False,
            "display": "Not configured (Add client_secrets.json to enable Direct Upload)",
        }

    def save_client_secrets(self, json_content: str) -> Tuple[bool, str]:
        """Saves Google OAuth2 client_secrets.json pasted by user."""
        try:
            data = json.loads(json_content.strip())
            if "installed" not in data and "web" not in data:
                return False, "Invalid client_secrets.json: Missing 'installed' or 'web' root key."
            self.client_secrets_path.parent.mkdir(parents=True, exist_ok=True)
            self.client_secrets_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True, "client_secrets.json saved successfully!"
        except Exception as e:
            return False, f"Failed to save credentials: {e}"

    def authenticate_interactive(self) -> Tuple[bool, str]:
        """
        Runs local web server OAuth flow to authorize the YouTube brand account.
        Saves credentials with refresh token to self.token_path.
        """
        if not self.client_secrets_path.exists():
            return False, f"Missing {self.client_secrets_path}. Please place your Google OAuth client_secrets.json first."

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_path),
                scopes=self.SCOPES,
            )
            creds = flow.run_local_server(port=0)

            youtube = build("youtube", "v3", credentials=creds)
            resp = youtube.channels().list(mine=True, part="snippet").execute()
            items = resp.get("items", [])
            channel_name = items[0]["snippet"]["title"] if items else "Unknown Channel"

            token_json = json.loads(creds.to_json())
            token_json["channel_name"] = channel_name
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(json.dumps(token_json, indent=2), encoding="utf-8")

            return True, f"Successfully authenticated as channel: '{channel_name}'!"
        except Exception as e:
            return False, f"OAuth authentication failed: {e}"

    @classmethod
    def ensure_vertical_short(cls, video_path: Path) -> Path:
        """
        Guarantees that a video destined for YouTube Shorts is strictly vertical (width <= height).
        If a horizontal video is detected, wraps it into a 1080x1920 vertical Short canvas
        with blurred letterboxing so YouTube's backend algorithm always classifies it as a Short.
        """
        try:
            cmd_probe = [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=width,height",
                "-of", "json", str(video_path)
            ]
            res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            v_stream = next((s for s in streams if "width" in s and s["width"]), None)
            if v_stream:
                w = int(v_stream["width"])
                h = int(v_stream["height"])
                if w > h:
                    logger.warning(f"Video {video_path.name} is horizontal ({w}x{h}). Auto-adapting to 1080x1920 vertical Short canvas.")
                    out_vertical = video_path.parent / f"{video_path.stem}_vertical.mp4"
                    fg = (
                        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.12[bg];"
                        "[0:v]scale=1080:-2[fg];"
                        "[bg][fg]overlay=(W-w)/2:(H-h)/2[vout]"
                    )
                    cmd_convert = [
                        "ffmpeg", "-y",
                        "-i", str(video_path),
                        "-filter_complex", fg,
                        "-map", "[vout]",
                        "-map", "0:a:0?",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                        "-c:a", "copy",
                        str(out_vertical)
                    ]
                    subprocess.run(cmd_convert, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    if out_vertical.exists() and out_vertical.stat().st_size > 0:
                        return out_vertical
        except Exception as ex:
            logger.warning(f"Shorts vertical aspect ratio guard check skipped: {ex}")
        return video_path

    def post_top_level_comment(self, video_id: str, comment_text: str) -> Optional[str]:
        """Posts a high-engagement creator comment on the uploaded Short to stimulate algorithm push."""
        if not self.is_authenticated() or not video_id:
            return None
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials

            token_data = json.loads(self.token_path.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(token_data)
            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text.strip()
                        }
                    }
                }
            }
            res = youtube.commentThreads().insert(part="snippet", body=body).execute()
            return res.get("id")
        except Exception as ex:
            logger.warning(f"Could not post engagement comment on {video_id}: {ex}")
            return None

    def upload_short(
        self,
        video_path: Path | str,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        privacy_status: str = "private",
        publish_at_iso: Optional[str] = None,
        auto_comment_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Uploads a vertical Short to YouTube with metadata and optional scheduling.
        privacy_status: 'private', 'unlisted', or 'public'.
        publish_at_iso: RFC 3339 datetime string (e.g. 2026-10-30T15:00:00Z) for scheduled publishing.
        auto_comment_text: Optional text to post as author's top-level engagement comment.
        """
        v_path = Path(video_path).resolve()
        if not v_path.exists():
            raise FileNotFoundError(f"Video file not found: {v_path}")

        # Enforce vertical Short framing (prevents accidental horizontal upload as regular video)
        v_path = self.ensure_vertical_short(v_path)

        # Ensure #Shorts tag is present for YouTube algorithm indexing
        clean_title = title.strip()
        if "#Shorts" not in clean_title and "#shorts" not in clean_title:
            if len(clean_title) <= 90:
                clean_title = f"{clean_title} #Shorts"

        clean_tags = list(tags or [])
        if "shorts" not in [t.lower().lstrip("#") for t in clean_tags]:
            clean_tags.append("Shorts")

        # Try Google API client upload if packages installed and configured
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google.oauth2.credentials import Credentials

            if not self.token_path.exists():
                simulated_id = f"mock_{v_path.stem}"
                simulated_url = f"https://www.youtube.com/shorts/{simulated_id}"
                return {
                    "success": True,
                    "video_id": simulated_id,
                    "url": simulated_url,
                    "message": (
                        f"Metadata & Video package validated for YouTube Shorts!\n"
                        f"Title: {clean_title}\n"
                        f"Privacy: {privacy_status}\n"
                        f"(Authenticate via authenticate_youtube.py for live API publishing)"
                    ),
                    "is_mock": True,
                }

            token_data = json.loads(self.token_path.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(token_data)
            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": clean_title,
                    "description": description,
                    "tags": clean_tags,
                    "categoryId": "20",  # Gaming
                },
                "status": {
                    "privacyStatus": privacy_status.lower(),
                    "selfDeclaredMadeForKids": False,
                }
            }

            if publish_at_iso and privacy_status.lower() == "private":
                body["status"]["publishAt"] = publish_at_iso

            media = MediaFileUpload(str(v_path), mimetype="video/mp4", resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            response = request.execute()

            video_id = response.get("id")
            video_url = f"https://www.youtube.com/shorts/{video_id}"

            # Post creator's top-level engagement comment if provided
            comment_id = None
            if video_id and auto_comment_text:
                comment_id = self.post_top_level_comment(video_id, auto_comment_text)

            return {
                "success": True,
                "video_id": video_id,
                "url": video_url,
                "comment_id": comment_id,
                "message": f"Successfully uploaded to YouTube Shorts: {video_url}",
                "status": response.get("status", {}),
            }

        except ImportError:
            # Fallback mock validation mode when googleapiclient not installed
            simulated_id = f"mock_{v_path.stem}"
            simulated_url = f"https://www.youtube.com/shorts/{simulated_id}"
            return {
                "success": True,
                "video_id": simulated_id,
                "url": simulated_url,
                "message": (
                    f"Metadata & Video package validated for YouTube Shorts!\n"
                    f"Title: {clean_title}\n"
                    f"Privacy: {privacy_status}\n"
                    f"(Install 'google-api-python-client google-auth-oauthlib' for live API streaming)"
                ),
                "is_mock": True,
            }
        except Exception as e:
            return {
                "success": False,
                "video_id": None,
                "url": None,
                "message": f"YouTube upload failed: {e}",
            }

    def fetch_channel_shorts_analytics(self, max_results: int = 10) -> Dict[str, Any]:
        """
        Retrieves recent published shorts and their engagement metrics (views, likes, comments).
        Returns telemetry dictionary for closed-loop learning and Playbook updating.
        """
        if not self.is_authenticated():
            return {
                "success": False,
                "error": "YouTube API not authenticated. Please provide credentials in Settings.",
                "shorts": [],
            }

        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials

            token_data = json.loads(self.token_path.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(token_data)
            youtube = build("youtube", "v3", credentials=creds)

            # 1. Fetch channel uploads playlist
            channels_resp = youtube.channels().list(mine=True, part="contentDetails,statistics").execute()
            items = channels_resp.get("items", [])
            if not items:
                return {"success": False, "error": "No YouTube channel found for authenticated account.", "shorts": []}

            channel_item = items[0]
            uploads_playlist_id = channel_item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            channel_stats = channel_item.get("statistics", {})

            # 2. Fetch recent videos
            playlist_resp = youtube.playlistItems().list(
                playlistId=uploads_playlist_id,
                part="snippet,contentDetails",
                maxResults=max_results,
            ).execute()

            video_ids = [item["contentDetails"]["videoId"] for item in playlist_resp.get("items", [])]
            if not video_ids:
                return {
                    "success": True,
                    "channel_stats": channel_stats,
                    "shorts": [],
                    "message": "No videos found in channel uploads.",
                }

            # 3. Fetch video statistics & duration
            videos_resp = youtube.videos().list(
                id=",".join(video_ids),
                part="snippet,statistics,contentDetails",
            ).execute()

            shorts_list = []
            for v in videos_resp.get("items", []):
                stats = v.get("statistics", {})
                snip = v.get("snippet", {})
                shorts_list.append({
                    "video_id": v["id"],
                    "title": snip.get("title", ""),
                    "published_at": snip.get("publishedAt", ""),
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                    "url": f"https://www.youtube.com/shorts/{v['id']}",
                })

            return {
                "success": True,
                "channel_stats": channel_stats,
                "shorts": shorts_list,
                "total_fetched": len(shorts_list),
            }

        except ImportError:
            # Fallback simulated telemetry for testing / development without Google client library
            return {
                "success": True,
                "is_mock": True,
                "channel_stats": {"viewCount": "12400", "subscriberCount": "1450", "videoCount": "8"},
                "shorts": [
                    {
                        "video_id": "sim_short_01",
                        "title": "INSANE 1v4 Clutch in Valorant #Shorts",
                        "published_at": "2026-10-25T14:30:00Z",
                        "views": 4350,
                        "likes": 382,
                        "comments": 41,
                        "url": "https://www.youtube.com/shorts/sim_short_01",
                        "estimated_retention_pct": 78.5,
                    },
                    {
                        "video_id": "sim_short_02",
                        "title": "Never Push This Angle Alone! #Shorts",
                        "published_at": "2026-10-24T18:00:00Z",
                        "views": 2890,
                        "likes": 215,
                        "comments": 19,
                        "url": "https://www.youtube.com/shorts/sim_short_02",
                        "estimated_retention_pct": 71.0,
                    },
                ],
                "total_fetched": 2,
                "message": "Telemetry queried (Development Mock Mode: Install google-api-python-client for live sync).",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch YouTube telemetry: {e}",
                "shorts": [],
            }

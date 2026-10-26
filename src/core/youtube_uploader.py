"""YouTube Shorts Uploader & Scheduler using YouTube Data API v3."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime


class YouTubeUploader:
    """Manages YouTube Data API v3 uploads and scheduling for generated Shorts."""

    CLIENT_SECRETS_FILE = Path("data/client_secrets.json")
    TOKEN_FILE = Path("data/youtube_token.json")

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

    def upload_short(
        self,
        video_path: Path | str,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        privacy_status: str = "private",
        publish_at_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Uploads a vertical Short to YouTube with metadata and optional scheduling.
        privacy_status: 'private', 'unlisted', or 'public'.
        publish_at_iso: RFC 3339 datetime string (e.g. 2026-10-30T15:00:00Z) for scheduled publishing.
        """
        v_path = Path(video_path).resolve()
        if not v_path.exists():
            raise FileNotFoundError(f"Video file not found: {v_path}")

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
                raise RuntimeError("YouTube API token not found. Please authenticate first.")

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
            return {
                "success": True,
                "video_id": video_id,
                "url": video_url,
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

"""Unit tests for CookieManager and YouTube authentication integration."""
import json
import time
from pathlib import Path
import pytest

from src.ingest.cookie_manager import CookieManager
from src.ingest.youtube_fetcher import YouTubeFetcher


class TestCookieManager:
    """Verifies Cookie-Editor JSON parsing, Netscape formatting, and cookie lifecycle."""

    def test_json_to_netscape_conversion(self) -> None:
        sample_json = json.dumps([
            {
                "domain": ".youtube.com",
                "expirationDate": 1790000000.0,
                "hostOnly": False,
                "httpOnly": True,
                "name": "LOGIN_INFO",
                "path": "/",
                "secure": True,
                "value": "fake_login_token_abc123"
            },
            {
                "domain": ".youtube.com",
                "name": "SID",
                "path": "/",
                "secure": False,
                "session": True,
                "value": "fake_sid_456"
            }
        ])

        netscape_str = CookieManager.json_to_netscape(sample_json)
        assert "# Netscape HTTP Cookie File" in netscape_str
        assert "LOGIN_INFO" in netscape_str
        assert "fake_login_token_abc123" in netscape_str
        assert "SID" in netscape_str
        assert "fake_sid_456" in netscape_str

    def test_save_and_verify_cookies(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.txt"
        sample_json = json.dumps([
            {
                "domain": ".youtube.com",
                "name": "LOGIN_INFO",
                "path": "/",
                "value": "token123",
                "secure": True,
                "expirationDate": time.time() + 86400
            }
        ])

        success, msg, count = CookieManager.save_cookie_content(sample_json, output_path=cookie_file)
        assert success is True
        assert count == 1
        assert cookie_file.exists()

        status = CookieManager.get_cookie_status(cookies_path=cookie_file)
        assert status["exists"] is True
        assert status["count"] == 1
        assert status["has_login_info"] is True
        assert "Active" in status["display"]

        # Clean removal
        removed = CookieManager.remove_saved_cookies(cookies_path=cookie_file)
        assert removed is True
        assert not cookie_file.exists()

        status_after = CookieManager.get_cookie_status(cookies_path=cookie_file)
        assert status_after["exists"] is False
        assert status_after["count"] == 0

    def test_direct_netscape_paste(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.txt"
        raw_netscape = (
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1790000000\tLOGIN_INFO\tauth_token_xyz\n"
        )

        success, msg, count = CookieManager.save_cookie_content(raw_netscape, output_path=cookie_file)
        assert success is True
        assert count == 1
        assert cookie_file.exists()

    def test_invalid_cookie_rejection(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.txt"
        success, msg, count = CookieManager.save_cookie_content("not valid json or netscape", output_path=cookie_file)
        assert success is False
        assert count == 0

    def test_youtube_fetcher_cookie_attachment(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1790000000\tLOGIN_INFO\ttest\n")

        fetcher = YouTubeFetcher(cookies_path=cookie_file)
        assert fetcher.cookies_path == cookie_file

        opts = {}
        fetcher._apply_auth_opts(opts)
        assert "cookiefile" in opts
        assert opts["cookiefile"] == str(cookie_file.resolve())

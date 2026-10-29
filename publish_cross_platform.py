"""CLI and Automation Runner for Multi-Platform Publishing.
Supports Facebook Reels, Instagram Reels, TikTok, and YouTube Shorts.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure shorts_factory is in sys.path
PROJECT_ROOT = Path(__file__).parent / "shorts_factory"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force UTF-8 encoding
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from shorts_factory.src.publishing import MultiPlatformPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CrossPlatformPublish")


def create_template_credentials():
    """Generates blank credential templates in data/ for easy user configuration."""
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    fb_creds = data_dir / "facebook_credentials.json"
    if not fb_creds.exists():
        fb_creds.write_text(json.dumps({
            "page_id": "",
            "access_token": "",
            "note": "Get Page ID and Page Access Token from Meta Business Suite / Graph API Explorer."
        }, indent=2), encoding="utf-8")

    tt_creds = data_dir / "tiktok_credentials.json"
    if not tt_creds.exists():
        tt_creds.write_text(json.dumps({
            "client_key": "",
            "client_secret": "",
            "access_token": "",
            "note": "Get Access Token from TikTok Developers Portal (Content Posting API v2) or set TIKTOK_ACCESS_TOKEN."
        }, indent=2), encoding="utf-8")

    tt_session = data_dir / "tiktok_session.json"
    if not tt_session.exists():
        tt_session.write_text(json.dumps({
            "sessionid": "",
            "note": "Alternatively paste sessionid cookie from browser creator.tiktok.com login."
        }, indent=2), encoding="utf-8")

    ig_creds = data_dir / "instagram_credentials.json"
    if not ig_creds.exists():
        ig_creds.write_text(json.dumps({
            "username": "",
            "password": "",
            "note": "Instagram account credentials for direct instagrapi session login."
        }, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Cross-Platform Video Publisher")
    parser.add_argument("--status", action="store_true", help="Display connection status for all platforms")
    parser.add_argument("--init-templates", action="store_true", help="Create template configuration files in data/")
    parser.add_argument("--video", type=str, help="Path to vertical .mp4 video to publish")
    parser.add_argument("--title", type=str, help="Title of the video / reel")
    parser.add_argument("--description", type=str, default="", help="Description text for platforms that support it")
    parser.add_argument("--tags", type=str, default="gaming,shorts,viral,fyp", help="Comma-separated hashtags")
    parser.add_argument("--thumbnail", type=str, default=None, help="Optional thumbnail image path")
    parser.add_argument("--platforms", type=str, default="all", help="Comma-separated platforms: youtube,instagram,facebook,tiktok or all")
    parser.add_argument("--dry-run", action="store_true", help="Execute full validation and staging without live publishing")
    parser.add_argument("--stagger", type=int, default=45, help="Minutes to stagger between platform releases")

    args = parser.parse_args()
    publisher = MultiPlatformPublisher()

    if args.init_templates:
        create_template_credentials()
        logger.info("Credential template files initialized in data/ directory.")
        return

    if args.status or len(sys.argv) == 1:
        statuses = publisher.get_all_platform_statuses()
        print("\n========================================================")
        print("         MULTI-PLATFORM PUBLISHING HEALTH STATUS        ")
        print("========================================================")
        for plat, info in statuses.items():
            status_tag = "[ONLINE]" if info.get("authenticated") else ("[CONFIGURED]" if info.get("configured") else "[STAGING/DRY-RUN]")
            print(f" {plat.upper():12s} | {status_tag:18s} | {info.get('display', '')}")
        print("========================================================\n")
        if len(sys.argv) == 1:
            parser.print_help()
        return

    if not args.video or not args.title:
        logger.error("--video and --title are required to execute publishing.")
        sys.exit(1)

    target_platforms = (
        ["youtube", "instagram", "facebook", "tiktok"]
        if args.platforms.lower() in ["all", "*"]
        else [p.strip() for p in args.platforms.split(",")]
    )

    tags_list = [t.strip() for t in args.tags.split(",") if t.strip()]

    logger.info(f"Initiating cross-platform dispatch for: '{args.title}'")
    logger.info(f"Target platforms: {', '.join(target_platforms)}")
    logger.info(f"Dry run mode: {args.dry_run}")

    receipt = publisher.publish_video(
        video_path=args.video,
        title=args.title,
        description=args.description,
        tags=tags_list,
        thumbnail_path=args.thumbnail,
        platforms=target_platforms,
        stagger_minutes=args.stagger,
        dry_run=args.dry_run,
    )

    print("\n========================================================")
    print("             CROSS-PLATFORM DISPATCH RECEIPT            ")
    print("========================================================")
    print(f"Title: {receipt['title']}")
    print(f"Video: {receipt['video_path']}")
    print(f"Total Dispatched: {receipt['total_dispatched']} | Succeeded/Staged: {receipt['total_success']}")
    print("--------------------------------------------------------")
    for plat, p_res in receipt["platforms"].items():
        ok = p_res.get("success", False)
        status_str = "SUCCESS" if ok else "FAILED"
        url = p_res.get("url", "N/A")
        mode = p_res.get("mode", "N/A")
        print(f" [{plat.upper()}] {status_str} (Mode: {mode}) -> {url}")
    print("========================================================\n")


if __name__ == "__main__":
    main()

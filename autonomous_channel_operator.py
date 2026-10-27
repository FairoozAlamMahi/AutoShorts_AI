"""Autonomous Channel Operator CLI & Daemon Runner.
Executes end-to-end viral highlight extraction, playbook optimization,
and automated YouTube scheduling from the command line or background automation.
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_toolkit import AgentToolkit


def main():
    parser = argparse.ArgumentParser(description="Autonomous YouTube Shorts Channel Operator")
    parser.add_argument("source", type=str, help="YouTube video URL or local file path to process")
    parser.add_argument("--count", type=int, default=3, help="Target number of Shorts to produce (default: 3)")
    parser.add_argument("--game", type=str, default=None, help="Game context name (e.g. 'Valorant', 'GTA 6')")
    parser.add_argument(
        "--publish",
        type=str,
        choices=["OFF", "DRAFT_UPLOAD", "SCHEDULE_STAGGERED"],
        default="SCHEDULE_STAGGERED",
        help="Publishing mode: SCHEDULE_STAGGERED (uploads & staggers 6h apart), DRAFT_UPLOAD (private), or OFF (render only)",
    )
    parser.add_argument("--rules", type=str, default=None, help="Optional per-clip rules (e.g. '2B, 3 with 4:3')")
    args = parser.parse_args()

    print("=" * 70)
    print("  AutoShorts AI — Autonomous Channel Operator")
    print("=" * 70)
    print(f"Source:         {args.source}")
    print(f"Target Count:   {args.count} clips")
    print(f"Game Context:   {args.game or 'Auto-detect'}")
    print(f"Publish Mode:   {args.publish}")
    print("=" * 70)

    toolkit = AgentToolkit(project_root=PROJECT_ROOT)

    briefing = toolkit.get_channel_performance_briefing()
    recs = briefing.get("recommendations", {})
    print(f"\n[PLAYBOOK] Total Analyzed Clips: {briefing.get('total_analyzed_clips', 0)}")
    print(f"[PLAYBOOK] Winning Layout:       {recs.get('recommended_layout')}")
    print(f"[PLAYBOOK] Winning Caption:      {recs.get('recommended_theme')}")
    print(f"[PLAYBOOK] Sweet Spot Duration:  {recs.get('recommended_min_duration_sec')}s - {recs.get('recommended_max_duration_sec')}s\n")

    print("[PIPELINE] Launching autonomous generation run...")
    result = toolkit.run_autonomous_campaign(
        source_url_or_path=args.source,
        target_count=args.count,
        publish_mode=args.publish,
        game_name=args.game,
        per_clip_rules=args.rules,
    )

    print("\n" + "=" * 70)
    print(f"  CAMPAIGN COMPLETED: Job ID {result.get('job_id')}")
    print(f"  Clips Rendered:     {result.get('total_clips_generated')}")
    for p in result.get("rendered_clips", []):
        print(f"    - {p}")

    uploads = result.get("uploads", [])
    if uploads:
        print("\n  YOUTUBE PUBLISHING STATUS:")
        for u in uploads:
            status = "Uploaded" if u.get("success") else "Failed"
            url = u.get("url", "N/A")
            print(f"    - [{status}] {url}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

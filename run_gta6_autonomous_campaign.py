"""Autonomous Campaign Runner for GTA 6.
Generates 4 vertical Shorts with heterogeneous presets/layouts,
uploads 1 immediately (public), and schedules 3 staggered later today before end of day.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

# Ensure shorts_factory is on python path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_toolkit import AgentToolkit
from src.config.schema import (
    AudioProcessMode,
    CaptionMode,
    CaptionTheme,
    DiscoveryMode,
    LayoutMode,
    MetadataMode,
    OwnershipType,
    PreRunToggles,
    RightsStatus,
)
from src.core.dto import JobRequestDTO, YouTubeMetadataDTO
from src.core.quota_guard import QuotaGuard
from src.core.youtube_uploader import YouTubeUploader


def main() -> None:
    print("=" * 80)
    print("  AUTOSHORTS AI — GTA 6 AUTONOMOUS 4-PACK CAMPAIGN")
    print("=" * 80)

    toolkit = AgentToolkit(project_root=PROJECT_ROOT)
    data_dir = PROJECT_ROOT / "data"
    scratch_dir = data_dir / "scratch"
    exports_dir = data_dir / "exports"

    source_video_path = scratch_dir / "job_gta6_1080p_3c7dba" / "source_video.mp4"
    if not source_video_path.exists():
        raise FileNotFoundError(f"GTA 6 source video not found at: {source_video_path}")

    print(f"[INGEST] Using verified source video: {source_video_path}")
    print(f"[INGEST] File Size: {source_video_path.stat().st_size / (1024*1024):.2f} MB")

    # 1. Job Setup & Cache Pre-seeding
    job_id = "job_gta6_auto4_exec"
    job_scratch = scratch_dir / job_id
    job_scratch.mkdir(parents=True, exist_ok=True)

    cached_source_scratch = scratch_dir / "job_gta6_1080p_3c7dba"
    for cache_fname in ["audio_16k.wav", "audio_signals.wav", "transcript.json", "signals_cache.json"]:
        src_cache = cached_source_scratch / cache_fname
        dst_cache = job_scratch / cache_fname
        if src_cache.exists() and not dst_cache.exists():
            print(f"[CACHE] Pre-seeding {cache_fname} ({src_cache.stat().st_size} bytes)")
            shutil.copy2(src_cache, dst_cache)

    # 2. Configure 4 Heterogeneous Presets
    # Clip 1: LAYOUT_HYBRID_CINEMA_STACK + NEON_CYBER_GREEN (Clutch / Cinema Stack)
    # Clip 2: LAYOUT_B_CENTER_CROP + MRBEAST_YELLOW (High-impact Action Crop)
    # Clip 3: LAYOUT_4_3_BLUR_FIT + TIKTOK_RED_BOX (Cinematic Blur-Fit)
    # Clip 4: LAYOUT_B_CENTER_CROP + CLEAN_WHITE (Minimalist Action Crop)
    rules = (
        "1: LAYOUT_HYBRID_CINEMA_STACK, NEON_CYBER_GREEN; "
        "2: LAYOUT_B_CENTER_CROP, MRBEAST_YELLOW; "
        "3: LAYOUT_4_3_BLUR_FIT, TIKTOK_RED_BOX; "
        "4: LAYOUT_B_CENTER_CROP, CLEAN_WHITE"
    )

    toggles = PreRunToggles(
        discovery_mode=DiscoveryMode.FULL_AUTO,
        captions_mode=CaptionMode.BURNED_IN_ANIMATED,
        layout_mode=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK,
        caption_theme=CaptionTheme.MRBEAST_YELLOW,
        metadata_mode=MetadataMode.LOCAL_VLM,
        audio_process_mode=AudioProcessMode.LOUDNORM_EBU_R128,
        transcription_enabled=True,
        use_speech_scoring=True,
        vlm_verification_enabled=False,
        target_clip_count=4,
        ownership_type=OwnershipType.YOUTUBE_THIRD_PARTY,
        rights_status=RightsStatus.ORIGINAL_RECORDING,
        game_name_context="GTA 6",
        min_duration_sec=30.0,
        max_duration_sec=55.0,
        smart_layout_distribution=True,
        per_clip_rules=rules,
    )

    req = JobRequestDTO(
        job_id=job_id,
        source_path_or_url=str(source_video_path.resolve()),
        toggles=toggles,
        created_at_iso=datetime.now(timezone.utc).isoformat(),
    )

    print("\n[PIPELINE] Launching video generation with orchestrator...")
    print(f"  Job ID:          {job_id}")
    print(f"  Target Count:    4 clips")
    print(f"  Per-Clip Rules:  {rules}")

    def progress_callback(stage: str, pct: float) -> None:
        print(f"  [{pct:5.1f}%] {stage}")

    rendered_files = toolkit.orchestrator.run_job(req, progress_callback=progress_callback)
    print(f"\n[PIPELINE] Generation finished! Rendered {len(rendered_files)} vertical Shorts:")
    for rf in rendered_files:
        print(f"  - {rf}")

    # 3. Read Clip Metadata and Provenance
    clips_info: List[Dict[str, Any]] = []
    job_exports = exports_dir / job_id

    for rf in rendered_files:
        p = Path(rf)
        meta_p = p.with_suffix(".meta.json")
        prov_p = p.with_suffix(".provenance.json")

        meta_data: Dict[str, Any] = {}
        prov_data: Dict[str, Any] = {}

        if meta_p.exists():
            try:
                meta_data = json.loads(meta_p.read_text(encoding="utf-8"))
            except Exception:
                pass

        if prov_p.exists():
            try:
                prov_data = json.loads(prov_p.read_text(encoding="utf-8"))
            except Exception:
                pass

        title = meta_data.get("primary_title") or f"GTA 6 Highlight #{p.stem}"
        desc = meta_data.get("small_description") or "Insane GTA 6 gameplay moment! Subscribe for more daily gaming shorts."
        tags = meta_data.get("tags") or ["#gta6", "#gaming", "#shorts", "#viral"]

        # Ensure #Shorts tag is present
        if "#Shorts" not in title and "#shorts" not in title:
            if len(title) <= 90:
                title = f"{title} #Shorts"

        snap = prov_data.get("toggles_snapshot", {})
        clips_info.append({
            "path": p,
            "title": title,
            "description": desc,
            "tags": tags,
            "layout": snap.get("layout_mode", "UNKNOWN"),
            "theme": snap.get("caption_theme", "UNKNOWN"),
            "scene_category": snap.get("scene_category", "UNKNOWN"),
            "hook_score": snap.get("hook_score", 0),
            "hook_overlay": snap.get("hook_overlay") or snap.get("hook_overlay_text", ""),
            "duration": round(prov_data.get("end_sec", 0.0) - prov_data.get("start_sec", 0.0), 2),
        })

    # 4. Check Authentication and Quota Guard
    uploader = toolkit.uploader
    is_auth = uploader.is_authenticated()
    quota_guard = QuotaGuard(quota_path=data_dir / "daily_upload_quota.json", max_daily_uploads=4)
    can_upload, quota_msg = quota_guard.can_upload(len(clips_info))

    print("\n" + "=" * 80)
    print("  YOUTUBE PUBLISHING & SCHEDULING")
    print("=" * 80)
    print(f"Authenticated:   {is_auth}")
    print(f"Quota Status:    {quota_msg}")

    # Staggered Schedule for today:
    # Local Time is Asia/Dhaka (UTC+6). Current time is ~07:00 AM local (01:00 UTC).
    # End of the day is 23:59:59 (11:59 PM).
    # Clip 1: Immediate live upload (public)
    # Clip 2: 12:00 PM local (06:00 UTC) -> 5h from now
    # Clip 3: 05:00 PM local (11:00 UTC) -> 10h from now
    # Clip 4: 09:30 PM local (15:30 UTC) -> 14.5h from now (today before end of day)
    schedule_times = [
        None,                        # Clip 1: Upload now (public)
        "2026-10-27T06:00:00Z",      # Clip 2: Noon today (scheduled private)
        "2026-10-27T11:00:00Z",      # Clip 3: Afternoon today (scheduled private)
        "2026-10-27T15:30:00Z",      # Clip 4: Tonight before end of day (scheduled private)
    ]

    upload_results: List[Dict[str, Any]] = []
    successful_uploads = 0

    for idx, cinfo in enumerate(clips_info):
        sched_time = schedule_times[idx] if idx < len(schedule_times) else None
        is_immediate = (idx == 0)
        privacy = "public" if is_immediate else "private"

        print(f"\n[PUBLISH] Processing Clip {idx + 1}/4:")
        print(f"  File:       {cinfo['path'].name}")
        print(f"  Title:      {cinfo['title']}")
        print(f"  Layout:     {cinfo['layout']}")
        print(f"  Theme:      {cinfo['theme']}")
        print(f"  Hook Score: {cinfo['hook_score']} / 100")
        if cinfo['hook_overlay']:
            print(f"  Hook Text:  \"{cinfo['hook_overlay']}\"")
        print(f"  Privacy:    {privacy}")
        print(f"  Schedule:   {sched_time if sched_time else 'IMMEDIATE LIVE'}")

        res = uploader.upload_short(
            video_path=cinfo["path"],
            title=cinfo["title"],
            description=cinfo["description"],
            tags=cinfo["tags"],
            privacy_status=privacy,
            publish_at_iso=sched_time,
        )

        upload_results.append({
            "clip_index": idx + 1,
            "path": str(cinfo["path"]),
            "title": cinfo["title"],
            "layout": cinfo["layout"],
            "theme": cinfo["theme"],
            "duration": cinfo["duration"],
            "hook_score": cinfo["hook_score"],
            "hook_overlay": cinfo["hook_overlay"],
            "privacy": privacy,
            "scheduled_time_iso": sched_time,
            "upload_result": res,
        })

        if res.get("success"):
            successful_uploads += 1
            print(f"  -> SUCCESS! Video ID: {res.get('video_id')}")
            print(f"  -> URL: {res.get('url')}")
        else:
            print(f"  -> FAILED: {res.get('error', 'Unknown error')}")

    # Record uploads with QuotaGuard
    if successful_uploads > 0:
        quota_guard.record_upload(count=successful_uploads, video_title="GTA 6 Autonomous 4-Pack")

    # 5. Save Final Campaign Artifact
    campaign_summary = {
        "job_id": job_id,
        "completed_at_iso": datetime.now(timezone.utc).isoformat(),
        "source_video": str(source_video_path.name),
        "total_clips_generated": len(rendered_files),
        "total_uploads_executed": successful_uploads,
        "quota_status_after": quota_guard.get_status(),
        "clips": upload_results,
    }

    summary_file = data_dir / "gta6_campaign_summary.json"
    summary_file.write_text(json.dumps(campaign_summary, indent=2), encoding="utf-8")
    print(f"\n[REPORT] Saved campaign report to: {summary_file}")

    print("\n" + "=" * 80)
    print("  AUTONOMOUS CAMPAIGN SUMMARY")
    print("=" * 80)
    for c in upload_results:
        idx = c["clip_index"]
        res = c["upload_result"]
        sched = c["scheduled_time_iso"] or "Live Now"
        print(f"Clip {idx}: [{c['layout']} | {c['theme']}] - {c['duration']}s - Hook: {c['hook_score']}/100")
        print(f"        Title: {c['title']}")
        print(f"        Status: {c['privacy'].upper()} ({sched})")
        print(f"        URL: {res.get('url', 'N/A')}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

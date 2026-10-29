"""
Generates 7 viral Phantom Blade Zero Shorts from HYsuUyMg8gQ:
- 3 Funny / Deadpan / Creepy dialogue moments
- 4 High-Intensity Combat / Boss Climax moments
- Audio: Broadcast-clean native dialogue & visceral sword clash sound (no forced BGM, as user requested)
- Subtitles: Animated Kinetic Pop subtitles for all spoken dialogue
- Layout: 4:3 Blur Fit (1080x1920) perfectly framing the 16:9 gameplay in the center with blurred ambient top/bottom
- Thumbnails: High-CTR multi-candidate packaging (thumb_A, thumb_B, thumb_C, thumb.jpg, thumbnails.json)
- Uploads & Schedules 5 of the shorts on YouTube across the next 6 hours (private with publishAt).
"""
import json
import logging
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from shorts_factory.src.rendering.ffmpeg_renderer import FFmpegRenderer, LayoutMode, AudioProcessMode
from shorts_factory.src.rendering.thumbnail_maker import BadgeStyle
from shorts_factory.src.captions.ass_compiler import ASSCompiler, CaptionTheme, CaptionMode
from shorts_factory.src.captions.phrase_chunker import PhraseChunker
from shorts_factory.src.core.dto import TranscriptDTO, TranscriptWordDTO, TranscriptSegmentDTO
from shorts_factory.src.core.youtube_uploader import YouTubeUploader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SevenShortsProduction")

SOURCE_VIDEO = Path("shorts_factory/data/sources/HYsuUyMg8gQ.mp4").resolve()
TRANSCRIPT_JSON = Path("shorts_factory/data/scratch/HYsuUyMg8gQ_transcript.json").resolve()
EXPORT_DIR = Path("shorts_factory/data/exports/pbz_7_shorts").resolve()
OUTPUT_DIR = Path("OUTPUT_VIDEOS").resolve()
SCRATCH_DIR = Path("shorts_factory/data/scratch/pbz_7_shorts").resolve()

EXPORT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def load_transcript_words():
    if not TRANSCRIPT_JSON.exists():
        return []
    with open(TRANSCRIPT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    words = []
    for s in data.get("segments", []):
        for w in s.get("words", []):
            words.append({
                "word": w["w"].strip(),
                "start": float(w["s"]),
                "end": float(w["e"]),
            })
    return words


def build_clip_transcript(clip_start: float, clip_dur: float, all_words):
    clip_end = clip_start + clip_dur
    matched = [
        w for w in all_words
        if w["start"] >= clip_start - 0.5 and w["end"] <= clip_end + 0.5
    ]
    if not matched:
        return None

    tr_words = []
    for w in matched:
        rel_start = max(0.0, w["start"] - clip_start)
        rel_end = min(clip_dur, w["end"] - clip_start)
        if rel_end > rel_start:
            tr_words.append(TranscriptWordDTO(
                word=w["word"],
                start_sec=round(rel_start, 2),
                end_sec=round(rel_end, 2),
                confidence=1.0,
            ))

    if not tr_words:
        return None

    full_text = " ".join(tw.word for tw in tr_words)
    seg = TranscriptSegmentDTO(
        id=0,
        start_sec=tr_words[0].start_sec,
        end_sec=tr_words[-1].end_sec,
        text=full_text,
        words=tr_words,
    )
    return TranscriptDTO(segments=[seg], language="en")


SHORTS_SPEC = [
    # -------------------------------------------------------------------------
    # 1. FUNNY / DEADPAN BANTER: "The Ethereal Swordsman was a total fraud"
    # -------------------------------------------------------------------------
    {
        "id": "pbz_01_hopeless_fraud",
        "title": "The Ethereal Swordsman Was A Total Fraud",
        "description": "He called himself the Ethereal Swordsman... Just a fraud, really! #PhantomBladeZero #PBZ #Gaming #Shorts",
        "start_sec": 4554.0,
        "duration_sec": 26.0,
        "theme": CaptionTheme.TIKTOK_RED_BOX,
        "thumb_text": "TOTAL FRAUD",
        "badge_style": BadgeStyle.MRBEAST_YELLOW,
        "tags": ["PhantomBladeZero", "PBZ", "Gaming", "FunnyMoments", "Soulslike", "PS5Pro"],
        "upload_to_channel": True,
        "schedule_delay_hours": 1.0,  # ~1h from now
        "reason": "Hilarious deadpan conversation exposing the fraudulent swordsman",
    },
    # -------------------------------------------------------------------------
    # 2. FUNNY / ROASTING: "Blacksmith Roasts Everyone in Phantom Blade"
    # -------------------------------------------------------------------------
    {
        "id": "pbz_02_thick_headed_fools",
        "title": "Blacksmith Roasts Everyone in Phantom Blade",
        "description": "Not like those thick-headed fools who only know how to fight! #PhantomBladeZero #PBZ #GamingRoast #Shorts",
        "start_sec": 3895.0,
        "duration_sec": 25.0,
        "theme": CaptionTheme.MRBEAST_YELLOW,
        "thumb_text": "THICK HEADED FOOLS",
        "badge_style": BadgeStyle.FLOATING_IMPACT,
        "tags": ["PhantomBladeZero", "PBZ", "Gaming", "GamingRoast", "Shorts", "PS5Pro"],
        "upload_to_channel": True,
        "schedule_delay_hours": 2.25,  # ~2h 15m from now
        "reason": "Witty artisan Forge roasting all martial artists who only know how to fight",
    },
    # -------------------------------------------------------------------------
    # 3. CREEPY / BIZARRE: "The Creepiest Town in Phantom Blade Zero"
    # -------------------------------------------------------------------------
    {
        "id": "pbz_03_drooling_puppets",
        "title": "The Creepiest Town in Phantom Blade Zero",
        "description": "Eyes wide open, drooling... Dancing wooden puppets! #PhantomBladeZero #PBZ #HorrorGaming #Shorts",
        "start_sec": 855.0,
        "duration_sec": 26.0,
        "theme": CaptionTheme.NEON_CYBER_GREEN,
        "thumb_text": "PUPPET PLAGUE",
        "badge_style": BadgeStyle.CYBER_CYAN,
        "tags": ["PhantomBladeZero", "PBZ", "HorrorGaming", "Creepy", "Shorts", "PS5Pro"],
        "upload_to_channel": True,
        "schedule_delay_hours": 3.5,  # ~3h 30m from now
        "reason": "Atmospheric, eerie description of the drooling puppet plague",
    },
    # -------------------------------------------------------------------------
    # 4. INTENSE COMBAT: "Insane Deflection Timing on Bridge Boss"
    # -------------------------------------------------------------------------
    {
        "id": "pbz_04_bridge_deflect_master",
        "title": "Insane Deflection Timing on Bridge Boss in PBZ",
        "description": "Show me how fast you can strike! 5-hit deflect combo timing. #PhantomBladeZero #PBZ #Parry #Shorts",
        "start_sec": 226.0,
        "duration_sec": 26.0,
        "theme": CaptionTheme.ELECTRIC_BLUE,
        "thumb_text": "PERFECT DEFLECT",
        "badge_style": BadgeStyle.CYBER_CYAN,
        "tags": ["PhantomBladeZero", "PBZ", "Parry", "BossFight", "GamingShorts", "PS5Pro"],
        "upload_to_channel": True,
        "schedule_delay_hours": 4.75,  # ~4h 45m from now
        "reason": "5-hit rapid sword parry combo on the suspension bridge with flying sparks",
    },
    # -------------------------------------------------------------------------
    # 5. MAX INTENSITY CLIMAX: "Most Brutal Execution in Phantom Blade Zero"
    # -------------------------------------------------------------------------
    {
        "id": "pbz_05_finishing_execution",
        "title": "Most Brutal Execution in Phantom Blade Zero",
        "description": "I have nothing left to say! High-energy fatal execution counter. #PhantomBladeZero #PBZ #Execution #Shorts",
        "start_sec": 720.0,
        "duration_sec": 26.0,
        "theme": CaptionTheme.TIKTOK_RED_BOX,
        "thumb_text": "BRUTAL FINISH",
        "badge_style": BadgeStyle.NEON_RED,
        "tags": ["PhantomBladeZero", "PBZ", "Execution", "BossFight", "GamingShorts", "PS5Pro"],
        "upload_to_channel": True,
        "schedule_delay_hours": 5.75,  # ~5h 45m from now
        "reason": "Highest audio energy spike (0.2654 RMS) lethal counter and boss finish",
    },
    # -------------------------------------------------------------------------
    # 6. INTENSE BOSS BATTLE: "Chained Boss Breaks Free in Phantom Blade Zero"
    # -------------------------------------------------------------------------
    {
        "id": "pbz_06_chained_executioner",
        "title": "Chained Boss Breaks Free in Phantom Blade Zero",
        "description": "Those restraints won't hold for long! Colossal brute breaks out. #PhantomBladeZero #PBZ #BossFight #Shorts",
        "start_sec": 3604.0,
        "duration_sec": 26.0,
        "theme": CaptionTheme.TIKTOK_RED_BOX,
        "thumb_text": "CHAINS BROKE",
        "badge_style": BadgeStyle.NEON_RED,
        "tags": ["PhantomBladeZero", "PBZ", "BossBattle", "Gaming", "PS5Pro", "Shorts"],
        "upload_to_channel": False,  # Showcase archive
        "schedule_delay_hours": None,
        "reason": "Giant chained mask walker smashing arena chains and charging the player",
    },
    # -------------------------------------------------------------------------
    # 7. HIGH-SPEED COMBAT: "Peak Combat Flow in Phantom Blade Zero"
    # -------------------------------------------------------------------------
    {
        "id": "pbz_07_shadow_blood_counter",
        "title": "Peak Combat Flow in Phantom Blade Zero",
        "description": "Lightning-fast dodge cancels and crimson blade slash trails. #PhantomBladeZero #PBZ #Combat #Shorts",
        "start_sec": 1818.0,
        "duration_sec": 26.0,
        "theme": CaptionTheme.ELECTRIC_BLUE,
        "thumb_text": "PEAK COMBAT FLOW",
        "badge_style": BadgeStyle.MRBEAST_YELLOW,
        "tags": ["PhantomBladeZero", "PBZ", "CombatCombos", "ActionGaming", "PS5Pro", "Shorts"],
        "upload_to_channel": False,  # Showcase archive
        "schedule_delay_hours": None,
        "reason": "High-octane multi-slash juggle and crimson sword trail parries",
    },
]


def run_production():
    logger.info("Starting 7-Shorts Production Pipeline for Phantom Blade Zero...")
    all_words = load_transcript_words()
    logger.info(f"Loaded {len(all_words)} aligned transcript words.")

    renderer = FFmpegRenderer()
    uploader = YouTubeUploader()

    # Time reference for scheduling
    now_utc = datetime.now(timezone.utc)
    logger.info(f"Current UTC time: {now_utc.isoformat()}")

    manifest = []
    upload_count = 0

    for idx, spec in enumerate(SHORTS_SPEC, 1):
        vid_id = spec["id"]
        logger.info(f"\n========================================================")
        logger.info(f"[{idx}/7] Producing Short: {vid_id}")
        logger.info(f"Scene Window: {spec['start_sec']}s ({spec['duration_sec']}s) | Type: {spec['reason']}")

        # 1. Compile Subtitles if dialogue exists
        ass_path = None
        clip_transcript = build_clip_transcript(spec["start_sec"], spec["duration_sec"], all_words)
        if clip_transcript and clip_transcript.segments:
            ass_path = SCRATCH_DIR / f"{vid_id}.ass"
            chunks = PhraseChunker.chunk_animated_pop(clip_transcript, words_per_block=2)
            ASSCompiler.compile_ass(
                chunks=chunks,
                mode=CaptionMode.BURNED_IN_ANIMATED,
                output_path=ass_path,
                theme=spec["theme"],
            )
            logger.info(f"Compiled animated kinetic subtitles -> {ass_path.name}")
        else:
            logger.info("No spoken dialogue in window; rendering pure visual action.")

        # 2. Render 1080x1920 Short with Broadcast EBU R128 Loudnorm (No extra BGM)
        out_mp4 = EXPORT_DIR / f"{vid_id}.mp4"
        t0 = time.time()
        renderer.render_clip(
            source_video=SOURCE_VIDEO,
            output_mp4=out_mp4,
            start_sec=spec["start_sec"],
            duration_sec=spec["duration_sec"],
            layout_mode=LayoutMode.LAYOUT_4_3_BLUR_FIT,
            ass_path=ass_path,
            audio_mode=AudioProcessMode.LOUDNORM_EBU_R128,
            prefer_nvenc=True,
        )
        dur_render = time.time() - t0
        mb_size = out_mp4.stat().st_size / (1024 * 1024)
        logger.info(f"Rendered in {dur_render:.2f}s -> {out_mp4.name} ({mb_size:.2f} MB)")

        # 3. Generate High-CTR Multi-Candidate Thumbnails
        thumbs = renderer.generate_multi_thumbnails(
            video_path=out_mp4,
            output_dir=EXPORT_DIR,
            duration_sec=spec["duration_sec"],
            hook_overlay_text=spec["thumb_text"],
            source_video=SOURCE_VIDEO,
            start_sec=spec["start_sec"],
            badge_style=spec["badge_style"],
        )
        logger.info(f"Generated A/B/C Thumbnails via yt-package suite: A={thumbs['A'].name}, B={thumbs['B'].name}, C={thumbs['C'].name}")

        # 4. Copy to Root OUTPUT_VIDEOS directory
        root_mp4 = OUTPUT_DIR / out_mp4.name
        shutil.copyfile(out_mp4, root_mp4)
        for t_key in ["A", "B", "C", "main"]:
            src_t = thumbs.get(t_key)
            if src_t and src_t.exists():
                shutil.copyfile(src_t, OUTPUT_DIR / src_t.name)
        if thumbs.get("meta") and thumbs["meta"].exists():
            shutil.copyfile(thumbs["meta"], OUTPUT_DIR / thumbs["meta"].name)

        # 5. YouTube Upload & Scheduling (for 5 selected videos)
        upload_result = None
        scheduled_iso = None
        if spec.get("upload_to_channel"):
            delay_h = spec["schedule_delay_hours"]
            sched_time = now_utc + timedelta(hours=delay_h)
            scheduled_iso = sched_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info(f"Scheduling Short for upload to YouTube channel: publishAt={scheduled_iso}")

            try:
                upload_result = uploader.upload_short(
                    video_path=out_mp4,
                    title=spec["title"],
                    description=spec["description"],
                    tags=spec["tags"],
                    privacy_status="private",
                    publish_at_iso=scheduled_iso,
                    auto_comment_text=f"What was your favorite moment in Phantom Blade Zero? Subscribe for more daily boss guides!",
                )
                upload_count += 1
                logger.info(f"Upload success! Video ID: {upload_result.get('video_id')} | URL: {upload_result.get('url')}")
            except Exception as e:
                logger.error(f"YouTube upload failed: {e}")
                upload_result = {"success": False, "error": str(e)}

        manifest.append({
            "id": vid_id,
            "title": spec["title"],
            "type": spec["reason"],
            "start_sec": spec["start_sec"],
            "duration_sec": spec["duration_sec"],
            "video_path": str(root_mp4),
            "thumb_A": str(OUTPUT_DIR / f"{vid_id}.thumb_A.jpg"),
            "thumb_B": str(OUTPUT_DIR / f"{vid_id}.thumb_B.jpg"),
            "thumb_C": str(OUTPUT_DIR / f"{vid_id}.thumb_C.jpg"),
            "uploaded": bool(upload_result and upload_result.get("success")),
            "youtube_url": upload_result.get("url") if upload_result else None,
            "youtube_id": upload_result.get("video_id") if upload_result else None,
            "scheduled_publish_utc": scheduled_iso,
        })

    # Save manifest
    (OUTPUT_DIR / "scheduled_7_shorts_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (EXPORT_DIR / "scheduled_7_shorts_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    logger.info("\n========================================================")
    logger.info(f"COMPLETED ALL 7 SHORTS! Uploaded & Scheduled: {upload_count}/5")
    logger.info(f"Manifest: {OUTPUT_DIR / 'scheduled_7_shorts_manifest.json'}")
    logger.info("========================================================")


if __name__ == "__main__":
    run_production()

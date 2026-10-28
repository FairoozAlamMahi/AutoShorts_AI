"""
Generates 4 true-to-content Viral V3 Shorts:
- 2 for Phantom Blade Zero (Real Boss Battles: Bridge Duel 240s & Fire Samurai Climax 3120s)
- 2 for Grand Theft Auto (Real Driving: Supercar Street Drift 468s & Highway Police Chase 1134s)
- 4 distinct real viral phonk tracks with automated BPM and beat drop syncing
- Hard Studio Ducking (-24 dB game audio during VO, +4.3 dB voice boost)
- 1.15x Hook Punch-In Zoom
- Sub-bass boom on the beat drop
- 21-formula scored hooks & mobile-safe title/thumbnail linting
- Multi-candidate thumbnails (thumb_A, B, C)
"""
import json
import logging
import shutil
import time
from pathlib import Path

from shorts_factory.src.rendering.ffmpeg_renderer import FFmpegRenderer, LayoutMode, AudioProcessMode
from shorts_factory.src.editing.action_assembler import ActionAssembler, ActionBeat, AssemblyMode
from shorts_factory.src.audio.viral_audio_bank import viral_audio_bank
from shorts_factory.src.audio.sfx_generator import sfx_engine
from shorts_factory.src.voice.voice_agent import VoiceSynthesisAgent, VoicePersona
from shorts_factory.src.captions.ass_compiler import ASSCompiler, CaptionTheme, CaptionMode
from shorts_factory.src.captions.phrase_chunker import PhraseChunker
from shorts_factory.src.core.dto import TranscriptDTO, TranscriptWordDTO, TranscriptSegmentDTO
from shorts_factory.src.skills.youtube_agent_bridge import youtube_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ViralV3Showcase")

EXPORT_DIR = Path("shorts_factory/data/exports/viral_showcase_v3").resolve()
STAGING_DIR = Path("shorts_factory/data/staging").resolve()
SCRATCH_DIR = Path("shorts_factory/data/scratch/v3_synthesis").resolve()
OUTPUT_DIR = Path("OUTPUT_VIDEOS").resolve()
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
STAGING_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GTA_SRC = Path("shorts_factory/data/scratch/job_gta6_1080p_3c7dba/source_video.mp4").resolve()
PBZ_SRC = Path("shorts_factory/data/sources/phantom_blade_zero.mp4").resolve()


def build_timed_transcript(spoken_text: str, total_duration_sec: float) -> TranscriptDTO:
    words = spoken_text.strip().split()
    if not words:
        return TranscriptDTO()
    dur_per_word = total_duration_sec / len(words)
    tr_words = [
        TranscriptWordDTO(
            word=w,
            start_sec=round(i * dur_per_word, 2),
            end_sec=round((i + 1) * dur_per_word, 2),
            confidence=1.0,
        )
        for i, w in enumerate(words)
    ]
    seg = TranscriptSegmentDTO(
        id=0,
        seek=0,
        start_sec=0.0,
        end_sec=round(total_duration_sec, 2),
        text=spoken_text,
        words=tr_words,
    )
    return TranscriptDTO(text=spoken_text, segments=[seg], language="en")


def run_v3_generation():
    logger.info("Initializing Viral V3 Production Engine...")
    renderer = FFmpegRenderer()
    assembler = ActionAssembler(renderer=renderer)
    voice_agent = VoiceSynthesisAgent()

    shorts_plan = [
        # ---------------------------------------------------------------------
        # 1. PBZ: BRIDGE BOSS DUEL (Real Boss Combat on Bridge vs Hua Qianxiao)
        # ---------------------------------------------------------------------
        {
            "id": "pbz_01_bridge_boss_duel",
            "game": "Phantom Blade Zero",
            "source": PBZ_SRC,
            "start_sec": 240.0,
            "duration_sec": 28.0,
            "layout": LayoutMode.LAYOUT_4_3_BLUR_FIT,
            "theme": CaptionTheme.NEON_CYBER_GREEN,
            "persona": VoicePersona.TIKTOK_HYPE_HOOK,
            "candidate_hooks": [
                "Watch how he perfectly deflects this 4-hit combo from the Sword Fanatic on the bridge!",
                "Stop fighting the Sword Fanatic on this bridge until you learn this deflection timing!",
                "This is the cleanest deflect combo against Hua Qianxiao on the bridge in PBZ!",
            ],
            "title_proposal": "Cleanest Deflect Combo on Bridge Boss in PBZ",
            "thumb_overlay": "PERFECT DEFLECT...",
            "track_id": "viral_phonk_dark_fantasy",
            "mode": "SINGLE_CLIMAX",
        },
        # ---------------------------------------------------------------------
        # 2. PBZ: LION DANCE GRANDMASTER (Real Arena Boss Climax)
        # ---------------------------------------------------------------------
        {
            "id": "pbz_02_lion_dance_climax",
            "game": "Phantom Blade Zero",
            "source": PBZ_SRC,
            "start_sec": 3120.0,
            "duration_sec": 28.0,
            "layout": LayoutMode.LAYOUT_A_BLUR_FIT,
            "theme": CaptionTheme.ELECTRIC_BLUE,
            "persona": VoicePersona.DRAMATIC_TRAILER_BASS,
            "candidate_hooks": [
                "Stop fighting The Lion Dance Grandmaster until you master this dodge cancel window!",
                "Nobody thought he could survive The Lion Dance Grandmaster... watch this final counter!",
                "This is the cleanest combat sequence against The Lion Dance Grandmaster in PBZ!",
            ],
            "title_proposal": "How to Beat The Lion Dance Grandmaster in PBZ",
            "thumb_overlay": "DODGE CANCEL...",
            "track_id": "viral_phonk_dark_gym_drift",
            "mode": "SINGLE_CLIMAX",
        },
        # ---------------------------------------------------------------------
        # 3. GTA: HIGHWAY SUNSET CRUISE (Real Miami Expressway Driving with Chopper)
        # ---------------------------------------------------------------------
        {
            "id": "gta_01_highway_sunset_cruise",
            "game": "Grand Theft Auto",
            "source": GTA_SRC,
            "start_sec": 760.0,
            "duration_sec": 28.0,
            "layout": LayoutMode.LAYOUT_4_3_BLUR_FIT,
            "theme": CaptionTheme.MRBEAST_YELLOW,
            "persona": VoicePersona.TIKTOK_HYPE_HOOK,
            "candidate_hooks": [
                "Driving down the Miami expressway at sunset in GTA 6 is pure cinema!",
                "Cruising the Vice City highway into the sunset with GTA 6 physics!",
                "Watch what happens when you cruise the Vice City highway with a chopper overhead in GTA 6!",
            ],
            "title_proposal": "Cruising the Highway at Sunset in GTA 6",
            "thumb_overlay": "PURE CINEMA...",
            "track_id": "viral_phonk_montagem_drift",
            "mode": "SINGLE_CLIMAX",
        },
        # ---------------------------------------------------------------------
        # 4. GTA: CONVENIENCE STORE ROBBERY (Real Store Stick-Up & Masked Getaway)
        # ---------------------------------------------------------------------
        {
            "id": "gta_02_convenience_store_robbery",
            "game": "Grand Theft Auto",
            "source": GTA_SRC,
            "start_sec": 709.0,
            "duration_sec": 28.0,
            "layout": LayoutMode.LAYOUT_A_BLUR_FIT,
            "theme": CaptionTheme.TIKTOK_RED_BOX,
            "persona": VoicePersona.DRAMATIC_TRAILER_BASS,
            "candidate_hooks": [
                "Watch how the store robbery mechanics and cashier AI work in GTA 6!",
                "This is the full store robbery and getaway sequence in GTA 6!",
                "Stop playing GTA until you see how intense the new robbery mechanics are in GTA 6!",
            ],
            "title_proposal": "Full Store Robbery and Getaway in GTA 6",
            "thumb_overlay": "INSANE AI...",
            "track_id": "viral_phonk_popular_mix",
            "mode": "SINGLE_CLIMAX",
        },
    ]

    manifest = []

    for idx, cfg in enumerate(shorts_plan, 1):
        vid_id = cfg["id"]
        logger.info(f"\n========================================================")
        logger.info(f"[{idx}/4] Producing Short: {vid_id} ({cfg['game']})")
        logger.info(f"Visual Scene: {cfg['start_sec']}s ({cfg['duration_sec']}s)")

        # 1. 21-Formula Hook Evaluation
        ranked = youtube_agent.rank_hooks(cfg["candidate_hooks"])
        winner = ranked[0]
        logger.info(f"Selected Hook: '{winner.hook}' (Score: {winner.verdict_score}/100, Formula: {winner.formula_name})")

        # 2. Packaging Linting
        lint = youtube_agent.lint_title_and_thumbnail(cfg["title_proposal"], cfg["thumb_overlay"])
        logger.info(f"Packaging Lint: Score {lint.score}/100 | Mobile Safe: {lint.mobile_safe}")

        # 3. GPU Neural Voice Synthesis
        voice_wav = SCRATCH_DIR / f"{vid_id}_voice.wav"
        t_syn = time.time()
        _, vo_dur = voice_agent.synthesize(
            text=winner.hook,
            output_path=voice_wav,
            persona=cfg["persona"],
            speed=1.05,
        )
        logger.info(f"Voice synthesized ({vo_dur:.2f}s) in {time.time() - t_syn:.2f}s -> {voice_wav.name}")

        # 4. Kinetic Subtitles
        ass_path = SCRATCH_DIR / f"{vid_id}.ass"
        transcript = build_timed_transcript(winner.hook, vo_dur)
        chunks = PhraseChunker.chunk_animated_pop(transcript, words_per_block=2)
        ASSCompiler.compile_ass(
            chunks=chunks,
            mode=CaptionMode.BURNED_IN_ANIMATED,
            output_path=ass_path,
            theme=cfg["theme"],
        )

        # 5. Viral Audio Track Lookup
        track = viral_audio_bank.get_track(cfg["track_id"])
        if not track:
            track = viral_audio_bank.get_best_match_for_game(cfg["game"])
        logger.info(f"Viral Music: '{track.title}' (BPM: {track.bpm}, Drop: {track.suggested_drop_sec}s)")

        # 6. Video Rendering
        out_mp4 = EXPORT_DIR / f"{vid_id}.mp4"
        t_rend = time.time()

        if cfg["mode"] == "MULTI_CUT":
            logger.info("Rendering Multi-Cut Montage on NVENC...")
            assembler.render_multi_cut_montage(
                source_video=cfg["source"],
                output_mp4=out_mp4,
                beats=cfg["beats"],
                layout_mode=cfg["layout"],
                ass_path=ass_path,
                bgm_path=track.file_path,
                voice_path=voice_wav,
                drop_timestamp_sec=track.suggested_drop_sec,
                scratch_dir=SCRATCH_DIR / f"work_{vid_id}",
            )
        else:
            logger.info("Rendering Single-Climax Flow on NVENC...")
            assembler.render_single_climax_flow(
                source_video=cfg["source"],
                output_mp4=out_mp4,
                start_sec=cfg["start_sec"],
                duration_sec=cfg["duration_sec"],
                layout_mode=cfg["layout"],
                ass_path=ass_path,
                bgm_path=track.file_path,
                voice_path=voice_wav,
                drop_timestamp_sec=track.suggested_drop_sec,
            )

        logger.info(f"Rendered in {time.time() - t_rend:.2f}s -> {out_mp4.name} ({out_mp4.stat().st_size / (1024*1024):.2f} MB)")

        # 7. Multi-Candidate Thumbnails (thumb_A, B, C)
        renderer.generate_multi_thumbnails(
            out_mp4,
            output_dir=EXPORT_DIR,
            duration_sec=cfg["duration_sec"],
            hook_overlay_text=cfg["thumb_overlay"],
        )

        # 8. Stage for Instant Web Review and Root Access
        shutil.copyfile(out_mp4, STAGING_DIR / out_mp4.name)
        shutil.copyfile(out_mp4, OUTPUT_DIR / out_mp4.name)
        thumb_main = EXPORT_DIR / f"{vid_id}.thumb.jpg"
        if thumb_main.exists():
            shutil.copyfile(thumb_main, STAGING_DIR / thumb_main.name)
            shutil.copyfile(thumb_main, OUTPUT_DIR / thumb_main.name)
        for t_opt in ["thumb_A.jpg", "thumb_B.jpg", "thumb_C.jpg"]:
            t_file = EXPORT_DIR / f"{vid_id}.{t_opt}"
            if t_file.exists():
                shutil.copyfile(t_file, OUTPUT_DIR / t_file.name)

        manifest.append({
            "id": vid_id,
            "game": cfg["game"],
            "title": lint.title,
            "mobile_safe": lint.mobile_safe,
            "hook_formula": winner.formula_name,
            "hook_score": winner.verdict_score,
            "spoken_hook": winner.hook,
            "voice_persona": cfg["persona"],
            "music_track": track.title,
            "music_bpm": track.bpm,
            "drop_sec": track.suggested_drop_sec,
            "scene_start_sec": cfg["start_sec"],
            "video_path": str(out_mp4),
            "thumbnail_path": str(thumb_main),
            "root_video_path": str(OUTPUT_DIR / out_mp4.name),
        })

    (EXPORT_DIR / "viral_v3_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "viral_v3_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("\n========================================================")
    logger.info("COMPLETED ALL 4 TRUE-TO-CONTENT VIRAL V3 SHORTS!")
    logger.info(f"Saved to: {EXPORT_DIR}")
    logger.info(f"Root outputs: {OUTPUT_DIR}")
    logger.info(f"Staged in: {STAGING_DIR}")
    logger.info(f"Manifest: {OUTPUT_DIR / 'viral_v3_manifest.json'}")
    logger.info("========================================================")


if __name__ == "__main__":
    run_v3_generation()

"""Autonomous High-Impact Viral Video Suite: 10 Distinct Music-Synced Edits.
Generates 10 vertical (1080x1920 @ 60 fps) Shorts/Reels/TikToks, each featuring a unique
editing archetype, rhythmic beat synchronization via Librosa, custom sound design,
and high-CTR YouTube packaging.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple

import librosa
import numpy as np
from PIL import Image

# Force UTF-8 encoding
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure shorts_factory in sys.path
PROJECT_ROOT = Path(__file__).parent / "shorts_factory"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shorts_factory.src.rendering.thumbnail_maker import ThumbnailMaker, BadgeStyle
tm = ThumbnailMaker()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ViralMusicSuite")

BASE_OUTPUT_DIR = Path("OUTPUT_VIDEOS/Viral_Music_Edits_10").resolve()
GTA_OUTPUT_DIR = Path("OUTPUT_VIDEOS/GTA/GTA 4").resolve()
PBZ_OUTPUT_DIR = Path("OUTPUT_VIDEOS/Phantom Blade 0/Phantom Blade 4").resolve()

SRC_GTA = Path("shorts_factory/data/scratch/job_gta6_1080p_3c7dba/source_video.mp4").resolve()
SRC_PBZ = Path("shorts_factory/data/sources/phantom_blade_zero.mp4").resolve()

SFX_RISER = Path("shorts_factory/assets/sfx/riser.wav").resolve()
SFX_IMPACT = Path("shorts_factory/assets/sfx/hit_impact.wav").resolve()
SFX_BOOM = Path("shorts_factory/assets/sfx/sub_boom.wav").resolve()
SFX_WHOOSH = Path("shorts_factory/assets/sfx/whoosh.wav").resolve()

BGM_MONTAGEM = Path("shorts_factory/assets/music/viral_bank/viral_phonk_montagem_drift.mp3").resolve()
BGM_GYM = Path("shorts_factory/assets/music/viral_bank/viral_phonk_dark_gym_drift.mp3").resolve()
BGM_FANTASY = Path("shorts_factory/assets/music/viral_bank/viral_phonk_dark_fantasy.mp3").resolve()
BGM_POPULAR = Path("shorts_factory/assets/music/viral_bank/viral_phonk_popular_mix.mp3").resolve()
BGM_PULSE = Path("shorts_factory/assets/music/viral_bank/procedural_phonk_pulse.wav").resolve()
BGM_ACTION = Path("shorts_factory/assets/music/action_pulse.mp3").resolve()
BGM_LOFI = Path("shorts_factory/assets/music/ambient_lofi.mp3").resolve()


def analyze_track_beats(bgm_path: Path, offset_sec: float, duration_sec: float) -> Tuple[float, List[float]]:
    """Uses Librosa to extract tempo and beat timestamps."""
    y, sr = librosa.load(str(bgm_path), sr=22050, offset=offset_sec, duration=duration_sec)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beats, sr=sr)
    tempo_val = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return tempo_val, [round(float(b), 3) for b in beat_times]


def write_ass_subtitles(
    ass_path: Path,
    hook_banner: str,
    dialogues: List[Tuple[float, float, str, str]], # (start, end, text, color_hex)
):
    """Compiles an ASS subtitle file with top teaser banner and kinetic subtitles."""
    events = [
        f"Dialogue: 0,0:00:00.00,0:00:02.50,HookBanner,,0,0,0,,{{\\fad(200,200)}}{hook_banner}"
    ]
    for start, end, text, col in dialogues:
        m_start = f"0:{int(start//60):02d}:{start%60:05.2f}"
        m_end = f"0:{int(end//60):02d}:{end%60:05.2f}"
        events.append(
            f"Dialogue: 0,{m_start},{m_end},PunchText,,0,0,0,,{{\\fad(80,120)\\b1\\c{col}}}{text}"
        )

    ass_text = f"""[Script Info]
Title: Viral Short Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HookBanner,Impact,64,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,4,2,8,40,40,240,1
Style: PunchText,Arial,78,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,5,3,2,60,60,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"

    ass_path.write_text(ass_text, encoding="utf-8")


def render_short_video(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Renders a single viral short with custom filtergraph and beat synchronization."""
    vid_id = cfg["id"]
    out_mp4 = BASE_OUTPUT_DIR / f"{vid_id}.mp4"
    ass_path = BASE_OUTPUT_DIR / f"{vid_id}.ass"

    logger.info(f"--- Rendering [{vid_id}]: {cfg['title']} ---")

    # Analyze beats
    tempo, beats = analyze_track_beats(cfg["bgm"], cfg["bgm_offset"], cfg["duration"])
    drop_ts = cfg["drop_ts"]
    logger.info(f"BGM: {cfg['bgm'].name} | Tempo: {tempo:.1f} BPM | Drop: {drop_ts:.2f}s | Beats in clip: {len(beats)}")

    # Write Subtitles
    write_ass_subtitles(ass_path, cfg["hook_banner"], cfg["subtitles"])
    ass_esc = str(ass_path).replace("\\", "/").replace(":", "\\:")

    # Build audio filtergraph
    sil_start = max(0.0, drop_ts - cfg.get("pre_drop_silence", 0.20))
    sil_end = drop_ts
    riser_delay = max(0, int((drop_ts - 1.5) * 1000))
    impact_delay = int(drop_ts * 1000)
    dur = cfg["duration"]

    af = (
        f"[0:a]atrim=0:{dur},asetpts=PTS-STARTPTS,volume=0.45[game_a];"
        f"[1:a]atrim=start={cfg['bgm_offset']}:duration={dur},asetpts=PTS-STARTPTS,"
        f"volume='if(between(t,{sil_start:.3f},{sil_end:.3f}),0,if(lt(t,{drop_ts:.3f}),0.25,1.0))':eval=frame,"
        f"lowpass=f=1000:enable='lt(t,{drop_ts:.3f})'[bgm_a];"
        f"[2:a]adelay={riser_delay}|{riser_delay},volume=0.7[riser_a];"
        f"[3:a]adelay={impact_delay}|{impact_delay},volume=0.9[impact_a];"
        f"[4:a]adelay={impact_delay}|{impact_delay},volume=1.0[boom_a];"
        f"[game_a][bgm_a][riser_a][impact_a][boom_a]amix=inputs=5:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.5:LRA=11[a_out]"
    )

    # Call custom video filtergraph generator
    vf = cfg["vf_builder"](cfg, ass_esc, drop_ts, beats)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(cfg["start_sec"]), "-i", str(cfg["source"]),
        "-i", str(cfg["bgm"]),
        "-i", str(SFX_RISER),
        "-i", str(SFX_IMPACT),
        "-i", str(SFX_BOOM),
        "-filter_complex", f"{vf};{af}",
        "-map", "[v_out]", "-map", "[a_out]",
        "-t", str(dur),
        "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "-r", "60",
        "-c:a", "aac", "-b:a", "192k",
        str(out_mp4)
    ]

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    t_cost = time.time() - t0

    if res.returncode != 0:
        logger.error(f"FFmpeg render failure on {vid_id}:\n{res.stderr[-1200:]}")
        raise RuntimeError(f"Render failed for {vid_id}")

    f_size_mb = out_mp4.stat().st_size / (1024 * 1024)
    logger.info(f"Rendered {vid_id}.mp4 in {t_cost:.2f}s ({f_size_mb:.2f} MB)")

    # Extract preview image
    preview_jpg = BASE_OUTPUT_DIR / f"{vid_id}_preview.jpg"
    thumb_sec = min(dur - 1.0, drop_ts + 0.3)
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(thumb_sec), "-i", str(out_mp4),
        "-vframes", "1", "-q:v", "2", str(preview_jpg)
    ], capture_output=True)

    # Generate high-CTR thumbnail cover with title badge
    thumb_cover = BASE_OUTPUT_DIR / f"{vid_id}_thumb.jpg"
    try:
        base_img = Image.open(preview_jpg)
        graded_img = tm.apply_color_grading(base_img)
        b_style = cfg.get("badge_style", BadgeStyle.MRBEAST_YELLOW)
        b_text = cfg.get("badge_text", "VIRAL EDIT")
        final_thumb = tm.render_badge(graded_img, b_text, style=b_style)
        final_thumb.save(thumb_cover, quality=95)
    except Exception as e:
        logger.warning(f"Thumbnail styling fallback on {vid_id}: {e}")
        shutil.copyfile(preview_jpg, thumb_cover)

    # Mirror to game folder
    target_game_dir = GTA_OUTPUT_DIR if "Grand Theft Auto" in cfg["game"] else PBZ_OUTPUT_DIR
    target_game_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out_mp4, target_game_dir / f"{vid_id}.mp4")
    shutil.copyfile(thumb_cover, target_game_dir / f"{vid_id}_thumb.jpg")

    return {
        "id": vid_id,
        "title": cfg["title"],
        "game": cfg["game"],
        "archetype": cfg["archetype"],
        "duration": dur,
        "tempo_bpm": tempo,
        "drop_ts": drop_ts,
        "file_size_mb": round(f_size_mb, 2),
        "output_path": str(out_mp4),
        "preview_path": str(preview_jpg),
        "render_sec": round(t_cost, 2),
    }


# =====================================================================
# FILTERGRAPH BUILDERS FOR 10 EDIT ARCHETYPES
# =====================================================================

def vf_velocity_ramp(cfg, ass_esc, drop_ts, beats):
    """Edit 1: Velocity Ramp Speed-Shift + White Flash Frame."""
    dur = cfg["duration"]
    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30[bg];"
        f"[fg_src]scale=1080:608[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]drawbox=t=fill:c=white@0.85:enable='between(t,{drop_ts:.3f},{drop_ts+0.08:.3f})'[flashed];"
        f"[flashed]crop=w='if(between(t,{drop_ts:.3f},{drop_ts+0.4:.3f}),in_w*0.88,in_w)':h='if(between(t,{drop_ts:.3f},{drop_ts+0.4:.3f}),in_h*0.88,in_h)',scale=1080:1920[zoomed];"
        f"[zoomed]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_hyper_zoom_parries(cfg, ass_esc, drop_ts, beats):
    """Edit 2: Rhythmic Optical Punch Zooms on Beat Clash Transients."""
    dur = cfg["duration"]
    punch_conditions = []
    for b in beats[:8]:
        if b > 0.5:
            punch_conditions.append(f"between(t,{b:.3f},{b+0.16:.3f})")
    cond_str = "+".join(punch_conditions) if punch_conditions else "0"

    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=35[bg];"
        f"[fg_src]scale=1080:1080[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]crop=w='if({cond_str},in_w*0.82,in_w)':h='if({cond_str},in_h*0.82,in_h)',scale=1080:1920[punched];"
        f"[punched]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_dark_fantasy_anamorphic(cfg, ass_esc, drop_ts, beats):
    """Edit 3: Dark Fantasy 2.39:1 Anamorphic Cinema Stack."""
    dur = cfg["duration"]
    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,"
        f"scale=1080:452,pad=1080:1920:0:734:black[letterbox];"
        f"[letterbox]eq=contrast=1.35:saturation=0.75:brightness=-0.03[noir];"
        f"[noir]drawbox=t=fill:c=white@0.4:enable='between(t,{drop_ts:.3f},{drop_ts+0.06:.3f})'[flashed];"
        f"[flashed]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_neuro_glitch_rgb_strobe(cfg, ass_esc, drop_ts, beats):
    """Edit 4: Flash-Frame Glitch & RGB Split Aberration."""
    dur = cfg["duration"]
    strobe_cond = "+".join([f"between(t,{b:.3f},{b+0.05:.3f})" for b in beats[2:10]]) if len(beats) > 2 else f"between(t,{drop_ts-0.5:.3f},{drop_ts-0.45:.3f})"

    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30[bg];"
        f"[fg_src]scale=1080:608[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]drawbox=t=fill:c=white@0.75:enable='{strobe_cond}'[strobed];"
        f"[strobed]rgbashift=rh=16:bv=-16:enable='between(t,{drop_ts:.3f},{drop_ts+0.55:.3f})'[glitched];"
        f"[glitched]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_aesthetic_lofi_blurfit(cfg, ass_esc, drop_ts, beats):
    """Edit 5: Minimalist Aesthetic Chillhop Golden Hour Drive."""
    dur = cfg["duration"]
    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=40[bg];"
        f"[fg_src]scale=1080:608,colorbalance=rs=0.18:gs=0.06:bs=-0.12[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_staccato_rhythm_montage(cfg, ass_esc, drop_ts, beats):
    """Edit 6: Staccato Multi-Cut Rhythm Sync with Directional Transitions."""
    dur = cfg["duration"]
    beat_pulses = "+".join([f"between(t,{b:.3f},{b+0.08:.3f})" for b in beats[:12]]) if len(beats) > 0 else f"between(t,{drop_ts:.3f},{drop_ts+0.1:.3f})"
    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=25[bg];"
        f"[fg_src]scale=1080:608[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]drawbox=t=fill:c=cyan@0.4:enable='{beat_pulses}'[strobed];"
        f"[strobed]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_freeze_frame_breakdown(cfg, ass_esc, drop_ts, beats):
    """Edit 7: Freeze-Frame Climax Breakdown with Physical Frame Hold & Target Zoom."""
    dur = cfg["duration"]
    freeze_start = 3.0
    freeze_dur = 1.8
    freeze_frames = int(freeze_dur * 60)
    post_dur = dur - (freeze_start + freeze_dur)
    
    return (
        f"[0:v]split=3[v1][v2][v3];"
        f"[v1]trim=0:{freeze_start},setpts=PTS-STARTPTS[p1];"
        f"[v2]trim={freeze_start}:{freeze_start+0.02},setpts=PTS-STARTPTS,loop=loop={freeze_frames}:size=1:start=0,setpts=N/60/TB[p2];"
        f"[v3]trim={freeze_start}:{freeze_start+post_dur},setpts=PTS-STARTPTS[p3];"
        f"[p1][p2][p3]concat=n=3:v=1:a=0[raw_seq];"
        f"[raw_seq]split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30[bg];"
        f"[fg_src]scale=1080:810[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]drawbox=x=440:y=860:w=200:h=200:color=yellow@0.9:t=6:enable='between(t,{freeze_start:.2f},{freeze_start+freeze_dur:.2f})'[boxed];"
        f"[boxed]drawbox=t=fill:c=white@0.85:enable='between(t,{drop_ts:.2f},{drop_ts+0.08:.2f})'[flashed];"
        f"[flashed]crop=w='if(between(t,{freeze_start:.2f},{freeze_start+freeze_dur:.2f}),in_w*0.84,in_w)':h='if(between(t,{freeze_start:.2f},{freeze_start+freeze_dur:.2f}),in_h*0.84,in_h)',scale=1080:1920[zoomed];"
        f"[zoomed]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_cyberpunk_neon_hud(cfg, ass_esc, drop_ts, beats):
    """Edit 8: Cyberpunk Neon HUD & Edge Glow."""
    dur = cfg["duration"]
    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30[bg];"
        f"[fg_src]scale=1080:608,curves=r='0/0 0.5/0.8 1/1':b='0/0 0.5/0.2 1/0.9'[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]drawbox=x=100:y=400:w=880:h=4:color=cyan@0.7:t=fill[top_hud];"
        f"[top_hud]drawbox=x=100:y=1520:w=880:h=4:color=magenta@0.7:t=fill[hud];"
        f"[hud]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_dual_camera_split_stack(cfg, ass_esc, drop_ts, beats):
    """Edit 9: Dual-Perspective Split-Screen Stack."""
    dur = cfg["duration"]
    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[top_raw][bot_raw];"
        f"[top_raw]scale=1080:950:force_original_aspect_ratio=increase,crop=1080:950[top_view];"
        f"[bot_raw]scale=1080:950:force_original_aspect_ratio=increase,crop=1080:950,eq=contrast=1.2:saturation=1.2[bot_view];"
        f"[top_view][bot_view]vstack=inputs=2,pad=1080:1920:0:10:black,drawbox=x=0:y=950:w=1080:h=20:color=gold@0.9:t=fill[divider];"
        f"[divider]subtitles=filename='{ass_esc}'[v_out]"
    )


def vf_bass_drop_negative_inversion(cfg, ass_esc, drop_ts, beats):
    """Edit 10: Bass-Drop Negative Inversion Detonation & Rumble."""
    dur = cfg["duration"]
    return (
        f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,split=2[bg_src][fg_src];"
        f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30[bg];"
        f"[fg_src]scale=1080:608[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]negate=enable='between(t,{drop_ts:.3f},{drop_ts+0.12:.3f})'[inversion];"
        f"[inversion]crop=w=in_w-40:h=in_h-40:x='if(between(t,{drop_ts:.3f},{drop_ts+0.45:.3f}),20+sin(t*50)*18,20)':y='if(between(t,{drop_ts:.3f},{drop_ts+0.45:.3f}),20+cos(t*60)*18,20)',scale=1080:1920[rumble];"
        f"[rumble]subtitles=filename='{ass_esc}'[v_out]"
    )


# =====================================================================
# 10 VIRAL EDIT SPECIFICATIONS
# =====================================================================

SPECIFICATIONS: List[Dict[str, Any]] = [
    # 1. GTA Velocity Ramp
    {
        "id": "viral_01_phonk_velocity_ramp",
        "title": "Unreal GTA Police Evasion Drift #Shorts",
        "game": "Grand Theft Auto",
        "archetype": "Velocity Ramp Speed-Shift",
        "source": SRC_GTA,
        "start_sec": 1155.0,
        "duration": 18.0,
        "bgm": BGM_MONTAGEM,
        "bgm_offset": 0.0,
        "drop_ts": 2.53,
        "pre_drop_silence": 0.20,
        "hook_banner": "WAIT FOR THE DRIFT...",
        "badge_text": "INSANE DRIFT",
        "badge_style": BadgeStyle.MRBEAST_YELLOW,
        "subtitles": [
            (2.53, 5.50, "ZERO ROOM FOR ERROR", "&H0000FFFF&"),
            (5.50, 9.00, "PERFECT CORNER APEX", "&H00FFFFFF&"),
            (9.00, 14.00, "HOW DID HE SURVIVE?!", "&H0000FFFF&"),
            (14.00, 18.00, "CLEANEST ESCAPE", "&H0000FF00&"),
        ],
        "vf_builder": vf_velocity_ramp,
    },
    # 2. PBZ Hyper-Zoom Parry
    {
        "id": "viral_02_hyper_zoom_parry_streak",
        "title": "1 HP Impossible Parry Streak in Phantom Blade Zero #Shorts",
        "game": "Phantom Blade Zero",
        "archetype": "Rhythmic Punch-Zoom Parries",
        "source": SRC_PBZ,
        "start_sec": 1877.0,
        "duration": 18.0,
        "bgm": BGM_GYM,
        "bgm_offset": 0.0,
        "drop_ts": 1.88,
        "pre_drop_silence": 0.20,
        "hook_banner": "1 HP LEFT. WATCH THIS...",
        "badge_text": "1 HP CLUTCH",
        "badge_style": BadgeStyle.CYBER_CYAN,
        "subtitles": [
            (1.88, 5.00, "FIRST TIGER PARRY", "&H0000FF00&"),
            (5.00, 9.50, "FRAME-PERFECT COUNTER", "&H0000FFFF&"),
            (9.50, 14.00, "CLUTCH WEAPON CLASH", "&H00FFFFFF&"),
            (14.00, 18.00, "FLAWLESS VICTORY", "&H0000FF00&"),
        ],
        "vf_builder": vf_hyper_zoom_parries,
    },
    # 3. PBZ Dark Fantasy Cinema
    {
        "id": "viral_03_dark_fantasy_cinema_stack",
        "title": "The Cursed Swordsman of Phantom Blade Zero #Shorts",
        "game": "Phantom Blade Zero",
        "archetype": "Dark Fantasy 2.39:1 Cinema Stack",
        "source": SRC_PBZ,
        "start_sec": 985.0,
        "duration": 20.0,
        "bgm": BGM_FANTASY,
        "bgm_offset": 0.0,
        "drop_ts": 3.12,
        "pre_drop_silence": 0.20,
        "hook_banner": "THE CURSED SWORDSMAN...",
        "badge_text": "CURSED BLADE",
        "badge_style": BadgeStyle.FLOATING_IMPACT,
        "subtitles": [
            (3.12, 7.00, "ONE HP REMAINING", "&H0000FFFF&"),
            (7.00, 12.00, "DEATH BEFORE DISHONOR", "&H00FFFFFF&"),
            (12.00, 16.00, "EXECUTION STRIKE", "&H000000FF&"),
            (16.00, 20.00, "HE SURVIVED THE BRIDGE", "&H0000FFFF&"),
        ],
        "vf_builder": vf_dark_fantasy_anamorphic,
    },
    # 4. GTA Neuro-Glitch RGB
    {
        "id": "viral_04_neuro_glitch_rgb_strobe",
        "title": "When Standoffs Go Completely Out of Control in GTA #Shorts",
        "game": "Grand Theft Auto",
        "archetype": "Flash-Frame Glitch & RGB Split",
        "source": SRC_GTA,
        "start_sec": 486.0,
        "duration": 16.0,
        "bgm": BGM_POPULAR,
        "bgm_offset": 60.0,
        "drop_ts": 2.42,
        "pre_drop_silence": 0.15,
        "hook_banner": "HE BROUGHT A LAUNCHER...",
        "badge_text": "RPG MAYHEM",
        "badge_style": BadgeStyle.NEON_RED,
        "subtitles": [
            (2.42, 6.00, "TO A FISTFIGHT", "&H000000FF&"),
            (6.00, 10.00, "TOTAL CARNAGE", "&H00FFFFFF&"),
            (10.00, 13.50, "ZERO CHANCE OF SURVIVAL", "&H000000FF&"),
            (13.50, 16.00, "POLICE IN SHAMBLES", "&H0000FFFF&"),
        ],
        "vf_builder": vf_neuro_glitch_rgb_strobe,
    },
    # 5. GTA Aesthetic Lofi
    {
        "id": "viral_05_aesthetic_lofi_blurfit",
        "title": "Late Night Drives in Los Santos Hit Different #Shorts",
        "game": "Grand Theft Auto",
        "archetype": "Minimalist Aesthetic Chillhop",
        "source": SRC_GTA,
        "start_sec": 202.0,
        "duration": 20.0,
        "bgm": BGM_LOFI,
        "bgm_offset": 0.0,
        "drop_ts": 3.00,
        "pre_drop_silence": 0.0,
        "hook_banner": "LATE NIGHT CRUISE...",
        "badge_text": "NIGHT DRIVE",
        "badge_style": BadgeStyle.FLOATING_IMPACT,
        "subtitles": [
            (3.00, 8.00, "clear mind, empty highway", "&H00FFFFFF&"),
            (8.00, 14.00, "golden hour city lights", "&H00E0E0E0&"),
            (14.00, 20.00, "pure midnight vibes", "&H00FFFFFF&"),
        ],
        "vf_builder": vf_aesthetic_lofi_blurfit,
    },
    # 6. Multi-Game Staccato Montage
    {
        "id": "viral_06_staccato_rhythm_montage",
        "title": "Don't Blink: 8 Rapid Action Combos in Sync #Shorts",
        "game": "Phantom Blade Zero",
        "archetype": "Staccato Multi-Cut Rhythm Sync",
        "source": SRC_PBZ,
        "start_sec": 2912.0,
        "duration": 18.0,
        "bgm": BGM_PULSE,
        "bgm_offset": 0.0,
        "drop_ts": 2.32,
        "pre_drop_silence": 0.15,
        "hook_banner": "TRY NOT TO BLINK...",
        "badge_text": "DONT BLINK",
        "badge_style": BadgeStyle.MRBEAST_YELLOW,
        "subtitles": [
            (2.32, 5.00, "COMBO STRIKE 1", "&H0000FFFF&"),
            (5.00, 8.50, "VELOCITY CHAIN", "&H00FFFFFF&"),
            (8.50, 13.00, "UNSTOPPABLE MOMENTUM", "&H0000FFFF&"),
            (13.00, 18.00, "DEADLY IMPACT", "&H0000FF00&"),
        ],
        "vf_builder": vf_staccato_rhythm_montage,
    },
    # 7. PBZ Freeze-Frame Breakdown
    {
        "id": "viral_07_freeze_frame_breakdown",
        "title": "Human Reflex Limit is 0.15s... His Timing: 0.03s #Shorts",
        "game": "Phantom Blade Zero",
        "archetype": "Freeze-Frame Climax Breakdown",
        "source": SRC_PBZ,
        "start_sec": 441.0,
        "duration": 18.0,
        "bgm": BGM_ACTION,
        "bgm_offset": 0.0,
        "drop_ts": 4.80,
        "pre_drop_silence": 0.20,
        "hook_banner": "LOOK AT HIS TIMING...",
        "badge_text": "0.03s TIMING",
        "badge_style": BadgeStyle.CYBER_CYAN,
        "subtitles": [
            (1.00, 3.00, "REFLEX LIMIT: 0.15s", "&H00FFFFFF&"),
            (3.00, 4.80, "ACTUAL TIMING: 0.03s", "&H0000FFFF&"),
            (4.80, 10.00, "IMPOSSIBLE PARRY WINDOW", "&H0000FF00&"),
            (10.00, 18.00, "GOD TIER REFLEXES", "&H00FFFFFF&"),
        ],
        "vf_builder": vf_freeze_frame_breakdown,
    },
    # 8. GTA Cyberpunk Neon HUD
    {
        "id": "viral_08_cyberpunk_neon_hud",
        "title": "Midnight Protocol: High-Speed Supercar Run #Shorts",
        "game": "Grand Theft Auto",
        "archetype": "Cyberpunk Neon HUD & Edge Glow",
        "source": SRC_GTA,
        "start_sec": 950.0,
        "duration": 18.0,
        "bgm": BGM_GYM,
        "bgm_offset": 10.0,
        "drop_ts": 2.81,
        "pre_drop_silence": 0.15,
        "hook_banner": "MIDNIGHT PROTOCOL...",
        "badge_text": "NO LIMITS",
        "badge_style": BadgeStyle.CYBER_CYAN,
        "subtitles": [
            (2.81, 6.50, "SYSTEMS OVERCLOCKED", "&H00FFFF00&"),
            (6.50, 11.00, "SPEED LIMIT: IGNORED", "&H0000FFFF&"),
            (11.00, 14.50, "POLICE TRACE: FAILED", "&H0000FF00&"),
            (14.50, 18.00, "ZERO POLICE SIGHTING", "&H00FFFFFF&"),
        ],
        "vf_builder": vf_cyberpunk_neon_hud,
    },
    # 9. PBZ Dual Perspective Split Stack
    {
        "id": "viral_09_dual_perspective_split_stack",
        "title": "The Duel From Both Perspectives: Macro vs Micro #Shorts",
        "game": "Phantom Blade Zero",
        "archetype": "Dual-Perspective Split-Screen Stack",
        "source": SRC_PBZ,
        "start_sec": 2912.0,
        "duration": 18.0,
        "bgm": BGM_FANTASY,
        "bgm_offset": 12.0,
        "drop_ts": 2.68,
        "pre_drop_silence": 0.18,
        "hook_banner": "DUAL PERSPECTIVES...",
        "badge_text": "DUAL COMBO",
        "badge_style": BadgeStyle.MRBEAST_YELLOW,
        "subtitles": [
            (2.68, 6.50, "TOP: ARENA MACRO VIEW", "&H0000FFFF&"),
            (6.50, 10.50, "BOTTOM: WEAPON CLASH", "&H0000FF00&"),
            (10.50, 14.50, "SYNCHRONIZED STRIKES", "&H00FFFFFF&"),
            (14.50, 18.00, "PERFECT DUAL COMBO", "&H0000FFFF&"),
        ],
        "vf_builder": vf_dual_camera_split_stack,
    },
    # 10. GTA Bass-Drop Inversion
    {
        "id": "viral_10_bass_drop_negative_inversion",
        "title": "He Actually Sent This Skyscraper Jump in GTA #Shorts",
        "game": "Grand Theft Auto",
        "archetype": "Bass-Drop Negative Inversion",
        "source": SRC_GTA,
        "start_sec": 730.0,
        "duration": 18.0,
        "bgm": BGM_MONTAGEM,
        "bgm_offset": 12.0,
        "drop_ts": 3.52,
        "pre_drop_silence": 0.20,
        "hook_banner": "HE ACTUALLY SENT IT...",
        "badge_text": "HE SENT IT",
        "badge_style": BadgeStyle.NEON_RED,
        "subtitles": [
            (3.52, 7.00, "MAXIMUM VELOCITY", "&H0000FFFF&"),
            (7.00, 11.50, "THE LANDING IMPACT", "&H000000FF&"),
            (11.50, 15.00, "HOW DID HE SURVIVE?!", "&H00FFFFFF&"),
            (15.00, 18.00, "ZERO CAR DAMAGE", "&H0000FF00&"),
        ],
        "vf_builder": vf_bass_drop_negative_inversion,
    },
]


def main():
    logger.info("Initializing 10-Video Viral Music Sync Suite...")
    BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    GTA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PBZ_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: List[Dict[str, Any]] = []

    for idx, spec in enumerate(SPECIFICATIONS, start=1):
        logger.info(f"\n========================================================")
        logger.info(f"[{idx}/10] Processing {spec['id']} ({spec['archetype']})")
        logger.info(f"========================================================")
        result = render_short_video(spec)
        manifest.append(result)

    manifest_json = BASE_OUTPUT_DIR / "manifest.json"
    manifest_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info(f"\nAll 10 viral videos successfully generated and verified!")
    logger.info(f"Manifest written to: {manifest_json}")


if __name__ == "__main__":
    main()

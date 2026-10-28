"""Unit and integration tests for Viral Edits, Local Voice Agent, Templates, and Instagram Hub."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import numpy as np

from src.voice.voice_agent import VoiceSynthesisAgent, VoicePersona, PERSONA_CONFIG
from src.scripting.script_writer import ScriptWriterAgent, ScriptStyle, GeneratedScriptDTO
from src.templates.template_manager import EditTemplateManager, EditTemplate
from src.publishing.instagram_uploader import InstagramUploader
from src.core.autopilot_v2 import AutopilotV2, AutopilotMode
from src.core.dto import CandidateClipDTO, VLMAnalysisDTO, TranscriptDTO
from src.config.schema import SceneCategory, LayoutMode, CaptionTheme


class TestEditTemplateManager:
    """Tests declarative template registration, loading, and BPM beat tracking."""

    def test_default_templates_seeded(self, tmp_path: Path):
        tm = EditTemplateManager(templates_dir=tmp_path / "templates", music_dir=tmp_path / "music")
        templates = tm.list_templates()
        assert len(templates) >= 4
        ids = [t.template_id for t in templates]
        assert "aura_brazilian_phonk" in ids
        assert "velocity_rage_trap" in ids
        assert "cinematic_lore_ambient" in ids
        assert "combat_parry_sync" in ids

    def test_get_and_save_template(self, tmp_path: Path):
        tm = EditTemplateManager(templates_dir=tmp_path / "templates", music_dir=tmp_path / "music")
        phonk = tm.get_template("aura_brazilian_phonk")
        assert phonk is not None
        assert phonk.category == "PHONK_AURA"
        assert phonk.bpm > 0

        # Save custom template
        new_template = EditTemplate(
            template_id="custom_wuxia_duel",
            display_name="Custom Wuxia Duel",
            category="SOUND_SYNC",
            bpm=140.0,
            beat_drop_sec=3.2,
            framing_mode="LAYOUT_A_BLUR_FIT",
            visual_effects=["ambient_blur", "2frame_flash"],
            recommended_persona=VoicePersona.DRAMATIC_TRAILER_BASS,
        )
        saved = tm.save_template(new_template)
        assert saved.exists()
        reloaded = tm.get_template("custom_wuxia_duel")
        assert reloaded is not None
        assert reloaded.bpm == 140.0

    def test_audio_beatgrid_analysis(self, tmp_path: Path):
        # Create synthetic 3-second wav file
        import soundfile as sf
        sample_rate = 22050
        duration = 3.0
        t = np.linspace(0, duration, int(sample_rate * duration))
        # 2 Hz pulse signal
        audio_signal = np.sin(2 * np.pi * 440 * t) * (np.sin(2 * np.pi * 2 * t) > 0)
        audio_file = tmp_path / "synthetic_pulse.wav"
        sf.write(str(audio_file), audio_signal, sample_rate)

        tm = EditTemplateManager(templates_dir=tmp_path / "templates", music_dir=tmp_path / "music")
        info = tm.analyze_audio_beatgrid(audio_file)
        assert "bpm" in info
        assert "suggested_drop_sec" in info
        assert info["bpm"] > 0


class TestScriptWriterAgent:
    """Tests VLM-grounded hook generation, persona assignment, and narrative styles."""

    def test_generate_action_hook_script(self):
        clip = CandidateClipDTO(
            clip_index=1,
            start_sec=10.0,
            end_sec=35.0,
            duration_sec=25.0,
            peak_timestamp_sec=18.0,
            composite_score=0.92,
            scene_category=SceneCategory.ACTION.value,
        )
        vlm = VLMAnalysisDTO(
            clutch_confidence=0.88,
            is_action_gameplay=True,
            scene_summary="Player executes a frame-perfect parry against the tiger boss.",
        )
        script = ScriptWriterAgent.generate_script(clip, game_title="Phantom Blade Zero", vlm_analysis=vlm)
        assert script.script_style == ScriptStyle.HOOK_ONLY
        assert len(script.spoken_text) > 0
        assert len(script.primary_title) > 0
        assert script.primary_title.endswith("#Shorts")
        assert len(script.tags) >= 3
        assert script.recommended_persona in [VoicePersona.DRAMATIC_TRAILER_BASS, VoicePersona.TIKTOK_HYPE_HOOK]

    def test_generate_lore_narrative_script(self):
        clip = CandidateClipDTO(
            clip_index=2,
            start_sec=50.0,
            end_sec=80.0,
            duration_sec=30.0,
            peak_timestamp_sec=65.0,
            composite_score=0.75,
            scene_category=SceneCategory.DIALOGUE.value,
        )
        script = ScriptWriterAgent.generate_script(clip, game_title="Elden Ring", force_style=ScriptStyle.FULL_NARRATIVE)
        assert script.script_style == ScriptStyle.FULL_NARRATIVE
        assert len(script.spoken_text.split()) > 10
        assert script.recommended_persona == VoicePersona.CALM_LORE_STORYTELLER


class TestVoiceSynthesisAgent:
    """Tests local neural TTS configuration, persona parameters, and hook synthesis."""

    def test_personas_and_speed_profiles(self):
        assert VoicePersona.DRAMATIC_TRAILER_BASS in PERSONA_CONFIG
        assert VoicePersona.TIKTOK_HYPE_HOOK in PERSONA_CONFIG
        assert VoicePersona.CALM_LORE_STORYTELLER in PERSONA_CONFIG

        cfg = PERSONA_CONFIG[VoicePersona.DRAMATIC_TRAILER_BASS]
        assert "voice" in cfg
        assert cfg["speed"] <= 1.0

    def test_synthesize_hook_duration_scaling(self, tmp_path: Path):
        agent = VoiceSynthesisAgent(clone_dir=tmp_path / "clones")
        out_wav = tmp_path / "test_hook.wav"

        # Mock Kokoro pipeline generator for rapid isolated test
        class MockKPipeline:
            def __call__(self, text, voice, speed):
                # Return dummy chunk: 0.5s of 24kHz audio
                dummy_pcm = np.zeros(12000, dtype=np.float32)
                yield None, None, dummy_pcm

        agent._pipeline = MockKPipeline()
        path, dur = agent.synthesize_hook(
            hook_text="Nobody believed he could survive this parry.",
            output_path=out_wav,
            persona=VoicePersona.TIKTOK_HYPE_HOOK,
        )
        assert path.exists()
        assert dur == 0.5


class TestInstagramUploader:
    """Tests Instagram Reels hybrid adapter, caption limits, and dry-run staging."""

    def test_caption_sanitization(self):
        title = "Epic Boss Fight #Shorts"
        desc = "Incredible combat sequences from Phantom Blade Zero."
        tags = [f"#tag{i}" for i in range(40)]  # 40 tags exceeds limit
        comment = "What would you rate this fight?"

        clean_caption = InstagramUploader.sanitize_caption(
            title=title,
            description=desc,
            tags=tags,
            engagement_question=comment,
        )
        assert len(clean_caption) <= 2200
        # Verify tag limit enforced (max 30 hashtags)
        hashtag_count = clean_caption.count("#")
        assert hashtag_count <= 30
        assert "What would you rate this fight?" in clean_caption

    def test_dry_run_upload_receipt(self, tmp_path: Path):
        # Create synthetic 1-sec test video
        test_video = tmp_path / "sample_reel.mp4"
        import subprocess
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=1080x1920:rate=30",
            "-c:v", "libx264", "-preset", "ultrafast",
            str(test_video)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        history_file = tmp_path / "ig_history.json"
        uploader = InstagramUploader(history_path=history_file)
        assert uploader.is_authenticated() is False

        receipt = uploader.upload_reel(
            video_path=test_video,
            caption="Test Reel Caption #gaming",
            dry_run=True,
        )
        assert receipt["success"] is True
        assert receipt["mode"] == "DRY_RUN_STAGED"
        assert "media_id" in receipt
        assert history_file.exists()

        history_data = json.loads(history_file.read_text(encoding="utf-8"))
        assert len(history_data) == 1
        assert history_data[0]["media_id"] == receipt["media_id"]

    def test_stagger_scheduling(self):
        yt_time = "2026-10-28T12:00:00+00:00"
        ig_time = InstagramUploader.calculate_optimal_stagger(yt_time)
        assert ig_time.minute == 45
        assert ig_time.hour == 12


class TestAutopilotV2:
    """Tests Autopilot ecosystem inspection and dynamic viral edit addition."""

    def test_ecosystem_status(self, tmp_path: Path):
        auto = AutopilotV2()
        status = auto.get_ecosystem_status()
        assert "youtube" in status
        assert "instagram" in status
        assert "registered_templates_count" in status
        assert status["registered_templates_count"] >= 4
        assert "NVIDIA GeForce RTX 4060 Ti" in status["gpu_device"]

    def test_add_viral_edit(self, tmp_path: Path):
        auto = AutopilotV2()
        tmpl = auto.add_viral_edit(
            template_id="test_phonk_burst",
            display_name="Test Phonk Burst",
            bpm=135.0,
            beat_drop_sec=2.2,
            framing_mode="LAYOUT_A_BLUR_FIT",
            recommended_persona=VoicePersona.TIKTOK_HYPE_HOOK,
        )
        assert tmpl.template_id == "test_phonk_burst"
        assert tmpl.bpm == 135.0
        # Verify persistence
        loaded = auto.template_mgr.get_template("test_phonk_burst")
        assert loaded is not None
        assert loaded.display_name == "Test Phonk Burst"

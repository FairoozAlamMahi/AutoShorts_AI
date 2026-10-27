"""Test suite for Agent Co-Pilot, Contextual Hook Engine, and Title Deduplication."""
import json
import pytest
from pathlib import Path

from src.analytics.hook_engine import HookEngine
from src.analytics.title_linter import TitleLinter
from src.analytics.agent_copilot import AgentCoPilotSynthesizer
from src.core.dto import ClipMetadataDTO
from src.agent_toolkit import AgentToolkit


def test_contextual_hook_generation_and_diversity():
    """Verifies that multi-clip batches generate distinct, non-duplicate hooks anchored in dialogue."""
    transcript_sample = "They said they're paying you a visit, so watch your back."
    hooks = []
    for idx in range(1, 5):
        h = HookEngine.generate_hook_overlay(
            transcript_snippet=transcript_sample,
            game_name="GTA 6",
            scene_type="ACTION",
            clip_index=idx,
        )
        assert len(h) > 10
        score = HookEngine.score_hook(h)
        assert score["overall_score"] >= 65
        hooks.append(h)

    # Verify diversity across clips (no 4 identical hooks)
    unique_hooks = set(hooks)
    assert len(unique_hooks) >= 3, f"Expected varied hooks across clips, got: {hooks}"

    # Verify that dialogue quote was incorporated
    assert any("paying you a visit" in h.lower() for h in hooks)

    # Verify story game GTA 6 does not get 1 HP trope
    assert not any("1 hp" in h.lower() for h in hooks)


def test_agent_copilot_synthesis_and_judgment():
    """Verifies AgentCoPilot synthesizes grounded metadata and algorithmically judges against VLM."""
    synth = AgentCoPilotSynthesizer.synthesize_agent_metadata(
        clip_index=1,
        transcript_text="Alright Jason, we are cargo. Maybe some warning next time.",
        vlm_summary="Helicopter pursuit over Vice City port",
        detected_events=["police_chase", "helicopter_approach"],
        game_name="GTA 6",
        scene_type="ACTION",
    )

    agent_meta = synth["agent_metadata"]
    assert "GTA 6" in agent_meta.primary_title or "Gta 6" in agent_meta.primary_title
    assert len(agent_meta.primary_title) <= 60
    assert len(agent_meta.tags) >= 3
    assert len(synth["extracted_quotes"]) > 0

    # Test Judgment against a generic VLM proposal
    generic_vlm_meta = ClipMetadataDTO(
        primary_title="INSANE GTA 6 MOMENT!",
        alternative_titles=["GTA 6 Highlight"],
        small_description="Watch this crazy moment in GTA 6!",
        tags=["#gta6", "#gaming"],
    )

    judgment = AgentCoPilotSynthesizer.judge_and_select_best_metadata(
        agent_synthesis=synth,
        vlm_proposed_meta=generic_vlm_meta,
        game_name="GTA 6",
    )

    # Agent should win against generic boilerplate
    assert judgment["winner"] == "AGENT"
    assert judgment["agent_score"] > judgment["vlm_score"]
    assert "generic fallback" in judgment["reason"].lower() or "mobile" in judgment["reason"].lower()
    assert judgment["selected_metadata"].primary_title == agent_meta.primary_title


def test_vlm_observation_bundle_and_toolkit_copilot(tmp_path: Path):
    """Verifies observation bundle export and AgentToolkit synthesis."""
    toolkit = AgentToolkit(project_root=tmp_path)
    bundle_path = tmp_path / "data" / "scratch" / "test_copilot_job" / "vlm_observation_bundle.json"

    clips_data = [
        {
            "clip_index": 1,
            "start_sec": 10.0,
            "end_sec": 42.0,
            "duration_sec": 32.0,
            "scene_category": "ACTION",
            "transcript": "Lucia, step on the gas right now before they block the bridge!",
            "vlm_summary": "Police pursuit over bridge at night",
            "vlm_events": ["police_chase"],
            "vlm_proposed_title": "INSANE GTA 6 MOMENT!",
            "hook_overlay_text": "",
            "keyframe_paths": [],
        },
        {
            "clip_index": 2,
            "start_sec": 50.0,
            "end_sec": 84.0,
            "duration_sec": 34.0,
            "scene_category": "CLUTCH",
            "transcript": "Jason watch out for that helicopter above us!",
            "vlm_summary": "Helicopter searchlight illuminates car",
            "vlm_events": ["searchlight"],
            "vlm_proposed_title": "INSANE GTA 6 MOMENT!",
            "hook_overlay_text": "",
            "keyframe_paths": [],
        }
    ]

    AgentCoPilotSynthesizer.export_observation_bundle(
        bundle_path=bundle_path,
        job_id="test_copilot_job",
        game_name="GTA 6",
        clips_data=clips_data,
    )

    # Test inspection
    inspected = toolkit.inspect_vlm_observations("test_copilot_job")
    assert inspected["job_id"] == "test_copilot_job"
    assert len(inspected["clips"]) == 2

    # Test synthesis & judgment across the job
    review = toolkit.synthesize_and_judge_metadata("test_copilot_job", update_disk=False)
    assert review["job_id"] == "test_copilot_job"
    assert len(review["judgments"]) == 2
    for j in review["judgments"]:
        assert j["winner"] == "AGENT"
        assert len(j["selected_title"]) > 5
        assert len(j["selected_hook_overlay"]) > 5

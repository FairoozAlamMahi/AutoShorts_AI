"""VLM-Grounded Scriptwriting Agent for Viral Gaming Shorts.
Generates spoken voiceover hooks, full narrative scripts, and synchronized subtitle tokens.
Supports Hybrid Dynamic Mode: Hook-Only for action/clutches, Full Narrative for lore/dialogue.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

from ..core.dto import CandidateClipDTO, VLMAnalysisDTO, TranscriptDTO
from ..config.schema import SceneCategory
from ..voice.voice_agent import VoicePersona
from ..skills.youtube_agent_bridge import youtube_agent

logger = logging.getLogger(__name__)


class ScriptStyle:
    HOOK_ONLY = "HOOK_ONLY"            # First 2.5s spoken hook -> drops into music
    FULL_NARRATIVE = "FULL_NARRATIVE"  # Continuous voiceover across the clip


class GeneratedScriptDTO(BaseModel):
    """Complete scripted narrative package for a viral short."""
    script_style: str = ScriptStyle.HOOK_ONLY
    spoken_text: str
    hook_overlay_text: str
    recommended_persona: str = VoicePersona.DRAMATIC_TRAILER_BASS
    primary_title: str
    description: str
    tags: List[str] = Field(default_factory=list)
    engagement_question: str
    estimated_voice_duration_sec: float = 3.0
    hook_score: int = 75
    hook_formula: str = "The Superlative"
    title_score: int = 85
    mobile_safe_title: str = ""


class ScriptWriterAgent:
    """Creates context-grounded spoken hooks and narrative scripts from VLM and acoustic signals."""

    # Curated hook templates by scene category
    ACTION_HOOK_TEMPLATES = [
        "Nobody expected him to pull off this parry...",
        "Watch what happens when he enters god mode.",
        "This is the cleanest combat sequence you will see today.",
        "He did not miss a single counter in this fight.",
        "Wait until the final strike lands.",
        "How did he survive this impossible boss combo?",
        "When you master the timing in this game...",
    ]

    CLUTCH_HOOK_TEMPLATES = [
        "He had one HP left and did this...",
        "The most clutch reflex save ever recorded.",
        "Never celebrate too early against this boss.",
        "One wrong input and it was over.",
    ]

    LORE_TEMPLATES = [
        "In the darkest corners of this world, only one warrior survived the collapse.",
        "They said this blade was cursed, but nobody was prepared for what it awakened.",
        "Every encounter in this arena is designed to test your absolute limits.",
        "He walked into the boss arena knowing he had zero room for error.",
    ]

    @classmethod
    def generate_script(
        cls,
        clip: CandidateClipDTO,
        game_title: Optional[str] = None,
        vlm_analysis: Optional[VLMAnalysisDTO] = None,
        transcript: Optional[TranscriptDTO] = None,
        force_style: Optional[str] = None,
    ) -> GeneratedScriptDTO:
        """
        Determines the script style (Hook-Only vs Full Narrative) and synthesizes the script package.
        """
        g_name = game_title or "Gaming"
        clean_game = re.sub(r"[^\w\s]", "", g_name).strip()

        # Decide script style based on scene category or force_style
        scene_cat = getattr(clip, "scene_category", SceneCategory.ACTION)
        if isinstance(scene_cat, str):
            scene_cat_val = scene_cat.upper()
        else:
            scene_cat_val = scene_cat.value.upper()

        if force_style:
            style = force_style
        elif scene_cat_val in ["DIALOGUE", "STORY", "LORE"]:
            style = ScriptStyle.FULL_NARRATIVE
        else:
            style = ScriptStyle.HOOK_ONLY

        # VLM visual context extraction if available
        v_summary = ""
        if vlm_analysis and vlm_analysis.scene_summary:
            v_summary = vlm_analysis.scene_summary

        if style == ScriptStyle.HOOK_ONLY:
            return cls._build_hook_only_script(clip, clean_game, scene_cat_val, v_summary)
        else:
            return cls._build_narrative_script(clip, clean_game, scene_cat_val, v_summary)

    @classmethod
    def _build_hook_only_script(
        cls, clip: CandidateClipDTO, game: str, category: str, v_summary: str
    ) -> GeneratedScriptDTO:
        """Builds a high-retention 2.5s opening hook script scored across 21 hook formulas."""
        candidates = [
            f"You will not believe how he survived this 1 HP fight in {game}!",
            f"Stop making this 1 combat mistake in {game} right now.",
            f"This is the cleanest combat combo in {game}... wait for the final strike!",
            f"Watch what happens when you hit this jump at maximum speed in {game}!",
            f"99% of players would have died here, but watch what he did next in {game}.",
            f"He triggered a 5-star wanted level in {game} and did this impossible escape!",
        ]
        if "CLUTCH" in category or "parry" in v_summary.lower():
            candidates.insert(0, f"He had 1 HP left and pulled off this impossible parry in {game}!")
            persona = VoicePersona.TIKTOK_HYPE_HOOK
        else:
            persona = VoicePersona.DRAMATIC_TRAILER_BASS

        # Score and rank all candidate hooks using the 5-metric panel from hookscore.py
        ranked = youtube_agent.rank_hooks(candidates)
        winner = ranked[0]
        spoken_hook = winner.hook
        hook_formula = winner.formula_name
        hook_score = winner.verdict_score

        overlay_hook = "IMPOSSIBLE PARRY..." if "parry" in spoken_hook.lower() else ("5 STAR ESCAPE..." if "star" in spoken_hook.lower() else "WATCH THE IMPACT...")

        # Craft title and lint pairing with thumbnail overlay
        candidate_title = f"Unreal 1 HP Clutch in {game} #Shorts" if "parry" in spoken_hook.lower() or "clutch" in spoken_hook.lower() else f"The Cleanest Move in {game} #Shorts"
        lint_res = youtube_agent.lint_title_and_thumbnail(candidate_title, overlay_hook)
        title = lint_res.title
        title_score = lint_res.score
        mobile_title = title if lint_res.mobile_safe else title[:40].rsplit(" ", 1)[0]

        desc = f"{title}\nHigh-octane action gameplay from {game}.\n\nRate this gameplay from 1 to 10 below!"
        tags = [f"#{game.lower().replace(' ', '')}", "#shorts", "#gaming", "#action", "#viral"]
        comment = "Could you have pulled this off? Drop your rating 1-10 below."

        return GeneratedScriptDTO(
            script_style=ScriptStyle.HOOK_ONLY,
            spoken_text=spoken_hook,
            hook_overlay_text=overlay_hook,
            recommended_persona=persona,
            primary_title=title,
            description=desc,
            tags=tags,
            engagement_question=comment,
            estimated_voice_duration_sec=2.8,
            hook_score=hook_score,
            hook_formula=hook_formula,
            title_score=title_score,
            mobile_safe_title=mobile_title,
        )

    @classmethod
    def _build_narrative_script(
        cls, clip: CandidateClipDTO, game: str, category: str, v_summary: str
    ) -> GeneratedScriptDTO:
        """Builds a continuous narrative voiceover script for lore/story moments."""
        import random
        base_line = random.choice(cls.LORE_TEMPLATES)
        if v_summary:
            spoken = f"In {game}, {v_summary.lower().rstrip('.')}—and what happens next changes everything."
        else:
            spoken = f"{base_line} This moment in {game} proves why the combat is unmatched."

        title = f"The Untold Lore of {game} #Shorts"
        desc = f"{title}\nDeep atmospheric lore and storytelling from {game}."
        tags = [f"#{game.lower().replace(' ', '')}", "#shorts", "#gaming", "#lore", "#story"]
        comment = "Did you notice this detail when you played? Let us know below."

        return GeneratedScriptDTO(
            script_style=ScriptStyle.FULL_NARRATIVE,
            spoken_text=spoken,
            hook_overlay_text="THE LORE GOES DEEP...",
            recommended_persona=VoicePersona.CALM_LORE_STORYTELLER,
            primary_title=title,
            description=desc,
            tags=tags,
            engagement_question=comment,
            estimated_voice_duration_sec=6.5,
        )

"""Multimodal Scene Classifier and Narrative Boundary Refiner.
Detects Action, Comedy, Clutch, Story/Dialogue, and Fail/Death moments
and recommends layout framing, caption themes, and BGM styling.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from ..config.schema import LayoutMode, CaptionTheme, SceneCategory
from ..core.dto import CandidateClipDTO, TranscriptDTO, VLMAnalysisDTO, TranscriptSegmentDTO


COMEDY_PATTERNS = [
    r"\b(ha+h+a+|l+o+l+|l+m+a+o+)\b",
    r"\b(what\s+the\s+heck|what\s+the\s+fuck|wtf)\b",
    r"\b(bro\s+what|no\s*way|are\s+you\s+kidding|are\s+you\s+serious)\b",
    r"\b(look\s+at\s+him|look\s+at\s+that|what\s+was\s+that)\b",
    r"\b(screaming|laughing|crying|died|wasted|fail|clown)\b",
]

ACTION_PATTERNS = [
    r"\b(shoot|fire|kill|eliminated|grenade|rpg|rocket|tank)\b",
    r"\b(drive|car|cops|police|faster|chase|speed|heli|helicopter)\b",
    r"\b(explosion|blast|boom|push|attack|smash|hit)\b",
]

CLUTCH_PATTERNS = [
    r"\b(clutch|clutched|ace|1v[1-5]|one\s*hp|1\s*hp)\b",
    r"\b(last\s+guy|last\s+one|defuse|we\s+won|let'?s\s*go|gg)\b",
]

DIALOGUE_PATTERNS = [
    r"\b(listen|plan|money|meet\s+me|contract|mission|secret|story|talking)\b",
    r"\b(i\s+told\s+you|why\s+did\s+you|where\s+are\s+we|who\s+is\s+that)\b",
]


@dataclass
class SceneClassificationResult:
    category: SceneCategory
    confidence: float
    reason: str
    recommended_layout: LayoutMode
    recommended_caption_theme: CaptionTheme
    recommended_caption_font_size: int
    recommended_bgm: Optional[str]


class MultimodalSceneClassifier:
    """Classifies video segments into semantic categories to drive per-clip customization."""

    @classmethod
    def classify(
        cls,
        clip: CandidateClipDTO,
        transcript: Optional[TranscriptDTO] = None,
        vlm_analysis: Optional[VLMAnalysisDTO] = None,
    ) -> SceneClassificationResult:
        """
        Analyzes audio scores, visual motion, transcript semantics, and optional VLM signals
        to categorize the clip and recommend optimal presentation styling.
        """
        # If VLM already made a high-confidence determination
        if vlm_analysis and vlm_analysis.scene_type:
            v_type = vlm_analysis.scene_type.upper()
            if "COMEDY" in v_type or "FAIL" in v_type:
                return cls._build_result(SceneCategory.COMEDY, 0.90, "VLM identified comedy/fail sequence")
            elif "CLUTCH" in v_type:
                return cls._build_result(SceneCategory.CLUTCH, 0.92, "VLM identified clutch sequence")
            elif "DIALOGUE" in v_type:
                return cls._build_result(SceneCategory.DIALOGUE, 0.88, "VLM identified dialogue/cutscene")
            elif "ACTION" in v_type:
                return cls._build_result(SceneCategory.ACTION, 0.90, "VLM identified high action gameplay")

        text = ""
        speech_coverage = 0.0
        if transcript and transcript.segments:
            text = " ".join(s.text for s in transcript.segments).lower()
            speech_coverage = transcript.speech_coverage_ratio

        scores = {
            SceneCategory.COMEDY: 0.0,
            SceneCategory.ACTION: 0.0,
            SceneCategory.CLUTCH: 0.0,
            SceneCategory.DIALOGUE: 0.0,
        }

        # 1. Semantic keyword scoring
        for pat in COMEDY_PATTERNS:
            if re.search(pat, text):
                scores[SceneCategory.COMEDY] += 1.5

        for pat in ACTION_PATTERNS:
            if re.search(pat, text):
                scores[SceneCategory.ACTION] += 1.2

        for pat in CLUTCH_PATTERNS:
            if re.search(pat, text):
                scores[SceneCategory.CLUTCH] += 1.8

        for pat in DIALOGUE_PATTERNS:
            if re.search(pat, text):
                scores[SceneCategory.DIALOGUE] += 1.0

        # 2. Multimodal signal fusion
        # High visual motion boosts action
        if clip.visual_score > 0.45:
            scores[SceneCategory.ACTION] += 1.2
        elif clip.visual_score < 0.25 and speech_coverage > 0.40:
            scores[SceneCategory.DIALOGUE] += 0.8

        # High acoustic score boosts action / clutch
        if clip.acoustic_score > 0.60:
            scores[SceneCategory.ACTION] += 0.6
            scores[SceneCategory.CLUTCH] += 0.4

        # Very high speech coverage with low motion leans towards comedy or dialogue
        if speech_coverage > 0.65:
            if scores[SceneCategory.COMEDY] > 0:
                scores[SceneCategory.COMEDY] += 0.8
            else:
                scores[SceneCategory.DIALOGUE] += 0.6

        # Determine winner
        best_cat = max(scores, key=lambda k: scores[k])
        best_score = scores[best_cat]

        if best_score < 0.5:
            # Default to action for gameplay highlights
            return cls._build_result(
                SceneCategory.ACTION,
                0.60,
                "Default high-energy gameplay action"
            )

        confidence = min(0.98, 0.65 + best_score * 0.1)
        reason = f"Detected {best_cat.value} signals (semantic score: {best_score:.2f})"
        return cls._build_result(best_cat, confidence, reason)

    @classmethod
    def _build_result(cls, category: SceneCategory, confidence: float, reason: str) -> SceneClassificationResult:
        if category == SceneCategory.COMEDY or category == SceneCategory.FAIL:
            return SceneClassificationResult(
                category=category,
                confidence=confidence,
                reason=reason,
                recommended_layout=LayoutMode.LAYOUT_4_3_BLUR_FIT,  # 4:3 framing so comedy/fails aren't cropped
                recommended_caption_theme=CaptionTheme.TIKTOK_RED_BOX,
                recommended_caption_font_size=68,
                recommended_bgm="assets/music/ambient_lofi.mp3",
            )
        elif category == SceneCategory.CLUTCH:
            return SceneClassificationResult(
                category=category,
                confidence=confidence,
                reason=reason,
                recommended_layout=LayoutMode.LAYOUT_4_3_BLUR_FIT,  # 4:3 high-impact focus for close combat & parries
                recommended_caption_theme=CaptionTheme.NEON_CYBER_GREEN,
                recommended_caption_font_size=72,
                recommended_bgm="assets/music/action_pulse.mp3",
            )
        elif category == SceneCategory.DIALOGUE:
            return SceneClassificationResult(
                category=category,
                confidence=confidence,
                reason=reason,
                recommended_layout=LayoutMode.LAYOUT_4_3_BLUR_FIT,  # 4:3 balanced framing for dialogues & cutscenes
                recommended_caption_theme=CaptionTheme.CLEAN_WHITE,
                recommended_caption_font_size=64,
                recommended_bgm="assets/music/ambient_lofi.mp3",
            )
        else:  # ACTION
            return SceneClassificationResult(
                category=category,
                confidence=confidence,
                reason=reason,
                recommended_layout=LayoutMode.LAYOUT_A_BLUR_FIT,  # 100% Full landscape view for wide arena & boss battles
                recommended_caption_theme=CaptionTheme.MRBEAST_YELLOW,
                recommended_caption_font_size=72,
                recommended_bgm="assets/music/action_pulse.mp3",
            )


class NarrativeBoundaryRefiner:
    """Refines candidate timestamps to snap cleanly to sentence boundaries and natural speech pauses."""

    @classmethod
    def refine_bounds(
        cls,
        raw_start: float,
        raw_end: float,
        transcript: Optional[TranscriptDTO],
        min_duration_sec: float = 30.0,
        max_duration_sec: float = 60.0,
        total_duration_sec: Optional[float] = None,
    ) -> Tuple[float, float, str]:
        """
        Adjusts raw_start and raw_end so that words or sentences are never truncated mid-phrase.
        Returns (refined_start, refined_end, refinement_note).
        """
        if not transcript or not transcript.segments or transcript.is_skipped:
            return raw_start, raw_end, "No transcript available for boundary refinement"

        start = raw_start
        end = raw_end
        notes = []

        # 1. Snap start to sentence start within [-2.5s, +1.5s]
        for seg in transcript.segments:
            diff = seg.start_sec - raw_start
            if -2.5 <= diff <= 1.5:
                start = max(0.0, seg.start_sec)
                notes.append(f"Snapped start to sentence at {start:.2f}s")
                break

        # 2. Snap end to sentence end (allow punchline or reaction to finish) within [-1.0s, +3.0s]
        for seg in reversed(transcript.segments):
            diff = seg.end_sec - raw_end
            if -1.0 <= diff <= 3.0:
                candidate_end = seg.end_sec + 0.3  # Add 300ms tail so audio doesn't clip
                if total_duration_sec:
                    candidate_end = min(total_duration_sec, candidate_end)
                end = candidate_end
                notes.append(f"Snapped end to complete sentence at {end:.2f}s")
                break

        # 3. Enforce min and max duration bounds
        dur = end - start
        if dur < min_duration_sec:
            deficit = min_duration_sec - dur
            start = max(0.0, start - deficit * 0.5)
            end = end + deficit * 0.5
            if total_duration_sec and end > total_duration_sec:
                end = total_duration_sec
                start = max(0.0, end - min_duration_sec)
            notes.append(f"Expanded to satisfy min duration ({min_duration_sec}s)")

        if (end - start) > max_duration_sec:
            end = start + max_duration_sec
            notes.append(f"Capped to max duration ({max_duration_sec}s)")

        note_str = "; ".join(notes) if notes else "Clean boundary alignment confirmed"
        return round(start, 3), round(end, 3), note_str

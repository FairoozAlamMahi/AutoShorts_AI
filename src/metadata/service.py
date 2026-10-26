"""MetadataService generating context-grounded titles, descriptions, and factual attribution."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from ..config.schema import MetadataMode, OwnershipType, PreRunToggles
from ..core.dto import ClipMetadataDTO, YouTubeMetadataDTO, TranscriptDTO, CandidateClipDTO
from ..providers.base import VLMProvider
from ..ingest.rights_manager import RightsManager


class MetadataService:
    """Generates context-aware titles, descriptions, and tags across AI and Rule-Based modes."""

    def __init__(self, vlm_provider: Optional[VLMProvider] = None) -> None:
        self.vlm_provider = vlm_provider

    def generate_metadata(
        self,
        clip: CandidateClipDTO,
        toggles: PreRunToggles,
        yt_meta: Optional[YouTubeMetadataDTO] = None,
        transcript: Optional[TranscriptDTO] = None,
        vlm_summary: Optional[str] = None,
    ) -> ClipMetadataDTO:
        # Mode: OFF
        if toggles.metadata_mode == MetadataMode.OFF:
            return ClipMetadataDTO(
                primary_title=f"Highlight #{clip.clip_index}",
                alternative_titles=[],
                small_description="",
                tags=[],
                attribution_text=None,
            )

        # Determine resolved game name
        resolved_game = (
            toggles.game_name_context
            or (yt_meta.detected_game if yt_meta else None)
            or "Gaming"
        )

        # Factual attribution string
        attribution = RightsManager.generate_attribution_string(
            ownership_type=toggles.ownership_type,
            uploader=yt_meta.uploader if yt_meta else None,
            title=yt_meta.title if yt_meta else None,
            url=yt_meta.url if yt_meta else None,
        )

        context: Dict[str, Any] = {
            "game_name": resolved_game,
            "clip_index": clip.clip_index,
            "start_sec": clip.start_sec,
            "end_sec": clip.end_sec,
            "scene_summary": vlm_summary or "High excitement gaming moment",
            "transcript_text": transcript.full_text if (transcript and not transcript.is_skipped) else "",
            "uploader": yt_meta.uploader if yt_meta else None,
            "source_title": yt_meta.title if yt_meta else None,
        }

        # Mode: LOCAL_VLM or EXTERNAL_MCP_AGENT
        if toggles.metadata_mode in (MetadataMode.LOCAL_VLM, MetadataMode.EXTERNAL_MCP_AGENT) and self.vlm_provider:
            try:
                meta = self.vlm_provider.generate_titles_and_description(context)
                meta.attribution_text = attribution
                if attribution:
                    meta.small_description = f"{meta.small_description}\n\n{attribution}".strip()
                return meta
            except Exception:
                pass  # Fallback to rule engine

        # Mode: RULE_BASED (or fallback)
        meta = self._generate_rule_based_metadata(clip, resolved_game, transcript, yt_meta)
        meta.attribution_text = attribution
        if attribution:
            meta.small_description = f"{meta.small_description}\n\n{attribution}".strip()
        return meta

    @staticmethod
    def _generate_rule_based_metadata(
        clip: CandidateClipDTO,
        game_name: str,
        transcript: Optional[TranscriptDTO] = None,
        yt_meta: Optional[YouTubeMetadataDTO] = None,
    ) -> ClipMetadataDTO:
        # Check for reaction words in transcript
        speech_text = transcript.full_text.lower() if (transcript and not transcript.is_skipped) else ""
        has_clutch = "clutch" in speech_text
        has_insane = "insane" in speech_text or "no way" in speech_text
        has_1hp = "1 hp" in speech_text or "one hp" in speech_text

        clean_game = game_name.strip()
        tag_game = f"#{re.sub(r'[^a-zA-Z0-9]', '', clean_game).lower()}"

        if has_1hp:
            primary = f"1 HP {clean_game.upper()} CLUTCH!"
            alts = [f"How Did I Survive This? ({clean_game})", f"Insane 1 HP Save in {clean_game}"]
        elif has_clutch:
            primary = f"THE CLEANEST {clean_game.upper()} CLUTCH!"
            alts = [f"Unreal 1v4 in {clean_game}", f"Never Give Up in {clean_game}"]
        elif has_insane:
            primary = f"THIS {clean_game.upper()} MOMENT WAS INSANE!"
            alts = [f"No Way This Just Happened ({clean_game})", f"Peak {clean_game} Gameplay"]
        else:
            primary = f"INSANE {clean_game.upper()} HIGHLIGHT #{clip.clip_index}!"
            alts = [f"Best {clean_game} Moments", f"Clean {clean_game} Elimination"]

        # Ensure primary title is < 60 chars
        if len(primary) > 55:
            primary = primary[:52] + "..."

        description = (
            f"Crazy highlight moment from {clean_game}! "
            f"Subscribe for more daily gaming shorts."
        )

        tags = [tag_game, "#gaming", "#shorts", "#gamer", "#viral"]

        return ClipMetadataDTO(
            primary_title=primary,
            alternative_titles=alts,
            small_description=description,
            tags=tags,
        )

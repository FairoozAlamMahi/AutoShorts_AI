"""Agent Co-Pilot & Multimodal Metadata Synthesizer.
Allows the AI Agent to review VLM keyframe visual data alongside Whisper transcripts,
synthesize context-grounded titles, descriptions, and starting text hooks,
and algorithmically judge whether the VLM or Agent metadata is superior for mobile CTR.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ..core.dto import ClipMetadataDTO, VLMAnalysisDTO, TranscriptDTO, CandidateClipDTO
from .hook_engine import HookEngine
from .title_linter import TitleLinter


class AgentCoPilotSynthesizer:
    """Co-Pilot interface combining visual VLM data and speech semantics with Agent judgment."""

    @classmethod
    def extract_salient_quotes(cls, transcript_text: str, max_words: int = 6) -> List[str]:
        """Extracts memorable dialogue phrases from transcript for clickable titles and hooks."""
        if not transcript_text or not transcript_text.strip():
            return []

        clean = re.sub(r"[^\w\s',!?]", "", transcript_text).strip()
        sentences = re.split(r"[.!?]+", clean)
        quotes: List[str] = []

        for s in sentences:
            s_clean = s.strip()
            words = s_clean.split()
            if 2 <= len(words) <= max_words:
                quotes.append(s_clean)
            elif len(words) > max_words:
                # Extract the punchiest contiguous segment
                quotes.append(" ".join(words[:max_words]))

        return [q for q in quotes if len(q) > 6]

    @classmethod
    def synthesize_agent_metadata(
        cls,
        clip_index: int,
        transcript_text: str = "",
        vlm_summary: Optional[str] = None,
        detected_events: Optional[List[str]] = None,
        game_name: Optional[str] = None,
        scene_type: str = "ACTION",
        attribution_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes a rich, mobile-optimized title, description, and on-screen hook
        grounded in the multimodal visual observations from VLM and spoken transcript.
        """
        game = (game_name or "Gaming").strip()
        events = detected_events or []
        quotes = cls.extract_salient_quotes(transcript_text, max_words=6)
        primary_quote = quotes[0] if quotes else ""

        # 1. Synthesize Contextual Title
        titles: List[str] = []
        clean_game = game.title() if len(game) > 4 else game.upper()

        # Check for named characters or specific dialogue
        has_jason = "jason" in transcript_text.lower()
        has_lucia = "lucia" in transcript_text.lower()
        has_characters = has_jason or has_lucia

        if primary_quote:
            clean_q = primary_quote.rstrip(",.!?")
            titles.append(f'"{clean_q}" in {clean_game}')
            titles.append(f'When They Said "{clean_q}" ({clean_game})')

        if has_characters:
            if has_jason and has_lucia:
                titles.append(f"Jason & Lucia's Craziest {clean_game} Moment")
            elif has_lucia:
                titles.append(f"Lucia's Unbelievable {clean_game} Move")
            elif has_jason:
                titles.append(f"Jason's Wildest {clean_game} Getaway")

        if vlm_summary and len(vlm_summary.strip()) > 5:
            # Ground title in visual scene observation
            sum_words = [w for w in vlm_summary.split() if len(w) > 3][:4]
            if sum_words:
                vis_phrase = " ".join(sum_words).title()
                titles.append(f"Insane {vis_phrase} in {clean_game}")

        # Add distinct formulaic backups if titles list is short
        titles.append(f"The 1 {clean_game} Play Nobody Expected #{clip_index}")
        titles.append(f"Why This {clean_game} {scene_type.title()} Went Viral")
        titles.append(f"Unreal {clean_game} {scene_type.title()} Moment #{clip_index}")

        # Lint and select the best agent title
        scored_titles = []
        for t in titles:
            lint = TitleLinter.lint_title(t)
            cleaned = TitleLinter.clean_and_format_title(t, game_name=clean_game)
            scored_titles.append((lint["score"], cleaned, lint))

        scored_titles.sort(key=lambda x: x[0], reverse=True)
        best_title = scored_titles[0][1] if scored_titles else f"{clean_game} Highlight #{clip_index} #Shorts"
        alt_titles = [st[1] for st in scored_titles[1:4]]

        # 2. Synthesize Contextual Description
        desc_lines = []
        if primary_quote:
            desc_lines.append(f'"{primary_quote}" - An incredible moment from {clean_game}!')
        elif vlm_summary:
            desc_lines.append(f"Visual highlight: {vlm_summary.strip().capitalize()}.")
        else:
            desc_lines.append(f"High excitement {scene_type.lower()} highlight from {clean_game}!")

        desc_lines.append(f"What would you have done in this situation? Drop a comment below!")
        desc_lines.append(f"Subscribe for more daily {clean_game} highlights & viral clips.")
        if attribution_text:
            desc_lines.append(f"\n{attribution_text}")

        tag_clean = re.sub(r"[^a-zA-Z0-9]", "", clean_game).lower()
        tags = [f"#{tag_clean}", "#gaming", "#shorts", f"#{scene_type.lower()}", "#viral"]

        # 3. Synthesize Contextual Starting Hook Overlay
        hook_overlay = HookEngine.generate_hook_overlay(
            transcript_snippet=transcript_text,
            game_name=clean_game,
            scene_type=scene_type,
            clip_index=clip_index,
            vlm_summary=vlm_summary,
        )

        # 4. Generate Auto-Pinned High-Engagement Question Comment
        engagement_comment = cls.generate_engagement_comment(
            transcript_text=transcript_text,
            game_name=clean_game,
            scene_type=scene_type,
            title=best_title,
        )

        agent_meta = ClipMetadataDTO(
            primary_title=best_title,
            alternative_titles=alt_titles,
            small_description="\n\n".join(desc_lines).strip(),
            tags=tags,
            attribution_text=attribution_text,
        )

        return {
            "clip_index": clip_index,
            "agent_metadata": agent_meta,
            "starting_hook_overlay": hook_overlay,
            "engagement_comment": engagement_comment,
            "top_lint_score": scored_titles[0][0] if scored_titles else 75,
            "extracted_quotes": quotes,
            "source_game": clean_game,
        }

    @classmethod
    def generate_engagement_comment(
        cls,
        transcript_text: str = "",
        game_name: Optional[str] = None,
        scene_type: str = "ACTION",
        title: str = "",
    ) -> str:
        """
        Drafts a high-engagement creator question comment to pin on YouTube Shorts.
        Prompts viewer replies to boost the YouTube Shorts algorithmic velocity.
        """
        game = (game_name or "Gaming").strip().title()
        quotes = cls.extract_salient_quotes(transcript_text, max_words=5)

        if "jason" in transcript_text.lower() or "lucia" in transcript_text.lower():
            return "Did they make the right call here? What would you do in Vice City? Let us know below."
        elif quotes:
            clean_q = quotes[0].rstrip(",.!?")
            return f'When they said "{clean_q}"... what was your honest reaction? Drop it in the comments.'
        elif scene_type.upper() in ("FAIL", "BUSTED"):
            return "Rate this fail from 1 to 10 in the comments."
        elif scene_type.upper() in ("CLUTCH", "VICTORY"):
            return "Could you have survived this play? Honest answers only in the comments."
        else:
            return "What is your honest take on this moment? Drop your thoughts below."

    @classmethod
    def judge_and_select_best_metadata(
        cls,
        agent_synthesis: Dict[str, Any],
        vlm_proposed_meta: Optional[ClipMetadataDTO] = None,
        game_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Judges between VLM-generated metadata and Agent-synthesized metadata.
        Evaluates mobile CTR safety, specificity, lack of generic buzzwords, and title score.
        Returns the winning metadata payload and the rationale for selection.
        """
        agent_meta: ClipMetadataDTO = agent_synthesis["agent_metadata"]
        hook_overlay: str = agent_synthesis.get("starting_hook_overlay", "")

        # If no VLM proposal provided, Agent wins by default
        if not vlm_proposed_meta or not vlm_proposed_meta.primary_title:
            return {
                "winner": "AGENT",
                "reason": "No VLM proposal provided; using Agent synthesized metadata.",
                "selected_metadata": agent_meta,
                "selected_hook_overlay": hook_overlay,
                "agent_score": agent_synthesis.get("top_lint_score", 80),
                "vlm_score": 0,
            }

        # Lint both titles
        vlm_lint = TitleLinter.lint_title(vlm_proposed_meta.primary_title, thumb_text=hook_overlay)
        agent_lint = TitleLinter.lint_title(agent_meta.primary_title, thumb_text=hook_overlay)

        vlm_score = vlm_lint["score"]
        agent_score = agent_lint["score"]

        # Bonus: Give agent credit if it incorporated specific quotes or character names
        reasons: List[str] = []
        if agent_lint["is_mobile_safe"] and not vlm_lint["is_mobile_safe"]:
            agent_score += 15
            reasons.append("Agent title fits mobile character limits (<40 chars) while VLM truncated")

        if len(agent_synthesis.get("extracted_quotes", [])) > 0:
            agent_score += 5
            reasons.append("Agent grounded title in real dialogue quotes")

        # Check for generic boilerplate in VLM (e.g. "INSANE GTA 6 MOMENT!")
        vlm_t = vlm_proposed_meta.primary_title.lower()
        if "moment!" in vlm_t or "highlight #" in vlm_t:
            vlm_score -= 20
            reasons.append("VLM used generic fallback template phrasing")

        if agent_score >= vlm_score:
            winner = "AGENT"
            winning_meta = agent_meta
            rationale = (
                f"Agent metadata chosen ({agent_score} vs {vlm_score} pts). "
                + ("; ".join(reasons) if reasons else "Superior mobile CTR formulation.")
            )
        else:
            winner = "VLM"
            winning_meta = vlm_proposed_meta
            rationale = f"VLM metadata chosen ({vlm_score} vs {agent_score} pts). Strong visual action alignment."

        return {
            "winner": winner,
            "reason": rationale,
            "selected_metadata": winning_meta,
            "selected_hook_overlay": hook_overlay,
            "agent_score": agent_score,
            "vlm_score": vlm_score,
            "vlm_title": vlm_proposed_meta.primary_title,
            "agent_title": agent_meta.primary_title,
        }

    @classmethod
    def export_observation_bundle(
        cls,
        bundle_path: Path | str,
        job_id: str,
        game_name: str,
        clips_data: List[Dict[str, Any]],
    ) -> Path:
        """
        Saves a structured VLM observation manifest for the Agent to inspect and review.
        Enables user to ask in chat: 'Review job X and synthesize titles'.
        """
        p = Path(bundle_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "job_id": job_id,
            "game_name": game_name,
            "clip_count": len(clips_data),
            "clips": clips_data,
        }
        p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return p

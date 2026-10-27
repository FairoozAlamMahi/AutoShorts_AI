"""Algorithmic Hook Scoring & Formulation Engine.
Scores opening lines against 5 retention properties and generates on-screen hook overlays
utilizing proven viral formula frameworks.
"""
from __future__ import annotations

import re
from typing import Optional, List, Dict, Any, Tuple


FILLER_WORDS = {
    "basically", "actually", "literally", "just", "really", "very", "so", "kind", "sort",
    "like", "guys", "hey", "welcome", "today", "video", "subscribe", "channel"
}

VAGUE_WORDS = {
    "amazing", "incredible", "insane", "crazy", "huge", "massive", "gamechanger",
    "secret", "powerful", "ultimate", "best", "revolutionary", "mindblowing", "unbelievable"
}

CONCRETE_REGEX = re.compile(
    r"\b(\d[\d,.]*\s?(%|k|m|x|s|h|hp|kills?|stars?)?|\$\d|\d+\s?(second|minute|hour|day|week|month|year)s?)\b",
    re.IGNORECASE,
)
YOU_REGEX = re.compile(r"\b(you|your|you're|youre|yourself)\b", re.IGNORECASE)
STAKE_REGEX = re.compile(
    r"\b(lose|lost|wasting|waste|quit|fail|broke|cost|risk|before|stop|never|die|dying|dead|wasted|banned|caught)\b",
    re.IGNORECASE,
)
CURIOSITY_REGEX = re.compile(
    r"\b(why|how|what|which|until|before|nobody|almost|except|reason|actually|mistake|secret)\b",
    re.IGNORECASE,
)


class HookEngine:
    """Evaluates opening lines and formulates viral hook overlays."""

    @classmethod
    def words(cls, text: str) -> List[str]:
        return re.findall(r"[a-z0-9'%$.]+", text.lower())

    @classmethod
    def score_specificity(cls, text: str) -> int:
        w = cls.words(text)
        if not w:
            return 0
        nums = len(CONCRETE_REGEX.findall(text))
        vague = sum(1 for x in w if x in VAGUE_WORDS)
        filler = sum(1 for x in w if x in FILLER_WORDS)
        s = 35 + nums * 22 - vague * 16 - filler * 5
        s += min(18, 6 * sum(1 for x in text.split()[1:] if x[:1].isupper()))
        return max(0, min(100, s))

    @classmethod
    def score_address(cls, text: str) -> int:
        w = cls.words(text)
        if not w:
            return 0
        n = len(YOU_REGEX.findall(text))
        first = 30 if YOU_REGEX.search(" ".join(text.split()[:6])) else 0
        return max(0, min(100, 26 + n * 20 + first))

    @classmethod
    def score_stakes(cls, text: str) -> int:
        w = cls.words(text)
        if not w:
            return 0
        n = len(STAKE_REGEX.findall(text))
        has_concrete = 14 if CONCRETE_REGEX.search(text) else 0
        return max(0, min(100, 22 + n * 26 + has_concrete))

    @classmethod
    def score_curiosity(cls, text: str) -> int:
        w = cls.words(text)
        if not w:
            return 0
        n = len(CURIOSITY_REGEX.findall(text))
        q = 18 if text.strip().endswith("?") else 0
        closed = -18 if re.search(r"\b(because|so that|which means)\b", text, re.IGNORECASE) else 0
        return max(0, min(100, 24 + n * 17 + q + closed))

    @classmethod
    def score_brevity(cls, text: str) -> int:
        w = cls.words(text)
        n = len(w)
        if n == 0:
            return 0
        if 5 <= n <= 14:
            return 100
        if n < 5:
            return max(0, 30 + n * 14)
        # Penalize over-long, meandering openings
        return max(0, 100 - (n - 14) * 6)

    @classmethod
    def score_hook(cls, text: str) -> Dict[str, Any]:
        """
        Scores hook on 5 core properties (0-100 each).
        Overall score is 60% mean and 40% weakest link (weakest link failure weighting).
        """
        if not text or not text.strip():
            return {
                "text": "",
                "overall_score": 0,
                "sub_scores": {
                    "specificity": 0, "address": 0, "stakes": 0, "curiosity": 0, "brevity": 0
                },
                "weakest_link": "specificity",
                "verdict": "empty",
            }

        scores = {
            "specificity": cls.score_specificity(text),
            "address": cls.score_address(text),
            "stakes": cls.score_stakes(text),
            "curiosity": cls.score_curiosity(text),
            "brevity": cls.score_brevity(text),
        }
        mean_score = sum(scores.values()) / len(scores)
        weakest_key = min(scores, key=lambda k: scores[k])
        weakest_val = scores[weakest_key]

        overall = round(0.60 * mean_score + 0.40 * weakest_val, 1)
        verdict = "viral_tier" if overall >= 72 else "strong" if overall >= 55 else "needs_hook_overlay"

        return {
            "text": text.strip(),
            "overall_score": overall,
            "sub_scores": scores,
            "weakest_link": weakest_key,
            "verdict": verdict,
        }

    @classmethod
    def _extract_punchy_quote(cls, text: str, max_words: int = 8) -> Optional[str]:
        """Extracts a short, dramatic dialogue fragment from transcript."""
        if not text or not text.strip():
            return None
        # Clean transcript artifacts
        clean = re.sub(r"[^\w\s',!?]", "", text).strip()
        phrases = [p.strip() for p in re.split(r"[,.!?]+", clean) if p.strip()]
        for p in phrases:
            # Strip common conversational lead-ins if present
            lower_p = p.lower()
            for lead in ("they said ", "i said ", "he said ", "she said ", "you know "):
                if lower_p.startswith(lead):
                    p = p[len(lead):].strip()
                    break
            words = p.split()
            if 2 <= len(words) <= max_words:
                return p
            elif len(words) > max_words:
                return " ".join(words[:max_words])
        return None

    @classmethod
    def generate_hook_overlay(
        cls,
        transcript_snippet: str = "",
        game_name: Optional[str] = None,
        scene_type: str = "ACTION",
        clip_index: int = 1,
        vlm_summary: Optional[str] = None,
    ) -> str:
        """
        Produces an on-screen text hook (overlayed in first 2.5s) when spoken opening scores < 65.
        Uses curiosity gap, concrete figures, dialogue anchors, and narrative stakes.
        Guarantees distinct, non-duplicate formulas across clips in a multi-clip campaign.
        """
        g = game_name.strip() if game_name and game_name.strip() else "This"
        st = scene_type.upper()
        quote = cls._extract_punchy_quote(transcript_snippet)

        is_shooter = any(k in g.lower() for k in ("valorant", "cs", "counter", "apex", "fortnite", "cod", "warzone", "overwatch", "siege"))

        candidates: List[str] = []

        # Formula 1: Quote-anchored (Extracts real Whisper dialogue)
        if quote:
            clean_q = quote.rstrip(".,!?")
            candidates.append(f"Before you play {g}, watch how 1 player escaped after \"{clean_q}\"")
            candidates.append(f"Why 99% of players like you would lose after saying \"{clean_q}\" in {g}")

        # Formula 2: Audience consequence & Stakes
        candidates.append(f"Why 99% of players like you would lose after 1 mistake in {g}")

        # Formula 3: Narrative mystery
        candidates.append(f"Before you play {g}, watch what happened when 1 player made this choice")

        # Formula 4: Clutch / Action timing
        if is_shooter:
            candidates.append(f"Before you play {g}, watch how 1 player survived with 1 HP")
            candidates.append(f"Watch how 1 HP and 0 seconds left won this in {g}")
        else:
            candidates.append(f"Before you blink, watch how 1 play in {g} saved you with 0 seconds left")
            candidates.append(f"The 1 {g} getaway that 99% of players like you would fail")

        # Formula 5: Comedy / Fail if applicable
        if "COMEDY" in st or "FAIL" in st:
            candidates.insert(0, f"Before you laugh, watch how 1 mistake lost everything in {g}")

        # Filter candidates that score >= 65
        scored_candidates = []
        for c in candidates:
            res = cls.score_hook(c)
            if res["overall_score"] >= 65:
                scored_candidates.append(c)

        if not scored_candidates:
            scored_candidates = candidates

        # Diverse rotation by clip_index so adjacent clips never share template structures
        rotation_idx = (max(1, clip_index) - 1) % len(scored_candidates)
        return scored_candidates[rotation_idx]

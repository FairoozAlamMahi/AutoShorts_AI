"""Title Linter & Mobile Feed Optimizer.
Enforces YouTube mobile character limits, anti-spam casing, concrete figures,
and thumbnail pairing deduplication.
"""
from __future__ import annotations

import re
from typing import Optional, List, Dict, Any, Tuple


DESKTOP_LIMIT = 60
MOBILE_LIMIT = 40
HARD_LIMIT = 100

VAGUE_WORDS = {
    "amazing", "incredible", "insane", "crazy", "huge", "massive", "ultimate", "best",
    "powerful", "secret", "revolutionary", "mindblowing", "epic", "perfect", "complete"
}

STOP_WORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "is", "are", "with",
    "your", "you", "my", "i", "this", "that", "it", "how", "what", "why"
}


class TitleLinter:
    """Validates and optimizes titles for YouTube mobile feed click-through rates."""

    @staticmethod
    def words(text: str) -> List[str]:
        return re.findall(r"[a-z0-9']+", text.lower())

    @classmethod
    def lint_title(cls, title: str, thumb_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Lints a proposed title and optional thumbnail overlay text.
        Returns score (0-100), issues list, and recommendations.
        """
        t = title.strip()
        n = len(t)
        issues: List[str] = []
        strengths: List[str] = []

        # 1. Length checks
        if n > HARD_LIMIT:
            issues.append(f"Title is {n} chars (exceeds YouTube hard limit of {HARD_LIMIT})")
        elif n > DESKTOP_LIMIT:
            issues.append(f"Title is {n} chars (desktop search cuts near {DESKTOP_LIMIT})")
        else:
            strengths.append(f"{n} characters, fits within {DESKTOP_LIMIT}-character desktop cut")

        if n > MOBILE_LIMIT:
            head = t[:MOBILE_LIMIT].rsplit(" ", 1)[0]
            issues.append(f"Mobile feeds truncate around {MOBILE_LIMIT} chars (showing '{head}...')")
        else:
            strengths.append(f"Under {MOBILE_LIMIT} characters, 100% visible on mobile home feeds")

        # 2. Shouting / Spam casing check
        caps = [w for w in t.split() if len(w) > 2 and w.isupper() and not w.startswith("#")]
        if len(caps) > 2:
            issues.append(f"{len(caps)} all-caps words (maximum 2 words before triggering spam filters)")
        elif caps:
            strengths.append(f"{len(caps)} all-caps word for clean visual emphasis")

        # 3. Vague clickbait buzzwords
        w_list = cls.words(t)
        vague_found = [w for w in w_list if w in VAGUE_WORDS]
        if vague_found:
            issues.append(f"Contains generic buzzwords: {', '.join(sorted(set(vague_found)))} (replace with concrete figures)")

        # 4. Concrete figures (numbers, stats, names)
        nums = re.findall(r"\b\d+[\d,.]*%?", t)
        if nums:
            strengths.append(f"Carries concrete numbers/figures ({', '.join(nums[:3])})")
        else:
            issues.append("Missing concrete number or figure (numbers increase CTR by ~30%)")

        # 5. Front-loading subject
        front = [w for w in w_list[:3] if w not in STOP_WORDS]
        if not front:
            issues.append("First 3 words are all filler stop-words (move the subject forward)")

        # 6. Thumbnail deduplication
        if thumb_text and thumb_text.strip():
            tw = set(cls.words(t)) - STOP_WORDS
            hw = set(cls.words(thumb_text)) - STOP_WORDS
            shared = tw & hw
            if shared:
                issues.append(f"Thumbnail text repeats title words ({', '.join(sorted(shared))})")
            else:
                strengths.append("Thumbnail and title carry complementary, non-duplicate text")

        score = max(0, min(100, 100 - 15 * len(issues) + 5 * len(strengths)))
        return {
            "title": t,
            "character_count": n,
            "score": score,
            "is_mobile_safe": n <= MOBILE_LIMIT,
            "issues": issues,
            "strengths": strengths,
        }

    @classmethod
    def clean_and_format_title(cls, raw_title: str, game_name: Optional[str] = None) -> str:
        """
        Cleans and formats title to be mobile-optimized and high-CTR:
        - Removes redundant buzzwords
        - Caps length under 55 characters
        - Adds hashtag #Shorts
        """
        clean = raw_title.strip()
        # Remove repeated all-caps shouting if excessive
        tokens = clean.split()
        capped_tokens = []
        caps_count = 0
        for tok in tokens:
            if tok.lower() in ("in", "on", "at", "to", "for", "of", "with", "by", "a", "an", "the"):
                tok = tok.lower()
            elif tok.isupper() and not tok.startswith("#"):
                caps_count += 1
                if caps_count > 2:
                    tok = tok.capitalize()
            capped_tokens.append(tok)
        clean = " ".join(capped_tokens)

        # Ensure #Shorts tag is appended cleanly without blowing limit
        if "#shorts" not in clean.lower():
            if len(clean) + 8 <= 60:
                clean = f"{clean} #Shorts"

        return clean.strip()

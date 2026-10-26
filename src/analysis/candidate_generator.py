"""Candidate generator with adaptive multi-modal weighting, zero jump-cut envelopes, and NMS."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple, Dict
import numpy as np

from ..config.schema import DiscoveryMode, PreRunToggles
from ..core.dto import CandidateClipDTO, TranscriptDTO


GAMING_REACTION_KEYWORDS = [
    r"\bclutch\b", r"\bno\s*way\b", r"\binsane\b", r"\blet'?s\s*go\b",
    r"\bone\s*hp\b", r"\bdead\b", r"\bomg\b", r"\bace\b",
    r"\bheadshot\b", r"\bpenta\b", r"\bkill\b", r"\bwin\b",
    r"\bwasted\b", r"\bholy\b", r"\bunbelievable\b"
]


class CandidateGenerator:
    """Discovers peak highlight moments and builds continuous setup-to-payoff clip windows."""

    @classmethod
    def calculate_speech_timeline(cls, transcript: TranscriptDTO, grid_len: int) -> np.ndarray:
        """Calculates speech excitement timeline based on words-per-second and reaction keywords."""
        if transcript.is_skipped or not transcript.segments:
            return np.zeros(grid_len, dtype=np.float32)

        speech_scores = np.zeros(grid_len, dtype=np.float32)

        for seg in transcript.segments:
            seg_text = seg.text.lower()
            keyword_bonus = 0.0
            for pat in GAMING_REACTION_KEYWORDS:
                if re.search(pat, seg_text):
                    keyword_bonus += 0.35

            for w in seg.words:
                sec_idx = min(grid_len - 1, max(0, int(w.start_sec)))
                speech_scores[sec_idx] += 1.0 + keyword_bonus

        ptp = np.ptp(speech_scores)
        if ptp > 1e-6:
            return ((speech_scores - np.min(speech_scores)) / ptp).astype(np.float32)
        return np.zeros(grid_len, dtype=np.float32)

    @classmethod
    def generate_candidates(
        cls,
        toggles: PreRunToggles,
        total_duration_sec: float,
        acoustic_scores: Optional[np.ndarray] = None,
        visual_scores: Optional[np.ndarray] = None,
        transcript: Optional[TranscriptDTO] = None,
    ) -> List[CandidateClipDTO]:
        """
        Orchestrates highlight selection across MANUAL_ONLY, FULL_AUTO, and HYBRID modes.
        """
        grid_len = max(1, int(np.ceil(total_duration_sec)))

        # Mode 1: MANUAL_ONLY
        if toggles.discovery_mode == DiscoveryMode.MANUAL_ONLY:
            return cls._generate_manual_candidates(toggles, total_duration_sec)

        # Ensure signal arrays match grid_len
        a_scores = acoustic_scores if acoustic_scores is not None and len(acoustic_scores) == grid_len else np.zeros(grid_len, dtype=np.float32)
        v_scores = visual_scores if visual_scores is not None and len(visual_scores) == grid_len else np.zeros(grid_len, dtype=np.float32)

        # Check speech coverage for adaptive weighting
        has_transcript = transcript is not None and not transcript.is_skipped and transcript.total_words > 0
        use_speech = toggles.transcription_enabled and toggles.use_speech_scoring and has_transcript

        if use_speech and transcript is not None and transcript.speech_coverage_ratio >= 0.15:
            # Commentary weighting
            s_scores = cls.calculate_speech_timeline(transcript, grid_len)
            composite = 0.40 * s_scores + 0.30 * a_scores + 0.30 * v_scores
        else:
            # Pure gameplay action weighting (speechless or speech scoring off)
            s_scores = np.zeros(grid_len, dtype=np.float32)
            composite = 0.55 * a_scores + 0.45 * v_scores

        # Handle Mode 2 (FULL_AUTO) vs Mode 3 (HYBRID)
        existing_windows: List[Tuple[float, float]] = []
        locked_candidates: List[CandidateClipDTO] = []

        if toggles.discovery_mode == DiscoveryMode.HYBRID:
            locked_candidates = cls._generate_manual_candidates(toggles, total_duration_sec)
            for c in locked_candidates:
                existing_windows.append((c.start_sec, c.end_sec))

        needed_auto = max(0, toggles.target_clip_count - len(locked_candidates))
        if needed_auto == 0:
            return locked_candidates

        auto_candidates = cls._find_peaks_and_expand_envelopes(
            composite=composite,
            a_scores=a_scores,
            v_scores=v_scores,
            s_scores=s_scores,
            total_duration_sec=total_duration_sec,
            target_count=needed_auto,
            toggles=toggles,
            existing_windows=existing_windows,
            transcript=transcript,
        )

        all_clips = locked_candidates + auto_candidates
        # Re-index clips sequentially
        for idx, c in enumerate(all_clips, start=1):
            c.clip_index = idx

        return all_clips

    @classmethod
    def _generate_manual_candidates(
        cls, toggles: PreRunToggles, total_duration_sec: float
    ) -> List[CandidateClipDTO]:
        candidates: List[CandidateClipDTO] = []
        for idx, m in enumerate(toggles.manual_timestamps, start=1):
            start = max(0.0, m.start_sec)
            end = min(total_duration_sec, m.end_sec)
            dur = max(0.1, end - start)
            candidates.append(CandidateClipDTO(
                clip_index=idx,
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                duration_sec=round(dur, 3),
                peak_timestamp_sec=round((start + end) / 2.0, 3),
                composite_score=1.0,
                is_manual=True,
                reason=m.label or "Manual user selection",
                sub_scores={"manual": 1.0},
            ))
        return candidates

    @classmethod
    def _find_peaks_and_expand_envelopes(
        cls,
        composite: np.ndarray,
        a_scores: np.ndarray,
        v_scores: np.ndarray,
        s_scores: np.ndarray,
        total_duration_sec: float,
        target_count: int,
        toggles: PreRunToggles,
        existing_windows: List[Tuple[float, float]],
        transcript: Optional[TranscriptDTO] = None,
    ) -> List[CandidateClipDTO]:
        grid_len = len(composite)
        candidates: List[CandidateClipDTO] = []
        occupied_windows = list(existing_windows)

        # Sort peak indices by composite score descending
        sorted_indices = np.argsort(composite)[::-1]

        for peak_sec in sorted_indices:
            peak_val = float(composite[peak_sec])
            if len(candidates) >= target_count:
                break

            # Envelope expansion: pre-roll and post-roll
            raw_start = max(0.0, float(peak_sec) - toggles.pre_roll_sec)
            raw_end = min(total_duration_sec, float(peak_sec) + toggles.post_roll_sec)

            # Snap to sentence start if transcript exists
            if transcript and transcript.segments:
                for seg in transcript.segments:
                    if abs(seg.start_sec - raw_start) <= 2.5:
                        raw_start = max(0.0, seg.start_sec)
                        break

            # Enforce duration bounds
            duration = raw_end - raw_start
            if duration < toggles.min_duration_sec:
                # Expand around peak (60% buildup, 40% payoff/reaction)
                deficit = toggles.min_duration_sec - duration
                left_expand = deficit * 0.6
                right_expand = deficit * 0.4
                new_start = max(0.0, raw_start - left_expand)
                unabsorbed_left = left_expand - (raw_start - new_start)
                new_end = min(total_duration_sec, raw_end + right_expand + unabsorbed_left)
                unabsorbed_right = (raw_end + right_expand + unabsorbed_left) - new_end
                if unabsorbed_right > 0:
                    new_start = max(0.0, new_start - unabsorbed_right)
                raw_start, raw_end = new_start, new_end
                duration = raw_end - raw_start

            if duration > toggles.max_duration_sec:
                raw_end = raw_start + toggles.max_duration_sec
                duration = toggles.max_duration_sec

            # NMS check against occupied windows
            conflict = False
            for w_start, w_end in occupied_windows:
                # Check overlap or gap < min_gap_sec
                if not (raw_end + toggles.min_gap_sec <= w_start or raw_start >= w_end + toggles.min_gap_sec):
                    conflict = True
                    break

            if conflict:
                continue

            occupied_windows.append((raw_start, raw_end))
            candidates.append(CandidateClipDTO(
                clip_index=len(candidates) + 1,
                start_sec=round(raw_start, 3),
                end_sec=round(raw_end, 3),
                duration_sec=round(duration, 3),
                peak_timestamp_sec=round(float(peak_sec), 3),
                acoustic_score=round(float(a_scores[peak_sec]), 3),
                visual_score=round(float(v_scores[peak_sec]), 3),
                speech_score=round(float(s_scores[peak_sec]), 3),
                composite_score=round(peak_val, 3),
                is_manual=False,
                reason=f"Auto peak discovery at {peak_sec}s",
                sub_scores={
                    "acoustic": round(float(a_scores[peak_sec]), 3),
                    "visual": round(float(v_scores[peak_sec]), 3),
                    "speech": round(float(s_scores[peak_sec]), 3),
                },
            ))

        # Sort candidates chronologically
        candidates.sort(key=lambda c: c.start_sec)
        return candidates

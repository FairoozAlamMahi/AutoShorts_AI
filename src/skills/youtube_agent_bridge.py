"""
YouTube Agent Skills Bridge Module
Exposes clean, programmatic Python APIs for the 6 core intelligence tools:
- hookscore.py (21-formula 5-property hook scorer)
- title.py (Title + thumbnail pairing linter)
- deadair.py (Dead-air, filler, and retake detector)
- swipe.py (Own-channel median multiple outlier detector)
- retention.py (Studio audience-retention leak auditor)
- chapters.py (Rule-compliant chapter generator)
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import importlib.util
import json
import os
import sys

SKILLS_DIR = Path(__file__).parent.resolve()


@dataclass
class HookScoreResult:
    hook: str
    verdict_score: int
    band: str  # STRONG, WORKABLE, WEAK
    formula_name: str
    formula_hits: int
    properties: Dict[str, int]
    weakest_property: str
    suggested_fix: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hook": self.hook,
            "score": self.verdict_score,
            "band": self.band,
            "formula": self.formula_name,
            "formula_hits": self.formula_hits,
            "properties": self.properties,
            "weakest": self.weakest_property,
            "fix": self.suggested_fix,
        }


@dataclass
class TitleLintResult:
    title: str
    thumbnail_text: Optional[str]
    char_count: int
    score: int
    issues: List[Dict[str, str]]
    good_points: List[str]
    mobile_safe: bool
    desktop_safe: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "thumbnail_text": self.thumbnail_text,
            "chars": self.char_count,
            "score": self.score,
            "issues": self.issues,
            "good": self.good_points,
            "mobile_safe": self.mobile_safe,
            "desktop_safe": self.desktop_safe,
        }


@dataclass
class DeadAirResult:
    source_path: str
    duration_sec: float
    cuts_count: int
    removed_sec: float
    output_duration_sec: float
    percent_shortened: float
    cuts: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source_path,
            "duration": self.duration_sec,
            "cuts_count": self.cuts_count,
            "removed_sec": self.removed_sec,
            "output_duration": self.output_duration_sec,
            "percent_shortened": self.percent_shortened,
            "cuts": self.cuts,
        }


@dataclass
class ViralOutlierResult:
    total_videos: int
    total_channels: int
    outliers: List[Dict[str, Any]]
    skipped_thin_channels: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_videos": self.total_videos,
            "total_channels": self.total_channels,
            "outliers": self.outliers,
            "skipped_thin": self.skipped_thin_channels,
        }


@dataclass
class RetentionAuditResult:
    data_points: int
    start_percent: float
    end_percent: float
    hook_leak: float
    hook_verdict: str  # healthy, leaking, severe
    cliffs: List[Dict[str, Any]]
    slide_per_unit: float
    said_at_cliffs: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": self.data_points,
            "start_pct": self.start_percent,
            "end_pct": self.end_percent,
            "hook_leak": self.hook_leak,
            "hook_verdict": self.hook_verdict,
            "cliffs": self.cliffs,
            "slide": self.slide_per_unit,
            "said": self.said_at_cliffs,
        }


class YouTubeAgentBridge:
    """Unified bridge for all YouTube agent skills tools."""

    def __init__(self):
        self._ensure_paths()

    def _ensure_paths(self):
        # Allow inter-tool imports
        yt_edit_dir = str(SKILLS_DIR / "yt-edit")
        if yt_edit_dir not in sys.path:
            sys.path.insert(0, yt_edit_dir)

    def score_hook(self, hook_text: str) -> HookScoreResult:
        """Evaluates a hook against the 21 formulas and 5 core properties."""
        script_dir = SKILLS_DIR / "yt-script"
        hookscore_path = script_dir / "hookscore.py"
        spec = importlib.util.spec_from_file_location("hookscore", str(hookscore_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        parts, verdict, name, hits = mod.score(hook_text)
        band_str = mod.band(verdict)
        low_key = min(parts, key=parts.get)
        fix_text = mod.FIX.get(low_key, "Review hook clarity and audience focus.")

        return HookScoreResult(
            hook=hook_text.strip(),
            verdict_score=int(verdict),
            band=band_str,
            formula_name=name,
            formula_hits=int(hits),
            properties={k: int(v) for k, v in parts.items()},
            weakest_property=low_key,
            suggested_fix=fix_text,
        )

    def rank_hooks(self, hooks: List[str]) -> List[HookScoreResult]:
        """Scores and ranks a list of hook candidates from highest to lowest score."""
        results = [self.score_hook(h) for h in hooks if h.strip()]
        results.sort(key=lambda r: -r.verdict_score)
        return results

    def lint_title_and_thumbnail(self, title: str, thumbnail_text: Optional[str] = None) -> TitleLintResult:
        """Lints title and thumbnail pairing for length, mobile truncation, and duplication."""
        pkg_dir = SKILLS_DIR / "yt-package"
        title_mod_path = pkg_dir / "title.py"
        spec = importlib.util.spec_from_file_location("title_linter", str(title_mod_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        res = mod.check(title, thumbnail_text)
        issues_list = [{"kind": k, "message": m} for k, m in res.get("issues", [])]
        good_list = res.get("good", [])

        chars = res.get("chars", len(title))
        mobile_safe = chars <= mod.MOBILE
        desktop_safe = chars <= mod.DESKTOP

        return TitleLintResult(
            title=title.strip(),
            thumbnail_text=thumbnail_text.strip() if thumbnail_text else None,
            char_count=chars,
            score=int(res.get("score", 0)),
            issues=issues_list,
            good_points=good_list,
            mobile_safe=mobile_safe,
            desktop_safe=desktop_safe,
        )

    def detect_dead_air(self, transcript_path: Path | str, floor: float = 0.45) -> DeadAirResult:
        """Analyzes transcript (.srt, .vtt, or Whisper .json) for dead-air gaps, fillers, and retakes."""
        p = Path(transcript_path).resolve()
        edit_dir = SKILLS_DIR / "yt-edit"
        deadair_path = edit_dir / "deadair.py"
        spec = importlib.util.spec_from_file_location("deadair", str(deadair_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        cues = mod.load(str(p))
        if not cues:
            return DeadAirResult(str(p), 0.0, 0, 0.0, 0.0, 0.0, [])

        dur = cues[-1][1]
        cuts = []
        for i, (s, e, t) in enumerate(cues):
            if mod.FILLER_ONLY.match(t):
                cuts.append({"kind": "FILLER", "start": s, "end": e, "why": t.strip()[:48]})
            if i:
                gap = s - cues[i - 1][1]
                if gap > floor:
                    keep = floor / 2
                    cuts.append({
                        "kind": "DEAD",
                        "start": round(cues[i - 1][1] + keep, 3),
                        "end": round(s - keep, 3),
                        "why": f"{gap:.2f}s gap"
                    })
            if t.strip() and not mod.FILLER_ONLY.match(t):
                j = i - 1
                while j >= 0 and (mod.FILLER_ONLY.match(cues[j][2]) or not cues[j][2].strip()):
                    j -= 1
                if j >= 0:
                    a1, b1 = mod.norm(cues[j][2])[:5], mod.norm(t)[:5]
                    if len(a1) >= 3 and a1 == b1:
                        cuts.append({
                            "kind": "REPEAT",
                            "start": cues[j][0],
                            "end": cues[j][1],
                            "why": f'restart of "{" ".join(a1)}"'
                        })

        cuts = [c for c in cuts if c["end"] > c["start"]]
        cuts.sort(key=lambda c: c["start"])
        removed = sum(c["end"] - c["start"] for c in cuts)
        out_dur = max(0.0, dur - removed)
        pct = (removed / dur * 100.0) if dur > 0 else 0.0

        return DeadAirResult(
            source_path=str(p),
            duration_sec=round(dur, 2),
            cuts_count=len(cuts),
            removed_sec=round(removed, 2),
            output_duration_sec=round(out_dur, 2),
            percent_shortened=round(pct, 1),
            cuts=cuts,
        )

    def find_viral_outliers(self, collected_json_path: Path | str, min_multiple: float = 1.5) -> ViralOutlierResult:
        """Finds videos that outperformed their own channel median by at least min_multiple."""
        p = Path(collected_json_path).resolve()
        viral_dir = SKILLS_DIR / "yt-viral"
        swipe_path = viral_dir / "swipe.py"
        spec = importlib.util.spec_from_file_location("swipe", str(swipe_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        rows = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("videos", [])

        import statistics
        by = {}
        for r in rows:
            by.setdefault(r.get("channel", "?"), []).append(r)

        outliers, thin = [], []
        for ch, vids in by.items():
            views = [float(v.get("views", 0) or 0) for v in vids]
            med = statistics.median(views) if views else 0
            if len(vids) < 4:
                thin.append({"channel": ch, "count": len(vids)})
                continue
            for v in vids:
                v_count = float(v.get("views", 0) or 0)
                m = (v_count / med) if med else 0
                if m >= min_multiple:
                    outliers.append({
                        "channel": ch,
                        "title": v.get("title", ""),
                        "views": int(v_count),
                        "median": int(med),
                        "multiple": round(m, 2),
                        "formula": mod.classify(v.get("title", "")),
                        "url": v.get("url", ""),
                    })

        outliers.sort(key=lambda r: -r["multiple"])
        return ViralOutlierResult(
            total_videos=len(rows),
            total_channels=len(by),
            outliers=outliers,
            skipped_thin_channels=thin,
        )

    def audit_retention(
        self,
        csv_path: Path | str,
        transcript_path: Optional[Path | str] = None,
        duration_sec: Optional[float] = None
    ) -> RetentionAuditResult:
        """Audits YouTube Studio audience-retention CSV export."""
        p = Path(csv_path).resolve()
        ret_dir = SKILLS_DIR / "yt-retention"
        ret_path = ret_dir / "retention.py"
        spec = importlib.util.spec_from_file_location("retention", str(ret_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        rows = mod.load_csv(str(p))
        if len(rows) < 8:
            raise ValueError(f"Could not read at least 8 data points from {csv_path}")

        xs = [r[0] for r in rows]
        ys = [r[1] for r in rows]
        pct_axis = max(xs) <= 100.5
        dur = duration_sec

        def at(x):
            return (x / 100.0 * dur) if (pct_axis and dur) else x

        start = ys[0] or 100.0
        cutoff = 30.0 if not pct_axis else (30.0 / dur * 100 if dur else 10.0)
        hook_end = min((y for x, y in rows if x <= cutoff), default=start)
        hook_leak = start - hook_end

        drops = []
        for i in range(1, len(rows)):
            d = ys[i - 1] - ys[i]
            span = xs[i] - xs[i - 1] or 1
            drops.append((d / span, xs[i - 1], xs[i], d))
        drops.sort(reverse=True)

        cliffs = [
            {
                "from": round(a1, 2),
                "to": round(b1, 2),
                "lost": round(d, 2),
                "at_seconds": round(at(a1), 1) if (not pct_axis or dur) else None
            }
            for _, a1, b1, d in drops[:5] if d > 0.8
        ]

        mid = [d for d, x0, _, _ in [(r[0], r[1], r[2], r[3]) for r in drops] if x0 > cutoff]
        slide = sum(mid) / len(mid) if mid else 0.0

        said = {}
        if transcript_path and Path(transcript_path).exists():
            edit_dir = SKILLS_DIR / "yt-edit"
            deadair_path = edit_dir / "deadair.py"
            spec_da = importlib.util.spec_from_file_location("deadair_cues", str(deadair_path))
            mod_da = importlib.util.module_from_spec(spec_da)
            spec_da.loader.exec_module(mod_da)
            cues = mod_da.load(str(Path(transcript_path).resolve()))
            for c in cliffs:
                if c["at_seconds"] is not None:
                    t = c["at_seconds"]
                    near = [q[2] for q in cues if q[0] <= t + 4 and q[1] >= t - 4]
                    said[str(c["from"])] = " ".join(near)[:140]

        verdict = "healthy" if hook_leak < 25 else "leaking" if hook_leak < 40 else "severe"

        return RetentionAuditResult(
            data_points=len(rows),
            start_percent=round(start, 1),
            end_percent=round(ys[-1], 1),
            hook_leak=round(hook_leak, 2),
            hook_verdict=verdict,
            cliffs=cliffs,
            slide_per_unit=round(slide, 3),
            said_at_cliffs=said,
        )


# Global singleton instance
youtube_agent = YouTubeAgentBridge()

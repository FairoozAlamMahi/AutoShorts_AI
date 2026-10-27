"""JobOrchestrator - Complete resumable pipeline runner with Dynamic Stage Bypass Router."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import numpy as np

from .dto import (
    JobRequestDTO,
    JobStatusDTO,
    MediaInspectionDTO,
    YouTubeMetadataDTO,
    TranscriptDTO,
    CandidateClipDTO,
    ClipMetadataDTO,
    ProvenanceDTO,
)
from .database import DatabaseManager
from .resource_guard import ResourceGuard
from ..config.schema import (
    DiscoveryMode,
    CaptionMode,
    LayoutMode,
    MetadataMode,
    PreRunToggles,
    FacecamPosition,
    CaptionTheme,
)
from ..providers.registry import ModelRegistry
from ..ingest.media_inspector import MediaInspector
from ..ingest.youtube_fetcher import YouTubeFetcher
from ..ingest.rights_manager import RightsManager
from ..transcription.service import TranscriptionService
from ..transcription.editor import TranscriptEditor
from ..analysis.audio_signals import AudioSignalAnalyzer
from ..analysis.visual_signals import VisualSignalAnalyzer
from ..analysis.candidate_generator import CandidateGenerator
from ..analysis.scene_classifier import MultimodalSceneClassifier, NarrativeBoundaryRefiner
from ..captions.phrase_chunker import PhraseChunker
from ..captions.ass_compiler import ASSCompiler
from ..captions.sidecar_exporter import SidecarExporter
from ..rendering.ffmpeg_renderer import FFmpegRenderer
from ..metadata.service import MetadataService
from ..analytics.hook_engine import HookEngine
from ..analytics.title_linter import TitleLinter
from ..analytics.agent_copilot import AgentCoPilotSynthesizer
from ..core.channel_playbook import ChannelPlaybook


class JobOrchestrator:
    """Coordinates pipeline execution across all stages with dynamic pre-run bypasses."""

    def __init__(
        self,
        db: DatabaseManager,
        resource_guard: ResourceGuard,
        model_registry: ModelRegistry,
        scratch_dir: Path | str = "data/scratch",
        export_dir: Path | str = "data/exports",
        ffmpeg_renderer: Optional[FFmpegRenderer] = None,
        playbook: Optional[ChannelPlaybook] = None,
    ) -> None:
        self.db = db
        self.resource_guard = resource_guard
        self.model_registry = model_registry
        self.scratch_dir = Path(scratch_dir).resolve()
        self.export_dir = Path(export_dir).resolve()
        self.inspector = MediaInspector()
        self.yt_fetcher = YouTubeFetcher()
        self.renderer = ffmpeg_renderer or FFmpegRenderer()
        self.playbook = playbook or ChannelPlaybook(playbook_path=self.scratch_dir.parent / "channel_playbook.json")

    @staticmethod
    def _classify_error(stage: str, err: Exception) -> str:
        msg = str(err).lower()
        if "stage_1" in stage.lower() or "ingest" in stage.lower():
            if "not found" in msg or "filenotfound" in msg:
                return "ERR_INGEST_FILE_NOT_FOUND"
            elif "corrupt" in msg or "moov" in msg or "invalid media" in msg:
                return "ERR_INGEST_MEDIA_CORRUPT"
            elif any(k in msg for k in ("youtube", "yt-dlp", "reloaded", "requested format", "sign in")):
                return "ERR_INGEST_YOUTUBE_FETCH"
            return "ERR_STAGE_1_INGEST"
        elif "stage_2" in stage.lower() or "transcription" in stage.lower():
            if "out of memory" in msg or "cuda" in msg:
                return "ERR_TRANSCRIPTION_GPU_OOM"
            return "ERR_STAGE_2_TRANSCRIPTION"
        elif "stage_3" in stage.lower() or "signal" in stage.lower():
            return "ERR_STAGE_3_SIGNAL_ANALYSIS"
        elif "stage_4" in stage.lower() or "candidate" in stage.lower():
            return "ERR_STAGE_4_CANDIDATE_DISCOVERY"
        elif "stage_5" in stage.lower() or "metadata" in stage.lower():
            return "ERR_STAGE_5_METADATA_GENERATION"
        elif "stage_6" in stage.lower() or "render" in stage.lower():
            if "encoder" in msg or "nvenc" in msg:
                return "ERR_RENDER_NVENC_ENCODER"
            return "ERR_STAGE_6_7_RENDERING"
        return "ERR_PIPELINE_GENERAL"

    def run_job(
        self,
        request: JobRequestDTO,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> List[Path]:
        """
        Executes the video pipeline honoring all PreRunToggles bypass rules.
        Returns the list of generated .mp4 clip paths.
        """
        job_id = request.job_id
        toggles = request.toggles
        self.db.create_job(request)

        current_stage = "INITIALIZED"
        current_pct = 5.0

        def _notify(stage: str, pct: float) -> None:
            nonlocal current_stage, current_pct
            current_stage = stage
            current_pct = pct
            self.db.update_job_status(job_id=job_id, status="RUNNING", stage=stage, progress_pct=pct)
            if progress_callback:
                progress_callback(stage, pct)

        try:
            _notify("INITIALIZED", 5.0)

            # -------------------------------------------------------------
            # Stage 1: Ingest & Media Inspect (Never bypassed)
            # -------------------------------------------------------------
            _notify("STAGE_1_INGEST", 10.0)
            source_input = request.source_path_or_url
            yt_meta: Optional[YouTubeMetadataDTO] = None
            source_file_path: Path

            if self.yt_fetcher.is_youtube_url(source_input):
                yt_meta = self.yt_fetcher.fetch_metadata(source_input)
                source_file_path = self.yt_fetcher.download_video(
                    url=source_input,
                    output_dir=self.scratch_dir,
                    job_id=job_id,
                )
            else:
                source_file_path = Path(source_input).resolve()
                if not source_file_path.exists():
                    raise FileNotFoundError(f"Source video not found: {source_file_path}")

            inspection = self.inspector.inspect(source_file_path)
            sha_prefix = self.inspector.compute_sha256_prefix(source_file_path)
            self.db.register_source(
                source_id=job_id,
                file_path_or_url=str(source_file_path),
                sha256_prefix=sha_prefix,
                inspection=inspection,
                yt_meta=yt_meta,
            )

            # -------------------------------------------------------------
            # Stage 2: Speech Transcription (Dynamic Bypass & Checkpoint)
            # -------------------------------------------------------------
            transcript: TranscriptDTO
            transcript_cache = self.scratch_dir / job_id / "transcript.json"
    
            if toggles.should_run_transcription():
                if transcript_cache.exists():
                    _notify("STAGE_2_TRANSCRIPTION_CACHED", 25.0)
                    try:
                        transcript = TranscriptDTO.model_validate_json(transcript_cache.read_text(encoding="utf-8"))
                    except Exception:
                        transcript = TranscriptDTO(segments=[], is_skipped=True)
                else:
                    _notify("STAGE_2_TRANSCRIPTION", 25.0)
                    try:
                        stt_provider = self.model_registry.create_stt_provider()
                        transcriber = TranscriptionService(
                            provider=stt_provider,
                            resource_guard=self.resource_guard,
                            scratch_dir=self.scratch_dir,
                        )
                        transcript = transcriber.transcribe_video(source_file_path, job_id=job_id)
                        transcript_cache.parent.mkdir(parents=True, exist_ok=True)
                        transcript_cache.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
                    except Exception:
                        transcript = TranscriptDTO(segments=[], is_skipped=True)
            else:
                _notify("STAGE_2_TRANSCRIPTION_BYPASSED", 25.0)
                transcript = TranscriptDTO(segments=[], is_skipped=True)
    
            # -------------------------------------------------------------
            # Stage 3: Audio/Visual Signal Analysis (Dynamic Bypass & Checkpoint)
            # -------------------------------------------------------------
            a_scores = None
            v_scores = None
            signals_cache = self.scratch_dir / job_id / "signals_cache.json"
    
            if toggles.should_run_signal_analysis():
                if signals_cache.exists():
                    _notify("STAGE_3_SIGNAL_ANALYSIS_CACHED", 45.0)
                    try:
                        sig_data = json.loads(signals_cache.read_text(encoding="utf-8"))
                        a_scores = np.array(sig_data["a_scores"], dtype=np.float32) if sig_data.get("a_scores") else None
                        v_scores = np.array(sig_data["v_scores"], dtype=np.float32) if sig_data.get("v_scores") else None
                    except Exception:
                        a_scores, v_scores = None, None
    
                if a_scores is None and v_scores is None:
                    _notify("STAGE_3_SIGNAL_ANALYSIS", 45.0)
                    # Audio signals
                    if inspection.has_audio:
                        wav_path = self.scratch_dir / job_id / "audio_signals.wav"
                        TranscriptionService(provider=None).extract_audio(source_file_path, wav_path)
                        a_scores, _ = AudioSignalAnalyzer.analyze_audio_timeline(wav_path, inspection.duration_sec)
    
                    # Visual signals
                    v_analyzer = VisualSignalAnalyzer()
                    v_scores = v_analyzer.analyze_video_timeline(source_file_path, inspection.duration_sec)
    
                    try:
                        signals_cache.parent.mkdir(parents=True, exist_ok=True)
                        signals_cache.write_text(
                            json.dumps({
                                "a_scores": a_scores.tolist() if a_scores is not None else [],
                                "v_scores": v_scores.tolist() if v_scores is not None else [],
                            }),
                            encoding="utf-8"
                        )
                    except Exception:
                        pass
            else:
                _notify("STAGE_3_SIGNAL_ANALYSIS_BYPASSED", 45.0)
    
            # -------------------------------------------------------------
            # Stage 4: Candidate Selection, Boundary Refinement & VLM Check
            # -------------------------------------------------------------
            _notify("STAGE_4_CANDIDATE_DISCOVERY", 60.0)
            candidates = CandidateGenerator.generate_candidates(
                toggles=toggles,
                total_duration_sec=inspection.duration_sec,
                acoustic_scores=a_scores,
                visual_scores=v_scores,
                transcript=transcript,
            )

            # Snap candidate boundaries to complete sentences / speech phrases
            for c in candidates:
                if not c.is_manual and transcript and not transcript.is_skipped:
                    c.start_sec, c.end_sec, _ = NarrativeBoundaryRefiner.refine_bounds(
                        raw_start=c.start_sec,
                        raw_end=c.end_sec,
                        transcript=transcript,
                        min_duration_sec=toggles.min_duration_sec,
                        max_duration_sec=toggles.max_duration_sec,
                        total_duration_sec=inspection.duration_sec,
                    )
                    c.duration_sec = round(c.end_sec - c.start_sec, 3)

                clip_tr = TranscriptEditor.slice_transcript_for_window(transcript, c.start_sec, c.end_sec)
                c.transcript_snippet = clip_tr.full_text[:200]

            # Optional VLM Keyframe Verification & Scene Analysis
            vlm_results: Dict[int, Any] = {}
            if toggles.should_run_vlm():
                _notify("STAGE_4_VLM_VERIFICATION", 68.0)
                try:
                    vlm_prov = self.model_registry.create_vlm_provider()
                except Exception:
                    vlm_prov = None

                for c in candidates:
                    kf_dir = self.scratch_dir / job_id / f"keyframes_clip_{c.clip_index}"
                    kf_dir.mkdir(parents=True, exist_ok=True)
                    kf_times = [
                        c.start_sec + min(2.0, c.duration_sec * 0.2),
                        c.peak_timestamp_sec,
                        max(c.start_sec, c.end_sec - min(2.0, c.duration_sec * 0.2)),
                    ]
                    k_paths = []
                    for k_idx, kt in enumerate(kf_times):
                        k_path = kf_dir / f"kf_{k_idx}.jpg"
                        try:
                            self.renderer.generate_thumbnail(source_file_path, k_path, timestamp_sec=kt)
                            if k_path.exists():
                                k_paths.append(str(k_path))
                        except Exception:
                            pass
                    c.keyframe_paths = k_paths

                    if vlm_prov and k_paths:
                        try:
                            v_analysis = vlm_prov.inspect_keyframes(
                                frame_paths=k_paths,
                                prompt_context=f"Game: {toggles.game_name_context or 'Gaming'}. Dialogue: {c.transcript_snippet}",
                            )
                            c.vlm_score = v_analysis.clutch_confidence
                            vlm_results[c.clip_index] = v_analysis
                        except Exception:
                            c.vlm_score = 0.85
                    else:
                        c.vlm_score = 0.85

            # Classify scene & resolve per-clip customization
            for c in candidates:
                clip_tr = TranscriptEditor.slice_transcript_for_window(transcript, c.start_sec, c.end_sec)
                v_res = vlm_results.get(c.clip_index)
                class_res = MultimodalSceneClassifier.classify(clip=c, transcript=clip_tr, vlm_analysis=v_res)
                c.scene_category = class_res.category.value

                # Resolve per-clip override:
                override = toggles.get_customization_for_clip(c.clip_index)
                if not override and getattr(request, "clip_overrides", None) and c.clip_index in request.clip_overrides:
                    override = request.clip_overrides[c.clip_index]

                if override and "layout_mode" in override:
                    lay = override["layout_mode"]
                    c.custom_layout = lay.value if isinstance(lay, LayoutMode) else str(lay)
                elif toggles.smart_layout_distribution:
                    c.custom_layout = class_res.recommended_layout.value
                else:
                    c.custom_layout = toggles.layout_mode.value

                if override and "caption_theme" in override:
                    theme = override["caption_theme"]
                    c.custom_caption_theme = theme.value if isinstance(theme, CaptionTheme) else str(theme)
                elif toggles.smart_layout_distribution:
                    c.custom_caption_theme = class_res.recommended_caption_theme.value
                else:
                    c.custom_caption_theme = toggles.caption_theme.value

                if override and "caption_font_size" in override:
                    c.custom_caption_font_size = int(override["caption_font_size"])
                elif toggles.smart_layout_distribution:
                    c.custom_caption_font_size = class_res.recommended_caption_font_size
                else:
                    c.custom_caption_font_size = toggles.caption_font_size

                if override and "bgm_track" in override:
                    c.custom_bgm_track = override["bgm_track"]
                elif toggles.smart_layout_distribution and toggles.bgm_track is None:
                    c.custom_bgm_track = class_res.recommended_bgm
                else:
                    c.custom_bgm_track = toggles.bgm_track

                # Spoken Hook Evaluation & On-Screen Hook Formulation
                spoken_words: List[str] = []
                if clip_tr and clip_tr.segments:
                    for s in clip_tr.segments:
                        spoken_words.extend([w.word for w in s.words])
                        if len(spoken_words) >= 12:
                            break
                spoken_opening = " ".join(spoken_words) if spoken_words else (c.transcript_snippet[:80] if c.transcript_snippet else "")
                hook_res = HookEngine.score_hook(spoken_opening)
                c.hook_score = hook_res["overall_score"]
                c.hook_breakdown = hook_res["sub_scores"]
                c.hook_formula = hook_res.get("weakest_link", "")

                # If spoken hook is weak (<65), formulate high-contrast on-screen text hook overlay
                if c.hook_score < 65:
                    c.hook_overlay_text = HookEngine.generate_hook_overlay(
                        transcript_snippet=c.transcript_snippet,
                        game_name=toggles.game_name_context,
                        scene_type=c.scene_category,
                        clip_index=c.clip_index,
                        vlm_summary=v_res.scene_summary if v_res else None,
                    )

            # -------------------------------------------------------------
            # Stage 5: Title & Description Generation
            # -------------------------------------------------------------
            _notify("STAGE_5_METADATA_GENERATION", 75.0)
            vlm_provider = None
            if toggles.metadata_mode in (MetadataMode.LOCAL_VLM, MetadataMode.EXTERNAL_MCP_AGENT, MetadataMode.AGENT_CO_PILOT):
                try:
                    vlm_provider = self.model_registry.create_vlm_provider()
                except Exception:
                    vlm_provider = None

            meta_service = MetadataService(vlm_provider=vlm_provider)
            metadata_map: Dict[int, ClipMetadataDTO] = {}
            used_titles: Set[str] = set()

            for c in candidates:
                clip_transcript = TranscriptEditor.slice_transcript_for_window(transcript, c.start_sec, c.end_sec)
                v_res = vlm_results.get(c.clip_index)
                meta = meta_service.generate_metadata(
                    clip=c,
                    toggles=toggles,
                    yt_meta=yt_meta,
                    transcript=clip_transcript,
                    vlm_summary=v_res.scene_summary if v_res else None,
                )
                # Lint and format title to mobile-safe <40 char rules
                formatted_title = TitleLinter.clean_and_format_title(
                    meta.primary_title,
                    game_name=toggles.game_name_context,
                )
                # Deduplication check: if title was already used in this batch, differentiate it
                if formatted_title in used_titles:
                    base_part = formatted_title.replace(" #Shorts", "").replace(" #shorts", "")
                    formatted_title = f"{base_part} Pt.{c.clip_index} #Shorts"
                used_titles.add(formatted_title)
                meta.primary_title = formatted_title
                metadata_map[c.clip_index] = meta

            # Export VLM & Transcript observation bundle for Agent Co-Pilot inspection
            bundle_clips = []
            for c in candidates:
                v_res = vlm_results.get(c.clip_index)
                clip_tr = TranscriptEditor.slice_transcript_for_window(transcript, c.start_sec, c.end_sec)
                bundle_clips.append({
                    "clip_index": c.clip_index,
                    "start_sec": c.start_sec,
                    "end_sec": c.end_sec,
                    "duration_sec": c.duration_sec,
                    "scene_category": c.scene_category,
                    "transcript": clip_tr.full_text if clip_tr else "",
                    "vlm_summary": v_res.scene_summary if v_res else "Action gameplay",
                    "vlm_events": v_res.detected_events if v_res else [],
                    "vlm_proposed_title": metadata_map[c.clip_index].primary_title if c.clip_index in metadata_map else "",
                    "hook_overlay_text": c.hook_overlay_text,
                    "keyframe_paths": c.keyframe_paths,
                })
            AgentCoPilotSynthesizer.export_observation_bundle(
                bundle_path=self.scratch_dir / job_id / "vlm_observation_bundle.json",
                job_id=job_id,
                game_name=toggles.game_name_context or "Gaming",
                clips_data=bundle_clips,
            )

            # -------------------------------------------------------------
            # Stage 6 & 7: Subtitle Compilation & FFmpeg Render
            # -------------------------------------------------------------
            _notify("STAGE_6_7_RENDERING", 85.0)
            job_export_dir = self.export_dir / job_id
            job_export_dir.mkdir(parents=True, exist_ok=True)
            rendered_paths: List[Path] = []

            for c in candidates:
                clip_id = f"{job_id}_clip_{c.clip_index:02d}"
                clip_base = job_export_dir / f"clip_{c.clip_index:02d}"
                output_mp4 = clip_base.with_suffix(".mp4")

                clip_transcript = TranscriptEditor.slice_transcript_for_window(transcript, c.start_sec, c.end_sec)
                has_words = clip_transcript.total_words > 0

                eff_layout = LayoutMode(c.custom_layout or toggles.layout_mode.value)
                eff_theme = CaptionTheme(c.custom_caption_theme or toggles.caption_theme.value)
                eff_font_size = int(c.custom_caption_font_size or toggles.caption_font_size)
                eff_bgm = c.custom_bgm_track if c.custom_bgm_track is not None else toggles.bgm_track

                ass_path: Optional[Path] = None
                has_overlay = bool(c.hook_overlay_text and c.hook_overlay_text.strip())
                should_compile = toggles.should_compile_subtitles(has_words=has_words) or (has_overlay and toggles.captions_mode != CaptionMode.NONE)

                if should_compile:
                    if toggles.captions_mode in (CaptionMode.BURNED_IN_ANIMATED, CaptionMode.BURNED_IN_PLUS_SIDECAR):
                        chunks = PhraseChunker.chunk_animated_pop(clip_transcript) if has_words else []
                        ass_path = self.scratch_dir / job_id / f"clip_{c.clip_index}.ass"
                        ASSCompiler.compile_ass(
                            chunks,
                            mode=CaptionMode.BURNED_IN_ANIMATED,
                            output_path=ass_path,
                            theme=eff_theme,
                            font_size=eff_font_size,
                            layout_mode=eff_layout,
                            hook_overlay_text=c.hook_overlay_text,
                        )
                    elif toggles.captions_mode == CaptionMode.BURNED_IN_CLASSIC:
                        chunks = PhraseChunker.chunk_classic(clip_transcript) if has_words else []
                        ass_path = self.scratch_dir / job_id / f"clip_{c.clip_index}.ass"
                        ASSCompiler.compile_ass(
                            chunks,
                            mode=CaptionMode.BURNED_IN_CLASSIC,
                            output_path=ass_path,
                            theme=eff_theme,
                            font_size=eff_font_size,
                            layout_mode=eff_layout,
                            hook_overlay_text=c.hook_overlay_text,
                        )

                    if toggles.should_export_sidecar(has_words=has_words):
                        classic_chunks = PhraseChunker.chunk_classic(clip_transcript)
                        SidecarExporter.export_all(classic_chunks, clip_base)

                # Render final MP4 with effective per-clip styling
                self.renderer.render_clip(
                    source_video=source_file_path,
                    output_mp4=output_mp4,
                    start_sec=c.start_sec,
                    duration_sec=c.duration_sec,
                    layout_mode=eff_layout,
                    ass_path=ass_path if (toggles.should_burn_in_subtitles(has_words=has_words) or (has_overlay and toggles.captions_mode != CaptionMode.NONE)) else None,
                    audio_mode=toggles.audio_process_mode,
                    facecam_pos=toggles.facecam_pos,
                    bgm_path=eff_bgm,
                    bgm_volume_duck_db=toggles.bgm_volume_duck_db,
                )
                rendered_paths.append(output_mp4)
    
                # Auto-Thumbnail Frame Picker (1080x1920)
                thumb_path = clip_base.with_suffix(".thumb.jpg")
                try:
                    self.renderer.generate_thumbnail(
                        video_path=output_mp4,
                        output_jpg=thumb_path,
                        timestamp_sec=min(2.0, c.duration_sec * 0.5),
                    )
                except Exception:
                    pass
    
                # Write Provenance Sidecar
                prov = RightsManager.build_provenance(
                    clip_id=clip_id,
                    source_sha256_prefix=sha_prefix,
                    toggles=toggles,
                    start_sec=c.start_sec,
                    end_sec=c.end_sec,
                    yt_meta=yt_meta,
                )
                prov.toggles_snapshot["layout_mode"] = eff_layout.value
                prov.toggles_snapshot["caption_theme"] = eff_theme.value
                prov.toggles_snapshot["scene_category"] = c.scene_category
                prov.toggles_snapshot["hook_score"] = c.hook_score
                prov.toggles_snapshot["hook_overlay"] = c.hook_overlay_text
                RightsManager.export_provenance_json(prov, clip_base.with_suffix(".provenance.json"))
    
                # Write Metadata Sidecar
                clip_meta = metadata_map.get(c.clip_index)
                if clip_meta and toggles.metadata_mode != MetadataMode.OFF:
                    (clip_base.with_suffix(".meta.json")).write_text(
                        clip_meta.model_dump_json(indent=2), encoding="utf-8"
                    )
    
                # Save clip record to SQLite
                self.db.save_clip(
                    clip_id=clip_id,
                    job_id=job_id,
                    clip=c,
                    meta=clip_meta,
                    exported_path=str(output_mp4),
                )
    
            _notify("COMPLETED", 100.0)
            self.db.update_job_status(job_id=job_id, status="COMPLETED", stage="ALL_STAGES_COMPLETE", progress_pct=100.0)
            return rendered_paths
        except Exception as e:
            code = self._classify_error(current_stage, e)
            clean_err = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip()
            diag_message = f"[{code}] {current_stage}: {clean_err}"
            self.db.update_job_status(
                job_id=job_id,
                status="FAILED",
                stage=f"FAILED_{current_stage}",
                progress_pct=current_pct,
                error_message=diag_message,
            )
            if progress_callback:
                progress_callback(f"FAILED ({code})", current_pct)
            raise RuntimeError(diag_message) from e

    def rerender_clip(
        self,
        source_video: Path | str,
        output_mp4: Path | str,
        start_sec: float,
        end_sec: float,
        layout_mode: LayoutMode,
        captions_mode: CaptionMode = CaptionMode.NONE,
        transcript: Optional[TranscriptDTO] = None,
        caption_theme: CaptionTheme = CaptionTheme.MRBEAST_YELLOW,
        caption_font_size: int = 68,
        facecam_pos: FacecamPosition = FacecamPosition.TOP_LEFT,
        bgm_path: Optional[Path | str] = None,
    ) -> Path:
        """Fast 10s single-clip re-render without re-running transcription or signal analysis."""
        duration = max(1.0, end_sec - start_sec)
        ass_path: Optional[Path] = None

        if transcript and captions_mode != CaptionMode.NONE:
            sliced_transcript = TranscriptEditor.slice_transcript_for_window(transcript, start_sec, end_sec)
            if sliced_transcript.total_words > 0:
                scratch_ass = Path(output_mp4).parent / "temp_rerender.ass"
                if captions_mode in (CaptionMode.BURNED_IN_ANIMATED, CaptionMode.BURNED_IN_PLUS_SIDECAR):
                    chunks = PhraseChunker.chunk_animated_pop(sliced_transcript)
                    ass_path = ASSCompiler.compile_ass(
                        chunks,
                        mode=CaptionMode.BURNED_IN_ANIMATED,
                        output_path=scratch_ass,
                        theme=caption_theme,
                        font_size=caption_font_size,
                        layout_mode=layout_mode,
                    )
                else:
                    chunks = PhraseChunker.chunk_classic(sliced_transcript)
                    ass_path = ASSCompiler.compile_ass(
                        chunks,
                        mode=CaptionMode.BURNED_IN_CLASSIC,
                        output_path=scratch_ass,
                        theme=caption_theme,
                        font_size=caption_font_size,
                        layout_mode=layout_mode,
                    )

        return self.renderer.rerender_single_clip(
            source_video=source_video,
            output_mp4=output_mp4,
            start_sec=start_sec,
            duration_sec=duration,
            layout_mode=layout_mode,
            ass_path=ass_path,
            facecam_pos=facecam_pos,
            bgm_path=bgm_path,
        )

    def run_batch(
        self,
        requests: List[JobRequestDTO],
        progress_callback: Optional[Callable[[str, float, int, int], None]] = None,
    ) -> Dict[str, List[Path]]:
        """
        Sequentially runs a batch queue of video requests.
        Reports stage, percentage, current index, and total jobs.
        """
        results: Dict[str, List[Path]] = {}
        total = len(requests)
        for idx, req in enumerate(requests, start=1):
            def _progress(stage: str, pct: float) -> None:
                if progress_callback:
                    progress_callback(stage, pct, idx, total)

            paths = self.run_job(req, progress_callback=_progress)
            results[req.job_id] = paths
        return results

    def resume_job(
        self,
        job_id: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> List[Path]:
        """Resumes an interrupted or failed job from its last completed checkpoint."""
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' not found in database.")

        toggles = PreRunToggles.model_validate_json(job["pre_run_toggles_json"])
        with self.db.get_connection() as conn:
            source_row = conn.execute("SELECT file_path_or_url FROM sources WHERE id = ?", (job_id,)).fetchone()
            src_path_or_url = source_row["file_path_or_url"] if source_row else ""

        req = JobRequestDTO(
            job_id=job_id,
            source_path_or_url=src_path_or_url,
            toggles=toggles,
            created_at_iso=job.get("created_at") or "",
        )
        return self.run_job(req, progress_callback=progress_callback)


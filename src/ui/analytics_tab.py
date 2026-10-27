"""Analytics & Channel Playbook UI Tab: Audience Retention Diagnostics, Hook Leak Detection, and Closed-Loop Learning."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
import gradio as gr

from ..config.schema import LayoutMode, CaptionTheme
from ..analytics.retention_diagnostics import RetentionDiagnostics
from ..core.channel_playbook import ChannelPlaybook
from ..core.youtube_uploader import YouTubeUploader
from ..core.database import DatabaseManager
from ..core.orchestrator import JobOrchestrator
from ..core.quota_guard import QuotaGuard
from ..core.autonomous_daemon import AutonomousDaemon


def create_analytics_tab(
    orchestrator: JobOrchestrator,
    db: DatabaseManager,
    uploader: YouTubeUploader,
    playbook: ChannelPlaybook,
) -> None:
    """Creates the Gradio UI tab for audience retention analytics and the channel playbook."""
    data_dir = orchestrator.scratch_dir.parent
    quota_guard = QuotaGuard(quota_path=data_dir / "daily_upload_quota.json")
    daemon = AutonomousDaemon(
        project_root=orchestrator.scratch_dir.parent.parent,
        quota_guard=quota_guard,
    )

    gr.Markdown("## 📈 Audience Retention Analytics & Autonomous Channel Playbook")
    gr.Markdown(
        "Diagnose viewer drop-off cliffs correlated with transcript dialogue, eliminate opening Hook Leak, "
        "and automatically evolve the Channel Playbook to optimize future video generation."
    )

    with gr.Accordion("🚀 1-Click Autonomous Executive Campaign (Founder Phone Mode)", open=True):
        quota_banner = gr.Markdown(f"**Daily Upload Quota:** `{quota_guard.get_status()['display']}`")
        gr.Markdown(
            "Paste any YouTube video URL or path. AutoShorts AI will automatically apply Playbook winning layouts, "
            "formulate viral hooks, render 60 FPS vertical Shorts, and schedule staggered YouTube uploads."
        )
        with gr.Row():
            campaign_source = gr.Textbox(
                label="Video URL or Local Path",
                placeholder="https://www.youtube.com/watch?v=...",
                lines=1,
            )
            campaign_count = gr.Slider(minimum=1, maximum=10, value=3, step=1, label="Target Clips Count")
            campaign_mode = gr.Dropdown(
                choices=["SCHEDULE_STAGGERED", "DRAFT_UPLOAD", "OFF"],
                value="SCHEDULE_STAGGERED",
                label="Publishing Strategy",
            )
            campaign_game = gr.Textbox(label="Game / Topic Context (Optional)", placeholder="e.g. Valorant, GTA 6")
        launch_campaign_btn = gr.Button("⚡ Launch Full-Auto Campaign", variant="primary")
        campaign_status = gr.Markdown("Ready to launch.")
        campaign_output = gr.JSON(label="Campaign Summary & Scheduled Uploads")

    with gr.Accordion("🤖 Auto-Pilot Daemon & Local Watch Folder", open=False):
        gr.Markdown(
            f"**Local Watch Folder:** `{daemon.watch_folder}`\n\n"
            "Drop any gameplay or stream recordings into this folder on your PC. "
            "When you run the cycle or launch the daemon, it processes and schedules them within your daily quota."
        )
        with gr.Row():
            run_cycle_btn = gr.Button("🔄 Run Catch-Up Sync & Watch Folder Cycle")
            refresh_quota_btn = gr.Button("📊 Refresh Quota Status")
        cycle_output = gr.JSON(label="Auto-Pilot Cycle Report")

    gr.Markdown("---")
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 🔍 Retention Curve & Drop-Off Cliff Audit")
            csv_file = gr.File(label="Upload YouTube Studio Retention CSV", file_types=[".csv", ".txt"])
            csv_text = gr.Textbox(
                label="Or Paste Retention Data (Timestamp, Retention %)",
                placeholder="0.0, 100\n2.5, 88\n5.0, 80\n10.0, 75\n15.0, 68\n25.0, 65\n40.0, 62",
                lines=5,
            )
            with gr.Row():
                dur_input = gr.Number(label="Video Duration (sec)", value=45.0)
                clip_id_input = gr.Textbox(label="Clip ID / Title", value="clip_01")
            with gr.Row():
                layout_select = gr.Dropdown(
                    choices=[m.value for m in LayoutMode],
                    value=LayoutMode.LAYOUT_HYBRID_CINEMA_STACK.value,
                    label="Layout Used",
                )
                theme_select = gr.Dropdown(
                    choices=[t.value for t in CaptionTheme],
                    value=CaptionTheme.MRBEAST_YELLOW.value,
                    label="Caption Theme Used",
                )
            transcript_input = gr.Textbox(
                label="Spoken Dialogue / Transcript (for Cliff Correlation)",
                placeholder="Paste dialogue text to automatically pinpoint what was spoken when viewers swiped away...",
                lines=3,
            )
            views_input = gr.Number(label="View Count (Optional)", value=1000)
            audit_btn = gr.Button("🔬 Run Diagnostics & Update Playbook", variant="primary")

        with gr.Column(scale=1):
            gr.Markdown("### 📊 Diagnostic Results & Cliff Breakdown")
            verdict_box = gr.Markdown("### Retention Health: Pending Audit\n*Upload or paste retention data to evaluate.*")
            cliffs_table = gr.JSON(label="Detected Drop-Off Cliffs & Correlated Dialogue")
            recommendations_box = gr.Markdown("### 💡 Actionable Next Steps\n- Run an audit to generate data-driven pacing and hook adjustments.")

    gr.Markdown("---")
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 🧠 Dynamic Channel Playbook Memory")
            gr.Markdown(
                "The Playbook tracks real-world retention by layout, duration, and theme. "
                "Future autonomous runs automatically query these parameters to maximize viewer retention."
            )
            playbook_stats = gr.JSON(label="Channel Playbook State", value=playbook.data if playbook else {})
            with gr.Row():
                refresh_playbook_btn = gr.Button("🔄 Refresh Playbook Memory")
                sync_telemetry_btn = gr.Button("📡 Sync YouTube Channel Telemetry")

        with gr.Column(scale=1):
            gr.Markdown("### 📡 YouTube Channel Telemetry")
            telemetry_status = gr.Markdown("Click 'Sync YouTube Channel Telemetry' to retrieve recent video performance.")
            telemetry_output = gr.JSON(label="Recent Shorts Metrics")

    gr.Markdown("---")
    with gr.Accordion("🔑 Link YouTube Brand Account & Credentials", open=not uploader.is_authenticated()):
        account_status = gr.Markdown(f"**Current Status:** {uploader.get_status_summary()['display']}")
        secrets_input = gr.Textbox(
            label="Paste client_secrets.json content here",
            placeholder='{"installed":{"client_id":"...","client_secret":"..."}}',
            lines=3,
        )
        save_secrets_btn = gr.Button("Save client_secrets.json")
        gr.Markdown(
            "**One-Time Authorization:**\n"
            "After saving `client_secrets.json`, open PowerShell and run:\n"
            "```powershell\npython shorts_factory/authenticate_youtube.py\n```\n"
            "A Google sign-in window will open in your browser to approve publishing permissions for your channel."
        )

    # Handler: Run Audit and Update Playbook
    def _run_audit(
        file_obj,
        raw_text: str,
        duration: float,
        clip_id: str,
        layout_str: str,
        theme_str: str,
        transcript_text: str,
        views: float,
    ):
        content = ""
        if file_obj is not None:
            try:
                p = Path(file_obj.name)
                content = p.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                content = raw_text
        else:
            content = raw_text

        if not content.strip():
            return (
                "### ❌ Error: No retention data provided.\nPlease upload a CSV or paste retention numbers.",
                [],
                "- Ensure at least 4 retention data points are provided.",
                playbook.data,
            )

        data_pts = RetentionDiagnostics.load_retention_data(content)
        if len(data_pts) < 4:
            return (
                "### ❌ Error: Insufficient data points.\nProvide at least 4 (timestamp, retention_pct) pairs.",
                [],
                "- YouTube retention curves typically export 20 to 100 data points.",
                playbook.data,
            )

        # Build synthetic or parsed segments from transcript text if provided
        segments = []
        if transcript_text.strip():
            lines = [l.strip() for l in transcript_text.splitlines() if l.strip()]
            sec_per_line = max(1.0, (duration or 45.0) / max(1, len(lines)))
            for idx, line in enumerate(lines):
                segments.append({
                    "start_sec": round(idx * sec_per_line, 1),
                    "end_sec": round((idx + 1) * sec_per_line, 1),
                    "text": line,
                })

        audit = RetentionDiagnostics.analyze_retention(
            retention_data=data_pts,
            duration_sec=float(duration) if duration else None,
            transcript_segments=segments if segments else None,
        )

        if "error" in audit:
            return (
                f"### ❌ Audit Error: {audit['error']}",
                [],
                "- Check the retention data format.",
                playbook.data,
            )

        # Update Playbook
        ret_end = audit.get("end_pct", 70.0)
        hook_leak = audit.get("hook_leak_pct", 0.0)
        playbook.record_clip_performance(
            clip_id=clip_id or "clip_unknown",
            layout_mode=layout_str,
            caption_theme=theme_str,
            duration_sec=float(duration) if duration else 45.0,
            scene_category="ACTION",
            retention_pct=ret_end,
            views=int(views or 0),
            hook_leak_pct=hook_leak,
            notes=f"Audited via UI: verdict={audit.get('verdict')}",
        )

        verdict_str = audit.get("verdict", "healthy").upper()
        badge_color = "🟢" if verdict_str == "VIRAL" else "🟡" if verdict_str == "HEALTHY" else "🔴"
        verdict_md = f"""### {badge_color} Retention Health: **{verdict_str}**
- **Hook Leak (First 15s):** `{hook_leak}%` lost
- **Final Completion Retention:** `{ret_end}%`
- **Total Curve Sample Points:** `{audit.get('total_points')}`
"""
        recs_list = audit.get("recommendations", [])
        recs_md = "### 💡 Actionable Next Steps\n" + "\n".join(f"- {r}" for r in recs_list)

        return (
            verdict_md,
            audit.get("top_cliffs", []),
            recs_md,
            playbook.data,
        )

    audit_btn.click(
        _run_audit,
        inputs=[
            csv_file,
            csv_text,
            dur_input,
            clip_id_input,
            layout_select,
            theme_select,
            transcript_input,
            views_input,
        ],
        outputs=[verdict_box, cliffs_table, recommendations_box, playbook_stats],
    )

    # Handler: Refresh Playbook Memory
    def _refresh_playbook():
        return playbook.data

    refresh_playbook_btn.click(
        _refresh_playbook,
        inputs=[],
        outputs=[playbook_stats],
    )

    # Handler: Sync YouTube Telemetry
    def _sync_telemetry():
        res = uploader.fetch_channel_shorts_analytics(max_results=10)
        if not res.get("success", False):
            msg = f"### ⚠️ Sync Status: Failed\n{res.get('error', 'Unknown error')}"
            return msg, {}
        note = " (Simulated Telemetry)" if res.get("is_mock") else " (Live API)"
        msg = f"### ✅ YouTube Telemetry Synced{note}\nFetched {res.get('total_fetched', 0)} recent Shorts from YouTube."
        return msg, res

    sync_telemetry_btn.click(
        _sync_telemetry,
        inputs=[],
        outputs=[telemetry_status, telemetry_output],
    )

    # Handler: Save client_secrets.json
    def _save_secrets(text: str):
        if not text or not text.strip():
            return "Please paste client_secrets.json content first."
        ok, msg = uploader.save_client_secrets(text)
        summary = uploader.get_status_summary()["display"]
        return f"**Save Status:** {msg}\n\n**Current Status:** {summary}"

    save_secrets_btn.click(
        _save_secrets,
        inputs=[secrets_input],
        outputs=[account_status],
    )

    # Handler: Launch Autonomous Campaign
    def _launch_campaign(source: str, count: float, pub_mode: str, game: str):
        if not source or not source.strip():
            return "### ❌ Please provide a video URL or file path.", {}, f"**Daily Upload Quota:** `{quota_guard.get_status()['display']}`"
        
        rep = daemon.process_source(
            source_url_or_path=source.strip(),
            target_count=int(count),
            publish_mode=pub_mode,
            game_name=game.strip() if game else None,
        )
        msg = f"### ✅ Campaign Complete!\n- Generated: {rep.get('total_clips_generated')} clips\n- Uploads: {len(rep.get('uploads', []))}"
        q_display = quota_guard.get_status()["display"]
        return msg, rep, f"**Daily Upload Quota:** `{q_display}`"

    launch_campaign_btn.click(
        _launch_campaign,
        inputs=[campaign_source, campaign_count, campaign_mode, campaign_game],
        outputs=[campaign_status, campaign_output, quota_banner],
    )

    # Handler: Auto-Pilot Cycle & Watch Folder
    def _run_daemon_cycle():
        rep = daemon.run_cycle()
        q_display = quota_guard.get_status()["display"]
        return rep, f"**Daily Upload Quota:** `{q_display}`"

    run_cycle_btn.click(
        _run_daemon_cycle,
        inputs=[],
        outputs=[cycle_output, quota_banner],
    )

    refresh_quota_btn.click(
        lambda: f"**Daily Upload Quota:** `{quota_guard.get_status()['display']}`",
        inputs=[],
        outputs=[quota_banner],
    )

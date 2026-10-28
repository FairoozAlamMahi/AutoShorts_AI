"""
YouTube Agent War Room Tab for Gradio UI
Exposes the 11 YouTube agent skills and 6 Python tools interactively:
- 21-Formula Hook Scorer & Ranker (hookscore.py)
- Title & Thumbnail Pairing Linter (title.py)
- Dead-Air & Filler Trimmer (deadair.py)
- Viral Outlier Swipe File (swipe.py)
- Audience Retention Leak Auditor (retention.py)
- Trending Audio Scraper & Viral Audio Bank Manager
"""
from pathlib import Path
import json
import gradio as gr

from ..skills.youtube_agent_bridge import youtube_agent
from ..audio.viral_audio_bank import viral_audio_bank
from ..audio.trending_scraper import trending_scraper


def create_war_room_tab():
    """Builds the complete YouTube Agent War Room UI interface."""
    gr.Markdown("## 🎯 YouTube Agent War Room (11 Channel Skills)")
    gr.Markdown(
        "Direct interactive integration of the 11 YouTube Agent Skills and 6 algorithmic Python tools. "
        "Craft viral hooks off 21 formulas, lint title/thumbnail pairings, trim dead-air, detect competitor outliers, "
        "audit retention leaks, and manage your viral phonk audio bank."
    )

    with gr.Tabs():
        # --- TAB 1: HOOK SCORER & 21 FORMULAS ---
        with gr.Tab("🪝 Hook Scorer & 21 Formulas"):
            gr.Markdown("### Score Hooks Across 5 Viral Properties (Specificity, Address, Stakes, Curiosity, Brevity)")
            with gr.Row():
                with gr.Column(scale=3):
                    hook_input = gr.Textbox(
                        label="Hook Lines (One per line)",
                        lines=5,
                        value=(
                            "97% of creators quit before video 30. Here is what you must do instead.\n"
                            "Stop making this 1 combat mistake in Phantom Blade Zero right now.\n"
                            "Watch what happens when you hit this jump at maximum speed in GTA!\n"
                            "Hey guys welcome back today I am doing a video."
                        ),
                    )
                    score_btn = gr.Button("Evaluate & Rank Hooks", variant="primary")
                with gr.Column(scale=4):
                    hook_output = gr.Markdown("Click **Evaluate & Rank Hooks** to score candidate hooks.")

            def _eval_hooks(text: str):
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if not lines:
                    return "Please enter at least one hook line."
                ranked = youtube_agent.rank_hooks(lines)
                md = "### Hook Ranking Results\n\n"
                for i, r in enumerate(ranked, 1):
                    badge = "🟢 STRONG" if r.verdict_score >= 70 else ("🟡 WORKABLE" if r.verdict_score >= 50 else "🔴 WEAK")
                    md += f"#### #{i}: Score {r.verdict_score}/100 [{badge}]\n"
                    md += f"> **Hook:** \"{r.hook}\"\n\n"
                    md += f"- **Formula Matched:** `{r.formula_name}` ({r.formula_hits} pattern hits)\n"
                    md += f"- **Weakest Property:** `{r.weakest_property}` ({r.properties.get(r.weakest_property, 0)}/100)\n"
                    md += f"- **Suggested Fix:** *{r.suggested_fix}*\n"
                    md += "- **Detailed Property Breakdown:** "
                    md += ", ".join([f"`{k}: {v}`" for k, v in r.properties.items()])
                    md += "\n\n---\n"
                return md

            score_btn.click(_eval_hooks, inputs=[hook_input], outputs=[hook_output])

        # --- TAB 2: TITLE & THUMBNAIL LINTER ---
        with gr.Tab("🖼️ Title & Thumbnail Linter"):
            gr.Markdown("### Atomic Packaging Linter (40-char Mobile Cutoff, 3-Word Thumbnail Rule, Word Overlap)")
            with gr.Row():
                with gr.Column(scale=3):
                    title_in = gr.Textbox(label="YouTube Title", value="Impossible 5-Star Police Escape in GTA")
                    thumb_in = gr.Textbox(label="Thumbnail Text Overlay", value="5 STAR ESCAPE")
                    lint_btn = gr.Button("Lint Packaging", variant="primary")
                with gr.Column(scale=4):
                    lint_output = gr.Markdown("Click **Lint Packaging** to check title and thumbnail.")

            def _lint_packaging(title: str, thumb: str):
                res = youtube_agent.lint_title_and_thumbnail(title, thumb)
                mobile_status = "✅ Safe (<= 40 chars)" if res.mobile_safe else "⚠️ Truncated on Mobile Feed"
                desktop_status = "✅ Safe (<= 60 chars)" if res.desktop_safe else "⚠️ Truncated on Desktop Search"
                md = f"### Packaging Score: {res.score}/100\n\n"
                md += f"- **Character Count:** {res.char_count} chars\n"
                md += f"- **Mobile Feed Status:** {mobile_status}\n"
                md += f"- **Desktop Search Status:** {desktop_status}\n\n"

                if res.issues:
                    md += "#### ⚠️ Issues Detected:\n"
                    for issue in res.issues:
                        md += f"- **[{issue['kind'].upper()}]:** {issue['message']}\n"
                    md += "\n"

                if res.good_points:
                    md += "#### ✅ What Works Well:\n"
                    for g in res.good_points:
                        md += f"- {g}\n"

                return md

            lint_btn.click(_lint_packaging, inputs=[title_in, thumb_in], outputs=[lint_output])

        # --- TAB 3: VIRAL AUDIO BANK & SCRAPER ---
        with gr.Tab("🎵 Viral Audio Bank & Phonk Scraper"):
            gr.Markdown("### Persistent Viral Audio Bank (BPM, Drop Timing, and yt-dlp Scraper)")
            with gr.Row():
                with gr.Column(scale=3):
                    gr.Markdown("#### Download New Viral Track from YouTube")
                    yt_url_in = gr.Textbox(label="YouTube Video / Shorts URL", placeholder="https://www.youtube.com/watch?v=...")
                    mood_in = gr.Dropdown(
                        label="Audio Mood Category",
                        choices=["BRAZILIAN_PHONK", "DRIFT_PHONK", "DARK_FANTASY", "RAGE_TRAP", "HYPE_EDM"],
                        value="BRAZILIAN_PHONK"
                    )
                    dl_btn = gr.Button("Download & Index Track", variant="primary")
                    dl_status = gr.Textbox(label="Scraper Status", interactive=False)
                with gr.Column(scale=4):
                    gr.Markdown("#### Cataloged Tracks in Bank")
                    bank_refresh_btn = gr.Button("Refresh Catalog")
                    catalog_display = gr.Markdown("Click **Refresh Catalog** to view indexed tracks.")

            def _download_track(url: str, mood: str):
                if not url.strip():
                    return "Please enter a valid YouTube URL."
                try:
                    track = trending_scraper.download_url(url.strip(), mood=mood)
                    if track:
                        return f"Downloaded: '{track.title}' | BPM: {track.bpm} | Drop: {track.suggested_drop_sec}s"
                    return "Download failed. Please check the URL."
                except Exception as e:
                    return f"Error: {e}"

            def _show_catalog():
                tracks = viral_audio_bank.list_tracks()
                if not tracks:
                    return "No tracks currently registered in the bank."
                md = f"### Indexed Audio Stems ({len(tracks)} tracks)\n\n"
                md += "| Track ID | Title | Mood | BPM | Beat Drop | Path |\n"
                md += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                for t in tracks:
                    md += f"| `{t.track_id}` | {t.title[:35]} | `{t.mood}` | **{t.bpm}** | **{t.suggested_drop_sec}s** | `{Path(t.file_path).name}` |\n"
                return md

            dl_btn.click(_download_track, inputs=[yt_url_in, mood_in], outputs=[dl_status])
            bank_refresh_btn.click(_show_catalog, inputs=[], outputs=[catalog_display])

        # --- TAB 4: VIRAL SWIPE OUTLIERS ---
        with gr.Tab("📈 Viral Outlier Finder (swipe.py)"):
            gr.Markdown("### Niche Competitor Outlier Detector (Own-Channel Median Multiples)")
            with gr.Row():
                with gr.Column(scale=3):
                    swipe_json_in = gr.Textbox(
                        label="Competitor Videos JSON or File Path",
                        lines=6,
                        placeholder='[{"channel":"GamerX","title":"Clip","views":50000,"url":"..."}, ...]'
                    )
                    min_mult_in = gr.Slider(label="Minimum Median Multiple", minimum=1.2, maximum=5.0, value=2.0, step=0.1)
                    swipe_btn = gr.Button("Detect Outliers", variant="primary")
                with gr.Column(scale=4):
                    swipe_out = gr.Markdown("Enter competitor video data to detect viral outliers.")

            def _run_swipe(data_str: str, min_m: float):
                import tempfile
                if not data_str.strip():
                    return "Please provide JSON data or a file path."
                p = Path(data_str.strip())
                temp_p = None
                if not p.exists():
                    try:
                        parsed = json.loads(data_str)
                        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
                            json.dump(parsed, f)
                            temp_p = f.name
                            p = Path(temp_p)
                    except Exception as e:
                        return f"Invalid JSON input: {e}"

                try:
                    res = youtube_agent.find_viral_outliers(p, min_multiple=min_m)
                    md = f"### Analyzed {res.total_videos} videos across {res.total_channels} channels\n\n"
                    if not res.outliers:
                        md += f"No videos beat their channel median by {min_m}x or more.\n"
                    else:
                        md += f"Found **{len(res.outliers)}** viral outliers:\n\n"
                        for o in res.outliers:
                            md += f"- **{o['multiple']}x median:** `{o['title']}` ({o['views']:,} views vs {o['median']:,} median) - *Formula:* `{o['formula']}`\n"
                    return md
                finally:
                    if temp_p:
                        Path(temp_p).unlink(missing_ok=True)

            swipe_btn.click(_run_swipe, inputs=[swipe_json_in, min_mult_in], outputs=[swipe_out])

"""
Script to restructure all generated output videos across the project
into a centralized, beautifully organized hierarchy inside OUTPUT_VIDEOS/.

Structure created:
OUTPUT_VIDEOS/
├── GTA/
│   ├── GTA 1/                 (Source: 720p GTA 6 - Extended Look, 12 videos)
│   ├── GTA 2/                 (Source: 1080p GTA 6 - Official Gameplay, 12 videos)
│   └── GTA 3/                 (Autonomous 4-Pack Campaign, 4 videos)
├── Phantom Blade 0/
│   ├── Phantom Blade 1/       (Source: PBZ 66m cut - Initial 5-Pack Campaign, 5 videos)
│   ├── Phantom Blade 2/       (Source: PBZ 66m cut - Viral Showcases V1/V2/V3, 9 videos)
│   └── Phantom Blade 3/       (Source: PBZ 78m 1080p60 HYsuUyMg8gQ - 7 Shorts Series, 7 videos)
└── Astro Bot/
    └── Astro Bot 1/           (Source: Astro Bot Gameplay - Initial Verification, 8 videos)

Direct junctions are also created at OUTPUT_VIDEOS root:
- OUTPUT_VIDEOS/GTA 1 -> GTA/GTA 1
- OUTPUT_VIDEOS/GTA 2 -> GTA/GTA 2
- OUTPUT_VIDEOS/GTA 3 -> GTA/GTA 3
- OUTPUT_VIDEOS/Phantom Blade 1 -> Phantom Blade 0/Phantom Blade 1
- OUTPUT_VIDEOS/Phantom Blade 2 -> Phantom Blade 0/Phantom Blade 2
- OUTPUT_VIDEOS/Phantom Blade 3 -> Phantom Blade 0/Phantom Blade 3
- OUTPUT_VIDEOS/Astro Bot 1 -> Astro Bot/Astro Bot 1
"""

import os
import sys
import glob
import json
import shutil
import hashlib
import subprocess
from pathlib import Path

WORKSPACE = Path(r"c:\Users\faalv\Desktop\Personal project\yt_shorts_generator")
OUTPUT_ROOT = WORKSPACE / "OUTPUT_VIDEOS"

# Ensure root destinations
DESTINATIONS = {
    "GTA_1": OUTPUT_ROOT / "GTA" / "GTA 1",
    "GTA_2": OUTPUT_ROOT / "GTA" / "GTA 2",
    "GTA_3": OUTPUT_ROOT / "GTA" / "GTA 3",
    "PBZ_1": OUTPUT_ROOT / "Phantom Blade 0" / "Phantom Blade 1",
    "PBZ_2": OUTPUT_ROOT / "Phantom Blade 0" / "Phantom Blade 2",
    "PBZ_3": OUTPUT_ROOT / "Phantom Blade 0" / "Phantom Blade 3",
    "ASTRO_1": OUTPUT_ROOT / "Astro Bot" / "Astro Bot 1",
}

for dest in DESTINATIONS.values():
    dest.mkdir(parents=True, exist_ok=True)

def sha256_file(path, limit_mb=100):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        read_bytes = 0
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
            read_bytes += len(chunk)
            if limit_mb and read_bytes >= limit_mb * 1024 * 1024:
                break
    return h.hexdigest()

def safe_copy(src: Path, dst_dir: Path, custom_name: str = None):
    dst_dir.mkdir(parents=True, exist_ok=True)
    target_name = custom_name if custom_name else src.name
    target = dst_dir / target_name
    if not target.exists() or target.stat().st_size != src.stat().st_size:
        shutil.copy2(src, target)
        return True, target
    return False, target

def safe_move(src: Path, dst_dir: Path, custom_name: str = None):
    dst_dir.mkdir(parents=True, exist_ok=True)
    target_name = custom_name if custom_name else src.name
    target = dst_dir / target_name
    if src == target:
        return False, target
    if target.exists():
        if target.stat().st_size == src.stat().st_size:
            src.unlink()
            return True, target
        else:
            # Different content, replace safely
            target.unlink()
    shutil.move(str(src), str(target))
    return True, target

def run_migration():
    print("Starting centralized output video restructuring...")
    
    # 1. Clean up / move loose files currently directly under OUTPUT_VIDEOS/
    print("\n[Step 1] Moving existing top-level files in OUTPUT_VIDEOS to matching subfolders...")
    for f in list(OUTPUT_ROOT.iterdir()):
        if f.is_file():
            name = f.name
            target_cat = None
            if name.startswith("gta_01_highway") or name.startswith("gta_02_convenience"):
                target_cat = "GTA_2"
            elif name.startswith("pbz_01_bridge") or name.startswith("pbz_02_lion"):
                target_cat = "PBZ_2"
            elif any(name.startswith(pfx) for pfx in [
                "pbz_01_hopeless", "pbz_02_thick", "pbz_03_drooling",
                "pbz_04_bridge_deflect", "pbz_05_finishing", "pbz_06_chained",
                "pbz_07_shadow", "scheduled_7_shorts"
            ]):
                target_cat = "PBZ_3"
            elif name == "viral_v3_manifest.json":
                # Copy to both GTA_2 and PBZ_2 as reference
                target_cat = "PBZ_2"
            
            if target_cat:
                dst = DESTINATIONS[target_cat]
                moved, tgt = safe_move(f, dst)
                print(f"  Moved: {name} -> {target_cat} ({tgt.relative_to(OUTPUT_ROOT)})")

    # 2. Populate GTA 1 (Source: 720p GTA 6 - Extended Look)
    print("\n[Step 2] Consolidating GTA 1 videos (job_gta6_846afb + viral_showcase GTA)...")
    src_gta1_raw = WORKSPACE / "shorts_factory" / "data" / "exports" / "job_gta6_846afb"
    if src_gta1_raw.exists():
        for f in src_gta1_raw.iterdir():
            if f.is_file():
                safe_copy(f, DESTINATIONS["GTA_1"])
                print(f"  GTA 1 raw: {f.name}")
                
    src_gta1_viral = WORKSPACE / "shorts_factory" / "data" / "exports" / "viral_showcase"
    if src_gta1_viral.exists():
        for f in src_gta1_viral.iterdir():
            if f.is_file() and f.name.startswith("gta_"):
                safe_copy(f, DESTINATIONS["GTA_1"])
                print(f"  GTA 1 viral: {f.name}")

    # 3. Populate GTA 2 (Source: 1080p GTA 6 - Official Gameplay)
    print("\n[Step 3] Consolidating GTA 2 videos (job_gta6_1080p_3c7dba + V2 + V3 + staging)...")
    src_gta2_raw = WORKSPACE / "shorts_factory" / "data" / "exports" / "job_gta6_1080p_3c7dba"
    if src_gta2_raw.exists():
        for f in src_gta2_raw.iterdir():
            if f.is_file():
                safe_copy(f, DESTINATIONS["GTA_2"])
                print(f"  GTA 2 raw: {f.name}")
                
    src_gta2_v2 = WORKSPACE / "shorts_factory" / "data" / "exports" / "viral_showcase_v2"
    if src_gta2_v2.exists():
        for f in src_gta2_v2.iterdir():
            if f.is_file() and f.name.startswith("gta_"):
                safe_copy(f, DESTINATIONS["GTA_2"])
                print(f"  GTA 2 V2: {f.name}")
                
    src_gta2_v3 = WORKSPACE / "shorts_factory" / "data" / "exports" / "viral_showcase_v3"
    if src_gta2_v3.exists():
        for f in src_gta2_v3.iterdir():
            if f.is_file() and f.name.startswith("gta_"):
                safe_copy(f, DESTINATIONS["GTA_2"])
                print(f"  GTA 2 V3: {f.name}")

    src_staging = WORKSPACE / "shorts_factory" / "data" / "staging"
    if src_staging.exists():
        for f in src_staging.iterdir():
            if f.is_file() and (f.name.startswith("gta_01_supercar") or f.name.startswith("gta_02_highway_police")):
                safe_copy(f, DESTINATIONS["GTA_2"])
                print(f"  GTA 2 staged: {f.name}")

    # 4. Populate GTA 3 (Source: Autonomous 4-Pack Campaign)
    print("\n[Step 4] Consolidating GTA 3 videos (job_gta6_auto4_exec)...")
    src_gta3 = WORKSPACE / "shorts_factory" / "data" / "exports" / "job_gta6_auto4_exec"
    if src_gta3.exists():
        for f in src_gta3.iterdir():
            if f.is_file():
                safe_copy(f, DESTINATIONS["GTA_3"])
                print(f"  GTA 3 autonomous: {f.name}")

    # 5. Populate Phantom Blade 1 (Initial 5-Pack Campaign)
    print("\n[Step 5] Consolidating Phantom Blade 1 videos (job_phantom_blade_5pack)...")
    src_pbz1 = WORKSPACE / "shorts_factory" / "data" / "exports" / "job_phantom_blade_5pack"
    if src_pbz1.exists():
        for f in src_pbz1.iterdir():
            if f.is_file():
                safe_copy(f, DESTINATIONS["PBZ_1"])
                print(f"  PBZ 1 5-pack: {f.name}")

    # 6. Populate Phantom Blade 2 (Viral Showcases V1, V2, V3, staging)
    print("\n[Step 6] Consolidating Phantom Blade 2 videos (viral_showcase V1, V2, V3, staging)...")
    if src_gta1_viral.exists():
        for f in src_gta1_viral.iterdir():
            if f.is_file() and f.name.startswith("pbz_"):
                safe_copy(f, DESTINATIONS["PBZ_2"])
                print(f"  PBZ 2 V1: {f.name}")
                
    if src_gta2_v2.exists():
        for f in src_gta2_v2.iterdir():
            if f.is_file() and f.name.startswith("pbz_"):
                safe_copy(f, DESTINATIONS["PBZ_2"])
                print(f"  PBZ 2 V2: {f.name}")
                
    if src_gta2_v3.exists():
        for f in src_gta2_v3.iterdir():
            if f.is_file() and f.name.startswith("pbz_"):
                safe_copy(f, DESTINATIONS["PBZ_2"])
                print(f"  PBZ 2 V3: {f.name}")
                
    if src_staging.exists():
        f = src_staging / "pbz_02_fire_samurai_climax.mp4"
        if f.exists():
            safe_copy(f, DESTINATIONS["PBZ_2"])
            print(f"  PBZ 2 staged: {f.name}")

    # 7. Populate Phantom Blade 3 (7 Shorts Series from HYsuUyMg8gQ)
    print("\n[Step 7] Consolidating Phantom Blade 3 videos (pbz_7_shorts)...")
    src_pbz3 = WORKSPACE / "shorts_factory" / "data" / "exports" / "pbz_7_shorts"
    if src_pbz3.exists():
        for f in src_pbz3.iterdir():
            if f.is_file():
                safe_copy(f, DESTINATIONS["PBZ_3"])
                print(f"  PBZ 3 7-shorts: {f.name}")

    # 8. Populate Astro Bot 1 (Verification runs)
    print("\n[Step 8] Consolidating Astro Bot 1 videos (job_e7db79f0 + job_e92466c9)...")
    src_astro_a = WORKSPACE / "shorts_factory" / "data" / "exports" / "job_e7db79f0"
    if src_astro_a.exists():
        for f in src_astro_a.iterdir():
            if f.is_file():
                safe_copy(f, DESTINATIONS["ASTRO_1"], custom_name=f"batch1_{f.name}")
                print(f"  Astro Bot batch 1: batch1_{f.name}")
                
    src_astro_b = WORKSPACE / "shorts_factory" / "data" / "exports" / "job_e92466c9"
    if src_astro_b.exists():
        for f in src_astro_b.iterdir():
            if f.is_file():
                safe_copy(f, DESTINATIONS["ASTRO_1"], custom_name=f"batch2_{f.name}")
                print(f"  Astro Bot batch 2: batch2_{f.name}")

    # 9. Create root directory junctions
    print("\n[Step 9] Creating root directory junctions for flat & hierarchical access...")
    junction_map = [
        ("GTA 1", DESTINATIONS["GTA_1"]),
        ("GTA 2", DESTINATIONS["GTA_2"]),
        ("GTA 3", DESTINATIONS["GTA_3"]),
        ("Phantom Blade 1", DESTINATIONS["PBZ_1"]),
        ("Phantom Blade 2", DESTINATIONS["PBZ_2"]),
        ("Phantom Blade 3", DESTINATIONS["PBZ_3"]),
        ("Astro Bot 1", DESTINATIONS["ASTRO_1"]),
    ]
    for j_name, target in junction_map:
        j_path = OUTPUT_ROOT / j_name
        if j_path.exists():
            subprocess.run(f'cmd /c "rmdir \"{j_path}\""', shell=True, capture_output=True)
        ps_cmd = f"New-Item -ItemType Junction -Path '{j_path}' -Target '{target}'"
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            print(f"  Junction created: {j_name} -> {target.relative_to(OUTPUT_ROOT)}")
        else:
            print(f"  Junction note ({j_name}): {res.stderr.strip() or res.stdout.strip()}")

    # 10. Generate Master Catalog Manifest & Markdown Index
    print("\n[Step 10] Generating Master Catalog Manifest and Documentation...")
    catalog = {
        "project_name": "Autonomous YouTube Shorts Generator",
        "central_output_directory": str(OUTPUT_ROOT),
        "categories": {}
    }

    markdown_lines = [
        "# Centralized Output Video Catalog",
        "",
        "All output videos created across the lifetime of the project have been structured into this centralized directory.",
        "",
        "## Directory Structure",
        "```",
        "OUTPUT_VIDEOS/",
        "|-- GTA/",
        "|   |-- GTA 1/                 (Source: 720p Grand Theft Auto VI: An Extended Look)",
        "|   |-- GTA 2/                 (Source: 1080p GTA 6 - Official Extended Gameplay)",
        "|   \\-- GTA 3/                 (Autonomous 4-Pack Campaign)",
        "|-- Phantom Blade 0/",
        "|   |-- Phantom Blade 1/       (Source: PBZ 66m cut - Initial 5-Pack Campaign)",
        "|   |-- Phantom Blade 2/       (Source: PBZ 66m cut - Viral Showcases V1/V2/V3)",
        "|   \\-- Phantom Blade 3/       (Source: PBZ 78m 1080p60 HYsuUyMg8gQ - 7 Shorts Series)",
        "\\-- Astro Bot/",
        "    \\-- Astro Bot 1/           (Source: Golden Costume Astro Bot Gameplay - Verification Runs)",
        "```",
        "",
        "> Direct access junctions are also available at the root level (`OUTPUT_VIDEOS/GTA 1`, `OUTPUT_VIDEOS/Phantom Blade 1`, etc.) for seamless flat navigation.",
        "",
        "---",
        ""
    ]

    for key, dest in DESTINATIONS.items():
        vids = sorted([p for p in dest.iterdir() if p.suffix.lower() == ".mp4"])
        cat_info = {
            "path": str(dest),
            "video_count": len(vids),
            "videos": []
        }
        
        markdown_lines.append(f"## {dest.parent.name} - {dest.name}")
        markdown_lines.append(f"**Location:** [`{dest.relative_to(WORKSPACE)}`](file:///{str(dest).replace(chr(92), '/')})")
        markdown_lines.append(f"**Total Videos:** {len(vids)}")
        markdown_lines.append("")
        markdown_lines.append("| Filename | Size (MB) | Thumbnail | Associated Sidecars |")
        markdown_lines.append("| :--- | :--- | :--- | :--- |")

        for v in vids:
            sz_mb = v.stat().st_size / (1024 * 1024)
            # Find thumbnails
            thumbs = sorted([t.name for t in dest.glob(f"{v.stem}*.jpg")])
            thumb_str = thumbs[0] if thumbs else "None"
            sidecars = sorted([s.name for s in dest.glob(f"{v.stem}*.json")])
            sidecar_str = ", ".join(sidecars) if sidecars else "None"
            
            v_entry = {
                "filename": v.name,
                "path": str(v),
                "size_bytes": v.stat().st_size,
                "size_mb": round(sz_mb, 2),
                "thumbnails": thumbs,
                "sidecars": sidecars
            }
            cat_info["videos"].append(v_entry)
            
            v_link = f"[{v.name}](file:///{str(v).replace(chr(92), '/')})"
            thumb_link = f"[{thumb_str}](file:///{str(dest / thumb_str).replace(chr(92), '/')})" if thumbs else "None"
            markdown_lines.append(f"| {v_link} | {sz_mb:.2f} MB | {thumb_link} | {sidecar_str} |")

        markdown_lines.append("")
        catalog["categories"][key] = cat_info

    # Write catalog manifest
    with open(OUTPUT_ROOT / "MASTER_CATALOG.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

    with open(OUTPUT_ROOT / "README.md", "w", encoding="utf-8") as f:
        f.write("\n".join(markdown_lines))

    print(f"\nRestructuring complete! Master manifest written to: {OUTPUT_ROOT / 'MASTER_CATALOG.json'}")
    print(f"Documentation written to: {OUTPUT_ROOT / 'README.md'}")

if __name__ == "__main__":
    run_migration()

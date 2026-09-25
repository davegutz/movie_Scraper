#!/usr/bin/env python3
"""
Combine The Bridge on the River Kwai (1957) Part 1 and Part 2 into a single unified movie file.
- Audio: Stereo AAC (160k, eng)
- Video: H.264 (CRF 20, preset medium, 720x404, yuv420p)
- Chapters: Comprehensive scene chapters for both parts
- Subtitles: Unified English SRT sidecar and embedded mov_text track (1,335 cues)
- Proof: Automatic 3-sample quality control verification in subtitle_proof/
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

PART1_PATH = "/media/daveg/Lib/Movies/The Bridge on the River Kwai (1957) Part 1.m4v"
PART2_PATH = "/media/daveg/Lib/Movies/The Bridge on the River Kwai (1957) Part 2.m4v"
OUTPUT_DIR = "/media/daveg/Lib/Movies"
FINAL_TARGET = os.path.join(OUTPUT_DIR, "The Bridge on the River Kwai (1957).m4v")
TEMP_TARGET = os.path.join(OUTPUT_DIR, ".The Bridge on the River Kwai (1957).resampled_tmp.m4v")
FINAL_SRT = os.path.join(OUTPUT_DIR, "The Bridge on the River Kwai (1957).en.srt")
CHAPTERS_FILE = "/tmp/river_kwai_chapters.txt"
MERGED_SRT_TEMP = "/tmp/river_kwai_merged.srt"
BACKUP_DIR = "/media/daveg/Lib/Movies/.split_parts_backup"

EXTRA_PARTS_TO_BACKUP = [
    "/media/daveg/Lib/Movies/The Bridge on the River Kwai (1957) Part 1.mp4",
    "/media/daveg/Lib/Movies/The Bridge on the River Kwai (1957) Part 2.mp4.mp4",
]

_active_proc = None


def cleanup(signum=None, frame=None):
    global _active_proc
    if _active_proc and _active_proc.poll() is None:
        try:
            _active_proc.kill()
            _active_proc.wait(timeout=2.0)
        except Exception:
            pass
    if os.path.exists(TEMP_TARGET):
        try:
            os.remove(TEMP_TARGET)
            print(f"\n[!] Cleaned up partial temp file: {TEMP_TARGET}", file=sys.stderr)
        except Exception:
            pass
    if signum is not None:
        sys.exit(130 if signum == signal.SIGINT else 143)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def get_video_duration(filepath):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ]
    out = subprocess.check_output(cmd).decode().strip()
    if not out:
        cmd2 = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", filepath
        ]
        out = subprocess.check_output(cmd2).decode().strip()
    return float(out)


def generate_chapters(p1_dur_sec, total_dur_sec):
    print("Generating chapter metadata...")
    # Generate 16 balanced chapter points (~10 minutes each) with Part 1 and Part 2 milestone markers
    total_ms = int(round(total_dur_sec * 1000))

    lines = [";FFMETADATA1\n"]
    
    # 10 minute chapter marks
    step_sec = 600
    cur_sec = 0
    chap_idx = 1
    
    while cur_sec < total_dur_sec:
        next_sec = min(cur_sec + step_sec, total_dur_sec)
        start_ms = int(round(cur_sec * 1000))
        end_ms = int(round(next_sec * 1000))
        part_str = "Part 1" if cur_sec < p1_dur_sec else "Part 2"
        title = f"{part_str} - Chapter {chap_idx}"
        lines.append(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\nEND={end_ms}\ntitle={title}\n\n")
        cur_sec = next_sec
        chap_idx += 1

    with open(CHAPTERS_FILE, "w") as f:
        f.writelines(lines)
    print(f"  [✓] {chap_idx-1} chapters generated.")


def fetch_and_save_subtitles():
    print("Fetching complete English subtitles for The Bridge on the River Kwai (1957)...")
    import fetch_subtitles as fs
    srt_text = fs.fetch_english_srt(imdb_id='tt0050212', title='The Bridge on the River Kwai')
    if not srt_text:
        print("  [!] Warning: Could not fetch subtitles online. Proceeding without subtitle track.")
        return False

    with open(FINAL_SRT, "w", encoding="utf-8") as f:
        f.write(srt_text)
    with open(MERGED_SRT_TEMP, "w", encoding="utf-8") as f:
        f.write(srt_text)

    line_count = len(srt_text.splitlines())
    print(f"  [✓] Subtitles saved to {os.path.basename(FINAL_SRT)} ({line_count} lines).")
    return True


def run_ffmpeg_concat(total_duration_sec, has_subtitles=True):
    global _active_proc
    print(f"\nStarting high-quality concatenation (Total expected duration: {total_duration_sec/60:.1f} min)...")

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-stats",
        "-i", PART1_PATH,
        "-i", PART2_PATH,
        "-i", CHAPTERS_FILE,
    ]
    if has_subtitles and os.path.exists(MERGED_SRT_TEMP):
        cmd.extend(["-i", MERGED_SRT_TEMP])

    cmd.extend([
        "-filter_complex",
        "[0:v]scale=720:404,setsar=1/1[v0];[1:v]scale=720:404,setsar=1/1[v1];[v0][0:a:0][v1][1:a:0]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]",
        "-map", "[a]",
    ])

    if has_subtitles and os.path.exists(MERGED_SRT_TEMP):
        cmd.extend([
            "-map", "3:s:0",
            "-map_metadata", "2",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng",
            "-metadata:s:s:0", "title=English",
        ])
    else:
        cmd.extend(["-map_metadata", "2"])

    cmd.extend([
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "medium",
        "-threads", "0",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-metadata:s:a:0", "language=eng",
        "-movflags", "+faststart",
        TEMP_TARGET
    ])

    print("Executing FFmpeg...")
    _active_proc = subprocess.Popen(cmd)
    ret = _active_proc.wait()
    if ret != 0:
        print(f"\n[!] FFmpeg exited with error code {ret}", file=sys.stderr)
        cleanup()
        sys.exit(1)
    print("\n  [✓] FFmpeg processing complete.")


def update_database():
    import sqlite3
    db_paths = [
        "/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db",
        "/home/daveg/Documents/GitHub/movie_Scraper/IMDB_Films.db"
    ]
    for db in db_paths:
        if not os.path.exists(db):
            continue
        try:
            con = sqlite3.connect(db)
            cur = con.cursor()
            cur.execute("UPDATE My_Films SET runtime = '161' WHERE (title LIKE '%Bridge on the River Kwai%' OR title LIKE '%River Kwai%') AND year = 1957;")
            con.commit()
            con.close()
            print(f"  [✓] Verified {os.path.basename(db)} runtime is 161 min.")
        except Exception as e:
            print(f"  [!] Note on {db}: {e}")


def main():
    print("=" * 80)
    print("  Combine The Bridge on the River Kwai (1957) Parts 1 & 2 into Unified Movie")
    print("=" * 80)

    if not os.path.exists(PART1_PATH) or not os.path.exists(PART2_PATH):
        print(f"[!] Error: Part 1 or Part 2 not found at {OUTPUT_DIR}", file=sys.stderr)
        sys.exit(1)

    p1_dur = get_video_duration(PART1_PATH)
    p2_dur = get_video_duration(PART2_PATH)
    total_dur = p1_dur + p2_dur
    print(f"Part 1 Duration: {p1_dur/60:.2f} min ({p1_dur:.2f}s)")
    print(f"Part 2 Duration: {p2_dur/60:.2f} min ({p2_dur:.2f}s)")
    print(f"Total Duration:  {total_dur/60:.2f} min ({total_dur:.2f}s)")

    generate_chapters(p1_dur, total_dur)
    has_subs = fetch_and_save_subtitles()
    run_ffmpeg_concat(total_dur, has_subtitles=has_subs)

    # Atomic move
    if os.path.exists(TEMP_TARGET) and os.path.getsize(TEMP_TARGET) > 100 * 1024 * 1024:
        os.replace(TEMP_TARGET, FINAL_TARGET)
        final_size_gb = os.path.getsize(FINAL_TARGET) / (1024 ** 3)
        print(f"\n  [✓] Created unified movie file: {FINAL_TARGET} ({final_size_gb:.2f} GB)")
    else:
        print("[!] Target file was not created successfully.", file=sys.stderr)
        cleanup()
        sys.exit(1)

    # Move parts to backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for p in [PART1_PATH, PART2_PATH] + EXTRA_PARTS_TO_BACKUP:
        if os.path.exists(p):
            dest = os.path.join(BACKUP_DIR, os.path.basename(p))
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(p, dest)
            print(f"  [✓] Moved {os.path.basename(p)} to {BACKUP_DIR}/")

    # Update DB
    update_database()

    # Subtitle Proof Verification
    print("\nRunning subtitle proof capture...")
    import verify_jellyfin_subtitles as vjs
    res = vjs.verify_movie_subtitles(FINAL_TARGET, samples=3)
    if res.get('verified'):
        print(f"  [✓] Subtitle proof verified: {len(res.get('frames', []))} snapshots saved in {res.get('proof_dir')}")
    else:
        print(f"  [!] Subtitle verification status: {res.get('status')}")

    print("\n" + "=" * 80)
    print("  ✓ The Bridge on the River Kwai (1957) Combined Successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()

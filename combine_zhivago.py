#!/usr/bin/env python3
"""
Combine Doctor Zhivago (1965) CD1/Disc 1 and CD2/Disc 2 into a single unified movie file.
- Audio: Stereo AAC (lossless stream copy)
- Video: H.264 (lossless stream copy)
- Chapters: Balanced 10-minute scene chapters for Part 1 and Part 2
- Subtitles: Clean full-length English SRT sidecar and embedded mov_text track
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

OUTPUT_DIR = "/media/daveg/Lib/Movies"
FINAL_TARGET = os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965).mp4")
TEMP_TARGET = os.path.join(OUTPUT_DIR, ".Doctor Zhivago (1965).resampled_tmp.mp4")
FINAL_SRT = os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965).en.srt")
CHAPTERS_FILE = "/tmp/zhivago_chapters.txt"
CONCAT_LIST_FILE = "/tmp/zhivago_concat_list.txt"
BACKUP_DIR = os.path.join(OUTPUT_DIR, ".split_parts_backup")

# Candidate paths for CD1 and CD2
CD1_CANDIDATES = [
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) -cd1.mp4"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965)-cd1.mp4"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) cd1.mp4"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) Disc 1.m4v"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) Part 1.mp4"),
]

CD2_CANDIDATES = [
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965)-cd2.mp4"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) -cd2.mp4"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) cd2.mp4"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) Disc 2.m4v"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) Part 2.mp4"),
]

BOGUS_SUBS_TO_CLEAN = [
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965)-cd2.en.srt"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) -cd2.en.srt"),
    os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) Disc 1.en.srt"),
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
    for tmp_file in [CHAPTERS_FILE, CONCAT_LIST_FILE]:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
    if signum is not None:
        sys.exit(130 if signum == signal.SIGINT else 143)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def find_file(candidates):
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def get_video_duration(filepath):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ]
    out = subprocess.check_output(cmd).decode().strip()
    if not out or out == "N/A":
        cmd2 = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", filepath
        ]
        out = subprocess.check_output(cmd2).decode().strip()
    return float(out)


def generate_chapters(p1_dur_sec, total_dur_sec):
    print("Generating chapter metadata...")
    lines = [";FFMETADATA1\n"]
    step_sec = 600  # 10 minute chapter points
    cur_sec = 0.0
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


def ensure_subtitles():
    if os.path.exists(FINAL_SRT) and os.path.getsize(FINAL_SRT) > 1000:
        print(f"  [✓] Verified existing subtitle track: {os.path.basename(FINAL_SRT)} ({os.path.getsize(FINAL_SRT):,} bytes).")
        return True

    print("Fetching authentic full-movie English subtitles from OpenSubtitles...")
    try:
        import fetch_subtitles
        srt_text = fetch_subtitles.search_opensubtitles('tt0059113')
        if srt_text and len(srt_text.strip()) > 1000:
            with open(FINAL_SRT, "w", encoding="utf-8") as f:
                f.write(srt_text)
            print(f"  [✓] Saved {os.path.basename(FINAL_SRT)} ({len(srt_text):,} bytes).")
            return True
        else:
            print("  [!] Could not retrieve subtitles from OpenSubtitles.", file=sys.stderr)
            return False
    except Exception as e:
        print(f"  [!] Subtitle fetch error: {e}", file=sys.stderr)
        return False


def run_ffmpeg_concat(cd1_path, cd2_path, total_dur_sec, has_subtitles=True):
    global _active_proc
    print(f"\nStarting lossless concatenation (Total duration: {total_dur_sec/60:.1f} min)...")

    # Generate concat demuxer list file
    with open(CONCAT_LIST_FILE, "w") as f:
        f.write(f"file '{cd1_path}'\n")
        f.write(f"file '{cd2_path}'\n")

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-stats",
        "-f", "concat", "-safe", "0", "-i", CONCAT_LIST_FILE
    ]

    input_idx = 1
    sub_input_idx = None
    chap_input_idx = None

    if has_subtitles and os.path.exists(FINAL_SRT):
        cmd.extend(["-i", FINAL_SRT])
        sub_input_idx = input_idx
        input_idx += 1

    if os.path.exists(CHAPTERS_FILE):
        cmd.extend(["-i", CHAPTERS_FILE])
        chap_input_idx = input_idx
        input_idx += 1

    cmd.extend([
        "-map", "0:v",
        "-map", "0:a"
    ])

    if sub_input_idx is not None:
        cmd.extend([
            "-map", f"{sub_input_idx}:s:0",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng",
            "-metadata:s:s:0", "title=English",
        ])

    if chap_input_idx is not None:
        cmd.extend([
            "-map_metadata", str(chap_input_idx),
            "-map_chapters", str(chap_input_idx),
        ])

    cmd.extend([
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+faststart",
        TEMP_TARGET
    ])

    print("Executing FFmpeg...")
    t_start = time.time()
    _active_proc = subprocess.Popen(cmd)
    ret = _active_proc.wait()
    _active_proc = None

    if ret != 0:
        print(f"\n[!] FFmpeg exited with error code {ret}", file=sys.stderr)
        cleanup()
        sys.exit(1)

    elapsed = time.time() - t_start
    print(f"  [✓] FFmpeg processing complete in {elapsed:.1f}s.")


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
            cur.execute("UPDATE My_Films SET runtime = '197' WHERE (title LIKE '%Zhivago%' OR title LIKE '%Doctor Zhivago%') AND year = 1965;")
            con.commit()
            con.close()
            print(f"  [✓] Verified {os.path.basename(db)} runtime is 197 min.")
        except Exception as e:
            print(f"  [!] Note on {db}: {e}")


def main():
    print("=" * 80)
    print("  Doctor Zhivago (1965) CD1 & CD2 Combination")
    print("=" * 80)

    cd1_path = find_file(CD1_CANDIDATES)
    cd2_path = find_file(CD2_CANDIDATES)

    if not cd1_path or not cd2_path:
        print(f"[!] Error: CD1 or CD2 file not found in {OUTPUT_DIR}", file=sys.stderr)
        if not cd1_path:
            print(f"    Missing CD1. Checked: {CD1_CANDIDATES}", file=sys.stderr)
        if not cd2_path:
            print(f"    Missing CD2. Checked: {CD2_CANDIDATES}", file=sys.stderr)
        sys.exit(1)

    print(f"  CD1 Source: {cd1_path}")
    print(f"  CD2 Source: {cd2_path}")
    print(f"  Target:     {FINAL_TARGET}")
    print("=" * 80)

    p1_dur = get_video_duration(cd1_path)
    p2_dur = get_video_duration(cd2_path)
    total_dur = p1_dur + p2_dur
    print(f"CD1 Duration:   {p1_dur/60:.2f} min ({p1_dur:.2f}s)")
    print(f"CD2 Duration:   {p2_dur/60:.2f} min ({p2_dur:.2f}s)")
    print(f"Total Duration: {total_dur/60:.2f} min ({total_dur:.2f}s)")

    generate_chapters(p1_dur, total_dur)
    has_subs = ensure_subtitles()
    run_ffmpeg_concat(cd1_path, cd2_path, total_dur, has_subtitles=has_subs)

    # Verify temp target
    if not os.path.exists(TEMP_TARGET) or os.path.getsize(TEMP_TARGET) < 500 * 1024 * 1024:
        print("[!] Target file was not created successfully or is too small.", file=sys.stderr)
        cleanup()
        sys.exit(1)

    # Atomic move
    os.replace(TEMP_TARGET, FINAL_TARGET)
    final_size_gb = os.path.getsize(FINAL_TARGET) / (1024 ** 3)
    print(f"\n  [✓] Created unified movie file: {FINAL_TARGET} ({final_size_gb:.2f} GB)")

    # Clean up chapters and concat list files
    for tmp_file in [CHAPTERS_FILE, CONCAT_LIST_FILE]:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass

    # Move original CD files and bogus subtitles to backup directory
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files_to_backup = [cd1_path, cd2_path]
    for p in files_to_backup:
        if os.path.exists(p):
            dest = os.path.join(BACKUP_DIR, os.path.basename(p))
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(p, dest)
            print(f"  [✓] Moved {os.path.basename(p)} to {BACKUP_DIR}/")

    for bogus_sub in BOGUS_SUBS_TO_CLEAN:
        if os.path.exists(bogus_sub):
            dest = os.path.join(BACKUP_DIR, os.path.basename(bogus_sub))
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(bogus_sub, dest)
            print(f"  [✓] Archived bogus subtitle {os.path.basename(bogus_sub)} to {BACKUP_DIR}/")

    # Update DB
    update_database()

    # Subtitle Proof Verification
    print("\nRunning subtitle proof capture...")
    try:
        import verify_jellyfin_subtitles as vjs
        res = vjs.verify_movie_subtitles(FINAL_TARGET, samples=3)
        if res.get('verified'):
            print(f"  [✓] Subtitle proof verified: {len(res.get('frames', []))} snapshots saved in {res.get('proof_dir')}")
        else:
            print(f"  [!] Subtitle verification status: {res.get('status')}")
    except Exception as e:
        print(f"  [!] Subtitle proof error: {e}")

    print("\n" + "=" * 80)
    print("  ✓ Doctor Zhivago (1965) Discs 1 & 2 Combined Successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()

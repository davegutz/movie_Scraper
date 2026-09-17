#!/usr/bin/env python3
"""
Combine Shackleton (2002) Part 1 and Part 2 into a single unified movie file.
- Audio: Stereo AAC (160k, eng)
- Video: H.264 (CRF 20, preset medium, SAR 32:27, 720x480, yuv420p)
- Chapters: Complete 24 chapters merged from both parts
- Subtitles: Unified English SRT sidecar and embedded mov_text track
- Proof: Automatic 3-sample quality control verification in subtitle_proof/
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time

PART1_PATH = "/media/daveg/Lib/Movies/Shackleton (2002) Part 1.m4v"
PART2_PATH = "/media/daveg/Lib/Movies/Shackleton (2002) Part 2.m4v"
OUTPUT_DIR = "/media/daveg/Lib/Movies"
FINAL_TARGET = os.path.join(OUTPUT_DIR, "Shackleton (2002).m4v")
TEMP_TARGET = os.path.join(OUTPUT_DIR, ".Shackleton (2002).resampled_tmp.m4v")
FINAL_SRT = os.path.join(OUTPUT_DIR, "Shackleton (2002).en.srt")
CHAPTERS_FILE = "/tmp/shackleton_chapters.txt"
MERGED_SRT_TEMP = "/tmp/shackleton_merged.srt"
BACKUP_DIR = "/media/daveg/Lib/Movies/.split_parts_backup"

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


def get_chapters(filepath):
    cmd = ["ffprobe", "-v", "error", "-show_chapters", "-print_format", "json", filepath]
    out = subprocess.check_output(cmd)
    return json.loads(out).get("chapters", [])


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


def generate_chapters(p1_dur_sec):
    print("Generating unified 24-chapter metadata...")
    p1_ch = get_chapters(PART1_PATH)
    p2_ch = get_chapters(PART2_PATH)
    p1_offset_ms = int(round(p1_dur_sec * 1000))

    lines = [";FFMETADATA1\n"]
    for ch in p1_ch:
        start_ms = int(round(float(ch['start_time']) * 1000))
        end_ms = int(round(float(ch['end_time']) * 1000))
        title = ch.get('tags', {}).get('title', f"Chapter {ch['id']+1}")
        lines.append(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\nEND={end_ms}\ntitle=Part 1: {title}\n\n")

    for ch in p2_ch:
        start_ms = int(round(float(ch['start_time']) * 1000)) + p1_offset_ms
        end_ms = int(round(float(ch['end_time']) * 1000)) + p1_offset_ms
        title = ch.get('tags', {}).get('title', f"Chapter {len(p1_ch) + ch['id'] + 1}")
        lines.append(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\nEND={end_ms}\ntitle=Part 2: {title}\n\n")

    with open(CHAPTERS_FILE, "w") as f:
        f.writelines(lines)
    print(f"  [✓] {len(p1_ch) + len(p2_ch)} chapters generated.")


def format_srt_time(sec):
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def merge_subtitles(p1_dur_sec):
    print("Extracting and merging English subtitles from Part 1 and Part 2...")
    import verify_jellyfin_subtitles as vjs
    
    stype1, starget1, _ = vjs.get_subtitle_source(PART1_PATH)
    stype2, starget2, _ = vjs.get_subtitle_source(PART2_PATH)
    
    cues1 = vjs.extract_cues(PART1_PATH, stype1, starget1)
    cues2 = vjs.extract_cues(PART2_PATH, stype2, starget2)
    
    srt_lines = []
    idx = 1
    for c in cues1:
        s_str = format_srt_time(c['start'])
        e_str = format_srt_time(c['end'])
        text = c['raw_text'].replace('<font size="23">', '').replace('</font>', '')
        text = text.replace('<font color="#ffff00">', '').replace('<font color="#ffffff">', '')
        srt_lines.append(f"{idx}\n{s_str} --> {e_str}\n{text}\n\n")
        idx += 1
        
    for c in cues2:
        s_str = format_srt_time(c['start'] + p1_dur_sec)
        e_str = format_srt_time(c['end'] + p1_dur_sec)
        text = c['raw_text'].replace('<font size="23">', '').replace('</font>', '')
        text = text.replace('<font color="#ffff00">', '').replace('<font color="#ffffff">', '')
        srt_lines.append(f"{idx}\n{s_str} --> {e_str}\n{text}\n\n")
        idx += 1

    srt_content = "".join(srt_lines)
    with open(FINAL_SRT, "w", encoding="utf-8") as f:
        f.write(srt_content)
    with open(MERGED_SRT_TEMP, "w", encoding="utf-8") as f:
        f.write(srt_content)
        
    print(f"  [✓] Merged {idx-1} subtitle cues into {os.path.basename(FINAL_SRT)}.")


def run_ffmpeg_concat(total_duration_sec):
    global _active_proc
    print(f"\nStarting high-quality concatenation (Total expected duration: {total_duration_sec/60:.1f} min)...")
    
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-stats",
        "-i", PART1_PATH,
        "-i", PART2_PATH,
        "-i", CHAPTERS_FILE,
        "-i", MERGED_SRT_TEMP,
        "-filter_complex",
        "[0:v]scale=720:480,setsar=32/27[v0];[1:v]scale=720:480,setsar=32/27[v1];[v0][0:a:0][v1][1:a:0]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]",
        "-map", "[a]",
        "-map", "3:s:0",
        "-map_metadata", "2",
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "superfast",
        "-threads", "0",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-c:s", "mov_text",
        "-metadata:s:s:0", "language=eng",
        "-metadata:s:s:0", "title=English",
        "-metadata:s:a:0", "language=eng",
        "-movflags", "+faststart",
        TEMP_TARGET
    ]
    
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
            cur.execute("UPDATE My_Films SET Time = 205 WHERE Title = 'Shackleton' AND Year = 2002;")
            con.commit()
            con.close()
            print(f"  [✓] Updated {os.path.basename(db)} runtime to 205 min.")
        except Exception as e:
            print(f"  [!] Note on {db}: {e}")


def main():
    print("=" * 80)
    print("  Combine Shackleton (2002) Parts 1 & 2 into Unified Movie")
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

    generate_chapters(p1_dur)
    merge_subtitles(p1_dur)
    run_ffmpeg_concat(total_dur)

    # Atomic move
    if os.path.exists(TEMP_TARGET) and os.path.getsize(TEMP_TARGET) > 100 * 1024 * 1024:
        os.replace(TEMP_TARGET, FINAL_TARGET)
        print(f"\n  [✓] Created unified movie file: {FINAL_TARGET} ({os.path.getsize(FINAL_TARGET)/(1024**3):.2f} GB)")
    else:
        print("[!] Target file was not created successfully.", file=sys.stderr)
        cleanup()
        sys.exit(1)

    # Move parts to backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil_dest1 = os.path.join(BACKUP_DIR, os.path.basename(PART1_PATH))
    shutil_dest2 = os.path.join(BACKUP_DIR, os.path.basename(PART2_PATH))
    
    import shutil
    shutil.move(PART1_PATH, shutil_dest1)
    shutil.move(PART2_PATH, shutil_dest2)
    print(f"  [✓] Moved Part 1 & Part 2 to {BACKUP_DIR}/")

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
    print("  ✓ Shackleton (2002) Parts 1 & 2 Combined Successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()

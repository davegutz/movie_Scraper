#!/usr/bin/env python3
"""
Combine Doctor Zhivago (1965) Disc 1 and Disc 2 into a single unified movie file.
- Audio: Stereo AAC (160k) + Surround AC-3 (448k)
- Video: H.264 (CRF 20, preset medium, SAR 32:27, yuv420p)
- Chapters: Complete 61 chapters merged from both discs
- Subtitles: Clean full-length English SRT fetched from OpenSubtitles
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time

DISC1_PATH = "/media/daveg/Lib/Movies/Doctor Zhivago (1965) Disc 1.m4v"
DISC2_PATH = "/media/daveg/Lib/Movies/Doctor Zhivago (1965) Disc 2.m4v"
OUTPUT_DIR = "/media/daveg/Lib/Movies"
FINAL_TARGET = os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965).m4v")
TEMP_TARGET = os.path.join(OUTPUT_DIR, ".Doctor Zhivago (1965).resampled_tmp.m4v")
FINAL_SRT = os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965).en.srt")
OLD_SRT = os.path.join(OUTPUT_DIR, "Doctor Zhivago (1965) Disc 1.en.srt")
CHAPTERS_FILE = "/tmp/zhivago_chapters.txt"

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
    return float(subprocess.check_output(cmd).decode().strip())


def generate_chapters():
    print("Generating unified 61-chapter metadata...")
    d1_ch = get_chapters(DISC1_PATH)
    d2_ch = get_chapters(DISC2_PATH)
    d1_dur_sec = get_video_duration(DISC1_PATH)
    d1_offset_ms = int(round(d1_dur_sec * 1000))

    lines = [";FFMETADATA1\n"]
    for ch in d1_ch:
        start_ms = int(round(float(ch['start_time']) * 1000))
        end_ms = int(round(float(ch['end_time']) * 1000))
        title = ch.get('tags', {}).get('title', f"Chapter {ch['id']+1}")
        lines.append(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\nEND={end_ms}\ntitle={title}\n\n")

    for ch in d2_ch:
        start_ms = int(round(float(ch['start_time']) * 1000)) + d1_offset_ms
        end_ms = int(round(float(ch['end_time']) * 1000)) + d1_offset_ms
        title = ch.get('tags', {}).get('title', f"Chapter {len(d1_ch) + ch['id'] + 1}")
        lines.append(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\nEND={end_ms}\ntitle={title}\n\n")

    with open(CHAPTERS_FILE, "w") as f:
        f.writelines(lines)
    print(f"  [✓] {len(d1_ch) + len(d2_ch)} chapters generated.")


def download_subtitles():
    print("Fetching authentic full-movie English subtitles...")
    try:
        import fetch_subtitles
        srt_text = fetch_subtitles.search_opensubtitles('tt0059113')
        if srt_text and len(srt_text.strip()) > 1000:
            with open(FINAL_SRT, "w", encoding="utf-8") as f:
                f.write(srt_text)
            print(f"  [✓] Saved {os.path.basename(FINAL_SRT)} ({len(srt_text):,} bytes).")
            if os.path.exists(OLD_SRT):
                try:
                    os.remove(OLD_SRT)
                    print(f"  [✓] Removed bogus {os.path.basename(OLD_SRT)}.")
                except Exception:
                    pass
        else:
            print("  [!] Could not retrieve subtitles from OpenSubtitles.", file=sys.stderr)
    except Exception as e:
        print(f"  [!] Subtitle fetch error: {e}", file=sys.stderr)


def main():
    global _active_proc

    if not os.path.isfile(DISC1_PATH) or not os.path.isfile(DISC2_PATH):
        print(f"Error: Disc files not found in {OUTPUT_DIR}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print("  Doctor Zhivago (1965) Discs 1 & 2 Combination")
    print("=" * 80)
    print(f"  Disc 1: {DISC1_PATH}")
    print(f"  Disc 2: {DISC2_PATH}")
    print(f"  Target: {FINAL_TARGET}")
    print("=" * 80)

    # 1. Generate unified chapters
    generate_chapters()

    # 2. Download subtitles
    download_subtitles()

    # 3. Calculate total duration
    d1_dur = get_video_duration(DISC1_PATH)
    d2_dur = get_video_duration(DISC2_PATH)
    total_dur_sec = d1_dur + d2_dur
    tot_h = int(total_dur_sec // 3600)
    tot_m = int((total_dur_sec % 3600) // 60)
    tot_s = int(total_dur_sec % 60)
    print(f"Total Combined Duration: {tot_h:02d}:{tot_m:02d}:{tot_s:02d} ({total_dur_sec:.1f}s)")

    # 4. Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-i", DISC1_PATH,
        "-i", DISC2_PATH,
        "-i", CHAPTERS_FILE,
        "-filter_complex", "[0:v][0:a:0][0:a:1][1:v][1:a:0][1:a:1]concat=n=2:v=1:a=2[outv][outa1][outa2]",
        "-map", "[outv]",
        "-map", "[outa1]",
        "-map", "[outa2]",
        "-map_metadata", "2",
        "-map_chapters", "2",
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a:0", "aac",
        "-b:a:0", "160k",
        "-metadata:s:a:0", "language=eng",
        "-metadata:s:a:0", "title=Stereo",
        "-c:a:1", "ac3",
        "-b:a:1", "448k",
        "-metadata:s:a:1", "language=eng",
        "-metadata:s:a:1", "title=Surround",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        TEMP_TARGET
    ]

    print("\nStarting video and audio concatenation with H.264 CRF 20 re-encode...")
    t_start = time.time()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    _active_proc = proc

    stderr_lines = []
    stderr_thread = threading.Thread(
        target=lambda: stderr_lines.extend(proc.stderr.readlines()),
        daemon=True
    )
    stderr_thread.start()

    cur_stats = {}
    last_print = 0.0

    try:
        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    cur_stats[k.strip()] = v.strip()
                if line.startswith('progress='):
                    now = time.time()
                    if now - last_print >= 0.5 or cur_stats.get('progress') == 'end':
                        out_time_raw = cur_stats.get('out_time', '')
                        if out_time_raw and out_time_raw != 'N/A':
                            out_time_disp = out_time_raw.split('.')[0]
                            fps = cur_stats.get('fps', '0')
                            speed = cur_stats.get('speed', '0x')
                            # Parse out_time to sec
                            parts = out_time_disp.split(':')
                            pct_str = ""
                            if len(parts) == 3:
                                cur_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                                pct = min(100.0, (cur_sec / total_dur_sec) * 100.0)
                                pct_str = f" ({pct:4.1f}%)"
                            msg = f"    [FFmpeg] time={out_time_disp} / {tot_h:02d}:{tot_m:02d}:{tot_s:02d}{pct_str} | fps={fps} | speed={speed}"
                            sys.stdout.write("\r" + f"{msg:<85}")
                            sys.stdout.flush()
                            last_print = now
        proc.wait()
        stderr_thread.join(timeout=2.0)
        sys.stdout.write("\n")
        sys.stdout.flush()
    except KeyboardInterrupt:
        cleanup()
        raise

    _active_proc = None

    if proc.returncode != 0:
        err_msg = "".join(stderr_lines)
        print(f"Error: FFmpeg failed with code {proc.returncode}:\n{err_msg[-1000:]}", file=sys.stderr)
        cleanup()
        sys.exit(1)

    # 5. Verify output file
    if not os.path.exists(TEMP_TARGET) or os.path.getsize(TEMP_TARGET) < 500 * 1024 * 1024:
        print("Error: Output file does not exist or is too small!", file=sys.stderr)
        cleanup()
        sys.exit(1)

    out_size = os.path.getsize(TEMP_TARGET)
    out_gb = out_size / (1024 ** 3)
    elapsed = time.time() - t_start

    print(f"\nEncoding Complete in {elapsed/60:.1f} minutes!")
    print(f"Output File Size: {out_gb:.2f} GB")

    # 6. Atomic swap and backup originals
    print("\nBacking up original Disc files and finalizing output...")
    os.replace(TEMP_TARGET, FINAL_TARGET)
    print(f"  [✓] Created: {FINAL_TARGET}")

    d1_bak = f"{DISC1_PATH}.bak"
    d2_bak = f"{DISC2_PATH}.bak"
    if os.path.exists(DISC1_PATH):
        os.replace(DISC1_PATH, d1_bak)
        print(f"  [✓] Backed up Disc 1 to: {os.path.basename(d1_bak)}")
    if os.path.exists(DISC2_PATH):
        os.replace(DISC2_PATH, d2_bak)
        print(f"  [✓] Backed up Disc 2 to: {os.path.basename(d2_bak)}")

    # Clean up chapters file
    if os.path.exists(CHAPTERS_FILE):
        try:
            os.remove(CHAPTERS_FILE)
        except Exception:
            pass

    print("\n" + "=" * 80)
    print("  Doctor Zhivago (1965) Discs 1 & 2 Successfully Combined!")
    print("=" * 80)


if __name__ == "__main__":
    main()

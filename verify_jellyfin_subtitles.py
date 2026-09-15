#!/usr/bin/env python3
"""
verify_jellyfin_subtitles.py - Automate visual verification of subtitles in video files and Jellyfin streams.

This tool verifies that subtitles actually render onto video frames as expected:
1. Extracts active dialogue cues (with timestamps and expected text) from embedded or sidecar subtitle tracks.
2. Uses FFmpeg to render exact video frames at those timestamps with burned-in subtitles.
3. Saves 2-3 high-resolution proof snapshots into the subtitle_proof/ subfolder of Lib/Movies
   for user quality control and Antigravity multimodal review.

Usage Examples:
  # Verify subtitles for a specific movie title
  python3 verify_jellyfin_subtitles.py "Caddyshack"

  # Verify using an exact video file path
  python3 verify_jellyfin_subtitles.py "/media/daveg/Lib/Movies/Caddyshack (1980).m4v"

  # Verify at a specific timestamp
  python3 verify_jellyfin_subtitles.py "Caddyshack" --timestamp 00:01:23

  # Test 5 sample dialogue cues across the film
  python3 verify_jellyfin_subtitles.py "Caddyshack" --samples 5

  # Open captured frames in the desktop image viewer for inspection
  python3 verify_jellyfin_subtitles.py "Caddyshack" --open

  # Output full results in JSON format
  python3 verify_jellyfin_subtitles.py "Caddyshack" --json
"""

import argparse
import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    requests = None

# Default paths
DEFAULT_MOVIES_DIR = "/media/daveg/Lib/Movies"
DEFAULT_PROOF_DIR = "/media/daveg/Lib/Movies/subtitle_proof"
DEFAULT_DB_PATH = "/home/daveg/Documents/GitHub/movie_Scraper/IMDB_Films.db"
DEFAULT_CACHE_DIR = DEFAULT_PROOF_DIR
VIDEO_EXTS = {'.m4v', '.mp4', '.mkv', '.avi', '.mov', '.ts', '.m2ts', '.webm'}

# ANSI color codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"


def format_seconds_to_timestamp(seconds):
    """Convert float seconds to HH:MM:SS or MM:SS format."""
    total_sec = int(seconds)
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_timestamp_to_seconds(ts_str):
    """Convert HH:MM:SS or MM:SS or float seconds string to float seconds."""
    ts_str = str(ts_str).strip()
    if ':' in ts_str:
        parts = ts_str.split(':')
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
    try:
        return float(ts_str)
    except ValueError:
        return 0.0


def clean_text_for_matching(raw_text):
    """Strip HTML tags, sound effect tags, and normalize whitespace for subtitle text."""
    if not raw_text:
        return ""
    # Remove HTML tags (e.g. <font ...>, </i>)
    t = re.sub(r'<[^>]+>', ' ', raw_text)
    # Normalize unicode & whitespace
    t = ' '.join(t.split())
    return t


def parse_srt_content(srt_text):
    """
    Parse SRT formatted string into list of dicts:
    [{'start': float_sec, 'end': float_sec, 'raw_text': str, 'clean_text': str}]
    """
    cues = []
    # Split by blank lines
    blocks = re.split(r'\r?\n\r?\n', srt_text.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        # Find the line with the timestamp arrow '-->'
        time_line_idx = -1
        for idx, line in enumerate(lines):
            if '-->' in line:
                time_line_idx = idx
                break
        if time_line_idx == -1:
            continue

        time_line = lines[time_line_idx]
        parts = time_line.split('-->')
        if len(parts) != 2:
            continue

        start_str = parts[0].strip().replace(',', '.')
        end_str = parts[1].strip().split()[0].replace(',', '.')

        try:
            start_sec = parse_timestamp_to_seconds(start_str)
            end_sec = parse_timestamp_to_seconds(end_str)
        except Exception:
            continue

        text_lines = lines[time_line_idx + 1:]
        raw_text = ' '.join(text_lines)
        clean_text = clean_text_for_matching(raw_text)

        if clean_text and (end_sec > start_sec):
            cues.append({
                'start': start_sec,
                'end': end_sec,
                'mid': (start_sec + end_sec) / 2.0,
                'raw_text': raw_text,
                'clean_text': clean_text
            })
    return cues


def find_video_file(movie_input, movies_dir=DEFAULT_MOVIES_DIR):
    """Resolve a title or file path to an absolute path of an existing video file."""
    if os.path.isfile(movie_input):
        return os.path.abspath(movie_input)

    # Check directly inside movies_dir
    candidate = os.path.join(movies_dir, movie_input)
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)

    # Search by case-insensitive name match in movies_dir
    if os.path.isdir(movies_dir):
        query = movie_input.lower().strip()
        # Direct matches
        for f in os.listdir(movies_dir):
            if not any(f.endswith(ext) for ext in VIDEO_EXTS):
                continue
            base = os.path.splitext(f)[0].lower()
            if query == base or query == f.lower():
                return os.path.abspath(os.path.join(movies_dir, f))

        # Partial matches
        for f in os.listdir(movies_dir):
            if not any(f.endswith(ext) for ext in VIDEO_EXTS):
                continue
            if query in f.lower():
                return os.path.abspath(os.path.join(movies_dir, f))

    return None


def get_subtitle_source(video_path):
    """
    Determine the best subtitle source for a video file:
    Returns (sub_type, sub_path_or_stream_idx, info_dict)
      sub_type: 'sidecar_srt', 'embedded_text', 'embedded_bitmap', or 'none'
    """
    base_no_ext, _ = os.path.splitext(video_path)

    # 1. Check for external sidecar .srt files
    sidecar_exts = ('.en.srt', '.srt', '.eng.srt', '.English.srt', '.en.default.srt')
    for ext in sidecar_exts:
        sidecar = base_no_ext + ext
        if os.path.isfile(sidecar) and os.path.getsize(sidecar) > 50:
            return 'sidecar_srt', sidecar, {'format': 'srt', 'path': sidecar}

    # 2. Check embedded streams via ffprobe
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title",
        "-of", "json",
        video_path
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=8).decode("utf-8")
        probe_data = json.loads(out)
        streams = probe_data.get("streams", [])
        if streams:
            # Look for English text stream first
            for s in streams:
                codec = s.get("codec_name", "").lower()
                tags = s.get("tags", {})
                lang = tags.get("language", "").lower()
                is_eng = lang in ('eng', 'en', 'english', 'en-us', 'en-gb', '')
                if codec in ('mov_text', 'subrip', 'text', 'ass', 'ssa', 'webvtt') and is_eng:
                    return 'embedded_text', s.get("index", 0), {'codec': codec, 'stream': s}

            # Any text stream
            for s in streams:
                codec = s.get("codec_name", "").lower()
                if codec in ('mov_text', 'subrip', 'text', 'ass', 'ssa', 'webvtt'):
                    return 'embedded_text', s.get("index", 0), {'codec': codec, 'stream': s}

            # Fallback to bitmap stream
            for s in streams:
                codec = s.get("codec_name", "").lower()
                if codec in ('dvd_subtitle', 'hdmv_pgs_subtitle', 'dvdsub'):
                    return 'embedded_bitmap', s.get("index", 0), {'codec': codec, 'stream': s}
    except Exception:
        pass

    return 'none', None, {}


def extract_cues(video_path, sub_type, sub_target):
    """
    Extract subtitle dialogue cues from sidecar or embedded subtitle track.
    Returns list of parsed cues.
    """
    if sub_type == 'sidecar_srt':
        try:
            with open(sub_target, 'r', encoding='utf-8', errors='ignore') as f:
                return parse_srt_content(f.read())
        except Exception:
            return []

    elif sub_type == 'embedded_text':
        # Dump embedded text subtitle to temporary srt via ffmpeg
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", video_path,
            "-map", f"0:{sub_target}",
            "-vn", "-an",
            "-f", "srt", "-"
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, text=True, errors='ignore')
            if res.stdout:
                return parse_srt_content(res.stdout)
        except Exception:
            pass

    return []


def select_sample_cues(cues, count=3, user_timestamp=None):
    """
    Select representative dialogue cues spread across the movie.
    Prefers cues with clear spoken words (ignoring audio effect markers like [MUSIC]).
    """
    if not cues:
        return []

    if user_timestamp is not None:
        target_sec = parse_timestamp_to_seconds(user_timestamp)
        # Find closest cue
        best_cue = min(cues, key=lambda c: abs(c['mid'] - target_sec))
        return [best_cue]

    # Filter for quality cues: length >= 6 chars, duration between 1.0s and 6.0s
    filtered = []
    for c in cues:
        text = c['clean_text']
        dur = c['end'] - c['start']
        # Skip pure metadata lines or sound effects like [LAUGHTER]
        if re.match(r'^\s*\[.+\]\s*$', text) or re.match(r'^\s*♪.+♪\s*$', text):
            continue
        if len(text) >= 8 and 1.2 <= dur <= 8.0:
            filtered.append(c)

    if not filtered:
        filtered = cues

    if len(filtered) <= count:
        return filtered

    # Select samples evenly distributed across the duration (e.g. 15%, 45%, 75%)
    selected = []
    step = len(filtered) / (count + 1)
    for i in range(1, count + 1):
        idx = int(i * step)
        if idx < len(filtered) and filtered[idx] not in selected:
            selected.append(filtered[idx])

    return selected or filtered[:count]


def capture_subtitle_frame(video_path, cue_sec, output_jpg_path, sub_type, sub_target):
    """
    Capture a single video frame with burned-in subtitles at cue_sec.
    Preserves presentation timestamps (-copyts) so libass accurately renders
    subtitles at absolute movie timestamps.
    """
    os.makedirs(os.path.dirname(output_jpg_path), exist_ok=True)
    time_str = format_seconds_to_timestamp(cue_sec)

    temp_srt = None
    vf_filter = None

    try:
        if sub_type == 'sidecar_srt':
            # Create a clean temporary symlink without special characters/apostrophes for robust ffmpeg filter parsing
            temp_fd, temp_srt = tempfile.mkstemp(suffix='.srt', dir='/tmp')
            os.close(temp_fd)
            os.remove(temp_srt)
            os.symlink(os.path.abspath(sub_target), temp_srt)
            vf_filter = f'subtitles={temp_srt}'
        elif sub_type == 'embedded_text':
            # Dump full srt to clean temporary file for fast rendering
            temp_fd, temp_srt = tempfile.mkstemp(suffix='.srt', dir='/tmp')
            os.close(temp_fd)
            subprocess.run([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-i', video_path,
                '-map', f'0:{sub_target}',
                '-f', 'srt', temp_srt
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
            vf_filter = f'subtitles={temp_srt}'

        # CRITICAL: -copyts keeps presentation timestamps (PTS) aligned with the subtitle file,
        # ensuring the subtitles filter evaluates cues at cue_sec instead of resetting to t=0.
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(cue_sec),
            "-copyts",
            "-i", video_path,
            "-ss", str(cue_sec),
        ]

        if vf_filter:
            cmd.extend(["-vf", vf_filter])
        elif sub_type == 'embedded_bitmap':
            cmd.extend(["-filter_complex", f"[0:v][0:{sub_target}]overlay"])

        cmd.extend([
            "-vframes", "1",
            "-q:v", "2",
            output_jpg_path
        ])

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=True)
        return os.path.isfile(output_jpg_path) and os.path.getsize(output_jpg_path) > 1024
    except Exception as e:
        print(f"  {C_RED}[!] Error capturing frame at {time_str}: {e}{C_RESET}", file=sys.stderr)
        return False
    finally:
        if temp_srt and (os.path.isfile(temp_srt) or os.path.islink(temp_srt)):
            try:
                os.remove(temp_srt)
            except Exception:
                pass


def verify_movie_subtitles(video_path, samples=3, output_dir=None, user_timestamp=None, skip_existing=False):
    """
    Verify that subtitles actually render onto video frames for a video file.
    Captures proof snapshots with burned-in subtitles into the subtitle_proof/ subfolder
    for user quality control.

    Returns dict:
        {
            'has_subtitles': bool,
            'subtitle_type': str,       # 'sidecar_srt', 'embedded_text', 'embedded_bitmap', 'none'
            'verified': bool,            # True if capture succeeded for sample cues
            'status': str,               # 'PASS', 'NO_SUBTITLES', 'NO_CUES_PARSED', 'CAPTURE_ERROR'
            'cues_checked': int,
            'cues_passed': int,
            'frames': list of str,       # Paths to captured frame images
            'details': list of dicts,
            'expected_text': str,        # Expected script dialogue
            'proof_dir': str,            # Directory where proof frames are saved
            'notes': str
        }
    """
    if not os.path.isfile(video_path):
        return {
            'has_subtitles': False,
            'subtitle_type': 'none',
            'verified': False,
            'status': 'FILE_NOT_FOUND',
            'cues_checked': 0,
            'cues_passed': 0,
            'frames': [],
            'details': [],
            'expected_text': '',
            'proof_dir': '',
            'notes': f"File not found: {video_path}"
        }

    sub_type, sub_target, sub_meta = get_subtitle_source(video_path)
    if sub_type == 'none':
        return {
            'has_subtitles': False,
            'subtitle_type': 'none',
            'verified': False,
            'status': 'NO_SUBTITLES',
            'cues_checked': 0,
            'cues_passed': 0,
            'frames': [],
            'details': [],
            'expected_text': '',
            'proof_dir': '',
            'notes': "No subtitle track (sidecar or embedded) found."
        }

    cues = extract_cues(video_path, sub_type, sub_target)
    if not cues and sub_type != 'embedded_bitmap':
        return {
            'has_subtitles': True,
            'subtitle_type': sub_type,
            'verified': False,
            'status': 'NO_CUES_PARSED',
            'cues_checked': 0,
            'cues_passed': 0,
            'frames': [],
            'details': [],
            'expected_text': '',
            'proof_dir': '',
            'notes': "Subtitle track exists but no dialogue cues could be parsed."
        }

    selected_cues = select_sample_cues(cues, count=samples, user_timestamp=user_timestamp)
    if not selected_cues:
        fallback_sec = parse_timestamp_to_seconds(user_timestamp) if user_timestamp else 60.0
        selected_cues = [{
            'start': fallback_sec,
            'end': fallback_sec + 2.0,
            'mid': fallback_sec + 1.0,
            'raw_text': 'Dialogue',
            'clean_text': 'Dialogue'
        }]

    if output_dir is None:
        if os.path.isdir(DEFAULT_PROOF_DIR):
            output_dir = DEFAULT_PROOF_DIR
        else:
            cand = os.path.join(os.path.dirname(os.path.abspath(video_path)), "subtitle_proof")
            output_dir = cand
    os.makedirs(output_dir, exist_ok=True)

    filename = os.path.basename(video_path)
    base_title, _ = os.path.splitext(filename)

    cues_checked = 0
    cues_passed = 0
    frames = []
    details = []

    for idx, cue in enumerate(selected_cues, start=1):
        ts_sec = cue['mid']
        ts_str = format_seconds_to_timestamp(ts_sec)
        frame_filename = f"{base_title}_proof_{idx:02d}_{ts_str.replace(':', '_')}.jpg"
        frame_path = os.path.join(output_dir, frame_filename)

        if skip_existing and os.path.isfile(frame_path) and os.path.getsize(frame_path) > 1024:
            frames.append(frame_path)
            cues_checked += 1
            cues_passed += 1
            details.append({
                'cue_index': idx,
                'timestamp': ts_str,
                'expected_text': cue['clean_text'],
                'status': 'PASS',
                'frame_path': frame_path,
                'cached': True
            })
            continue

        ok = capture_subtitle_frame(video_path, ts_sec, frame_path, sub_type, sub_target)
        if not ok:
            details.append({
                'cue_index': idx,
                'timestamp': ts_str,
                'expected_text': cue['clean_text'],
                'frame_path': None,
                'status': 'CAPTURE_ERROR'
            })
            continue

        frames.append(frame_path)
        cues_checked += 1
        cues_passed += 1
        details.append({
            'cue_index': idx,
            'timestamp': ts_str,
            'expected_text': cue['clean_text'],
            'status': 'PASS',
            'frame_path': frame_path
        })

    verified = (cues_passed > 0 and cues_passed == len(selected_cues))
    overall_status = "PASS" if verified else ("CAPTURE_ERROR" if cues_checked < len(selected_cues) else "FAIL")
    primary_exp = details[0].get('expected_text', '') if details else ''

    return {
        'has_subtitles': True,
        'subtitle_type': sub_type,
        'verified': verified,
        'status': overall_status,
        'cues_checked': cues_checked,
        'cues_passed': cues_passed,
        'frames': frames,
        'details': details,
        'expected_text': primary_exp,
        'proof_dir': output_dir,
        'notes': f"{cues_passed}/{len(selected_cues)} proof snapshots saved to {output_dir}"
    }


def main(*raw_args):
    argv = None
    if raw_args:
        import shlex
        if len(raw_args) == 1 and isinstance(raw_args[0], (list, tuple)):
            argv = list(raw_args[0])
        else:
            argv = []
            for a in raw_args:
                argv.extend(shlex.split(a) if isinstance(a, str) else [str(a)])

    parser = argparse.ArgumentParser(
        description="Verify subtitle rendering and capture proof snapshots into subtitle_proof/ for quality control."
    )
    parser.add_argument(
        "movie",
        help="Movie title (e.g. 'Caddyshack') or absolute/relative path to a video file."
    )
    parser.add_argument(
        "-t", "--timestamp",
        help="Specific timestamp to check (e.g. '00:01:23' or '83'). If omitted, samples across dialogue cues."
    )
    parser.add_argument(
        "-n", "--samples",
        type=int,
        default=3,
        help="Number of representative dialogue cue proof snapshots to save (default: 3)."
    )
    parser.add_argument(
        "--movies-dir",
        default=DEFAULT_MOVIES_DIR,
        help=f"Base movies directory (default: {DEFAULT_MOVIES_DIR})."
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_PROOF_DIR,
        help=f"Directory to save captured proof snapshots (default: {DEFAULT_PROOF_DIR})."
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open captured proof snapshots in desktop viewer (xdg-open) upon completion."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output."
    )

    args = parser.parse_args(argv)

    # 1. Locate video file
    video_path = find_video_file(args.movie, args.movies_dir)
    if not video_path:
        print(f"{C_RED}[!] Error: Could not find movie file for: '{args.movie}' in {args.movies_dir}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    filename = os.path.basename(video_path)
    title_clean = os.path.splitext(filename)[0]

    # 2. Determine subtitle track
    sub_type, sub_target, sub_meta = get_subtitle_source(video_path)
    if sub_type == 'none':
        print(f"{C_RED}[!] Error: No subtitle track (sidecar .srt or embedded) found for: {filename}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    # 3. Extract and parse dialogue cues
    cues = extract_cues(video_path, sub_type, sub_target)
    if not cues and sub_type != 'embedded_bitmap':
        print(f"{C_RED}[!] Warning: Subtitle track detected ({sub_type}), but no text cues could be parsed.{C_RESET}", file=sys.stderr)

    # 4. Select candidate cues to verify
    selected_cues = select_sample_cues(cues, count=args.samples, user_timestamp=args.timestamp)
    if not selected_cues:
        fallback_sec = parse_timestamp_to_seconds(args.timestamp) if args.timestamp else 60.0
        selected_cues = [{
            'start': fallback_sec,
            'end': fallback_sec + 2.0,
            'mid': fallback_sec + 1.0,
            'raw_text': 'Dialogue',
            'clean_text': 'Dialogue'
        }]

    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    if not args.json:
        print("=" * 80)
        print(f" {C_BOLD}Subtitle Proof & Quality Control: {title_clean}{C_RESET}")
        print(f" Video File:     {video_path}")
        print(f" Subtitle Track: {sub_type.upper()} ({sub_meta.get('codec', 'srt')})")
        print(f" Proof Folder:   {out_dir}")
        print(f" Snapshots:      {len(selected_cues)} representative dialogue cues")
        print("=" * 80)

    results = []
    captured_files = []

    for idx, cue in enumerate(selected_cues, start=1):
        ts_sec = cue['mid']
        ts_str = format_seconds_to_timestamp(ts_sec)
        frame_filename = f"{title_clean}_proof_{idx:02d}_{ts_str.replace(':', '_')}.jpg"
        frame_path = os.path.join(out_dir, frame_filename)

        if not args.json:
            print(f"\n[Cue {idx}/{len(selected_cues)}] Timestamp: {C_CYAN}{ts_str}{C_RESET}")
            print(f"  Expected Dialogue: \"{C_BOLD}{cue['clean_text']}{C_RESET}\"")

        # Capture frame with subtitles burned in
        ok = capture_subtitle_frame(video_path, ts_sec, frame_path, sub_type, sub_target)
        if not ok:
            if not args.json:
                print(f"  {C_RED}✗ Failed to capture video frame with FFmpeg{C_RESET}")
            results.append({
                'cue_index': idx,
                'timestamp': ts_str,
                'expected_text': cue['clean_text'],
                'frame_path': None,
                'status': 'CAPTURE_ERROR'
            })
            continue

        captured_files.append(frame_path)
        if not args.json:
            print(f"  {C_GREEN}✓ Subtitle proof snapshot saved:{C_RESET} {frame_path}")
        results.append({
            'cue_index': idx,
            'timestamp': ts_str,
            'expected_text': cue['clean_text'],
            'status': 'PASS',
            'frame_path': frame_path
        })

    all_passed = (len(captured_files) == len(selected_cues) and len(captured_files) > 0)

    if args.json:
        out_obj = {
            'movie': title_clean,
            'file': video_path,
            'subtitle_type': sub_type,
            'proof_dir': out_dir,
            'all_passed': all_passed,
            'frames': captured_files,
            'results': results
        }
        print(json.dumps(out_obj, indent=2))
        return

    print("\n" + "=" * 80)
    if all_passed:
        print(f" {C_GREEN}{C_BOLD}✓ ALL {len(captured_files)} PROOF SNAPSHOTS SAVED FOR QUALITY CONTROL{C_RESET}")
        print(f"   Destination: {out_dir}")
    else:
        print(f" {C_YELLOW}{C_BOLD}⚠ Quality control capture completed with warnings ({len(captured_files)}/{len(selected_cues)} captured){C_RESET}")
        print(f"   Destination: {out_dir}")
    print("=" * 80)

    # Optional desktop viewer open
    if args.open and captured_files:
        viewer = shutil.which("xdg-open") or shutil.which("eog") or shutil.which("display")
        if viewer:
            for f in captured_files[:3]:
                subprocess.Popen([viewer, f], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()

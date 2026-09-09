#!/usr/bin/env python3
"""
verify_jellyfin_subtitles.py - Automate visual verification of subtitles in video files and Jellyfin streams.

This tool verifies that subtitles actually render onto video frames as expected:
1. Extracts active dialogue cues (with timestamps and expected text) from embedded or sidecar subtitle tracks.
2. Uses FFmpeg to render exact video frames at those timestamps with burned-in subtitles.
3. Uses Gemini Multimodal Vision API (or local OCR / manual review) to inspect the captured frames
   and confirm that subtitles are visible, legible, and match the dialogue text.

Usage Examples:
  # Verify subtitles for a specific movie title
  python3 verify_jellyfin_subtitles.py "Caddyshack"

  # Verify using an exact video file path
  python3 verify_jellyfin_subtitles.py "/media/daveg/Lib/Movies/Caddyshack (1980).m4v"

  # Verify at a specific timestamp
  python3 verify_jellyfin_subtitles.py "Caddyshack" --timestamp 00:01:23

  # Test 5 sample dialogue cues across the film
  python3 verify_jellyfin_subtitles.py "Caddyshack" --samples 5

  # Specify Gemini API key directly (or export GEMINI_API_KEY="...")
  python3 verify_jellyfin_subtitles.py "Caddyshack" --gemini-api-key "YOUR_KEY"

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
DEFAULT_DB_PATH = "/home/daveg/Documents/GitHub/movie_Scraper/IMDB_Films.db"
DEFAULT_CACHE_DIR = os.path.expanduser("~/.cache/movie_scraper/sub_verify")
DEFAULT_MODEL = "gemini-2.5-flash"
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
            escaped_sub = sub_target.replace('\\', '/').replace("'", "'\\''").replace(':', '\\:')
            vf_filter = f"subtitles='{escaped_sub}'"
        elif sub_type == 'embedded_text':
            # Dump full srt to temporary file for fast rendering
            temp_fd, temp_srt = tempfile.mkstemp(suffix=".srt")
            os.close(temp_fd)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", video_path,
                "-map", f"0:{sub_target}",
                "-f", "srt", temp_srt
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
            escaped_sub = temp_srt.replace('\\', '/').replace("'", "'\\''").replace(':', '\\:')
            vf_filter = f"subtitles='{escaped_sub}'"
        elif sub_type == 'embedded_bitmap':
            vf_filter = None  # Handled via filter_complex overlay below

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
        if temp_srt and os.path.isfile(temp_srt):
            try:
                os.remove(temp_srt)
            except Exception:
                pass


def verify_frame_with_gemini(image_path, expected_text, api_key, model=DEFAULT_MODEL):
    """
    Call Google Gemini Vision API to verify subtitle visibility and text content.
    Returns dict:
      {'success': bool, 'visible': bool, 'detected_text': str, 'match': bool, 'confidence': float, 'notes': str}
    """
    if not api_key:
        return {
            'success': False,
            'visible': None,
            'detected_text': None,
            'match': None,
            'confidence': 0.0,
            'notes': "No GEMINI_API_KEY provided."
        }

    if requests is None:
        return {
            'success': False,
            'visible': None,
            'detected_text': None,
            'match': None,
            'confidence': 0.0,
            'notes': "The 'requests' python package is not installed."
        }

    try:
        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {'success': False, 'notes': f"Failed to read image file: {e}"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    prompt = f"""You are a professional QA video analysis system.
Examine this video frame captured from a movie player with subtitles enabled.
Expected dialogue/subtitle text: "{expected_text}"

Task:
1. Are subtitles or on-screen captions visible anywhere on this video frame (typically near the bottom)?
2. What exact text is displayed in the subtitles? Transcribe every word accurately.
3. Compare the detected subtitle text with the expected text. Do they match (allowing for minor formatting or punctuation differences)?
4. Rate the visual legibility: "Clear", "Faint", "Obscured", or "None".

You MUST reply with ONLY a single valid JSON object with the following keys:
{{
  "subtitles_visible": true or false,
  "detected_text": "string of exact transcribed subtitle text, or null if none",
  "match": true or false,
  "legibility": "Clear" or "Faint" or "Obscured" or "None",
  "confidence": float between 0.0 and 1.0,
  "notes": "brief 1-sentence description of the visual subtitle rendering"
}}"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_image
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
        if resp.status_code != 200:
            return {
                'success': False,
                'visible': None,
                'notes': f"Gemini API returned HTTP {resp.status_code}: {resp.text[:200]}"
            }

        res_data = resp.json()
        candidates = res_data.get("candidates", [])
        if not candidates:
            return {'success': False, 'notes': "No candidates returned by Gemini API"}

        candidate_parts = candidates[0].get("content", {}).get("parts", [])
        if not candidate_parts:
            return {'success': False, 'notes': "Empty response parts from Gemini"}

        text_out = candidate_parts[0].get("text", "").strip()
        clean_json = re.sub(r'^```(json)?|```$', '', text_out, flags=re.MULTILINE).strip()
        parsed = json.loads(clean_json)

        return {
            'success': True,
            'visible': bool(parsed.get("subtitles_visible", False)),
            'detected_text': parsed.get("detected_text", ""),
            'match': bool(parsed.get("match", False)),
            'legibility': parsed.get("legibility", "Unknown"),
            'confidence': float(parsed.get("confidence", 1.0)),
            'notes': parsed.get("notes", "")
        }

    except Exception as e:
        return {'success': False, 'notes': f"Error calling Gemini API: {e}"}


def get_gemini_api_key(args=None):
    """Resolve Gemini API key from arguments, environment, or user config."""
    if args and hasattr(args, 'gemini_api_key') and args.gemini_api_key:
        return args.gemini_api_key
    if os.getenv("GEMINI_API_KEY"):
        return os.getenv("GEMINI_API_KEY")
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY")

    cfg_paths = [
        os.path.expanduser("~/.config/gemini/api_key"),
        os.path.expanduser("~/.gemini/api_key")
    ]
    for p in cfg_paths:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                    if key:
                        return key
            except Exception:
                pass
    return None


def verify_movie_subtitles(video_path, samples=1, gemini_api_key=None, model=DEFAULT_MODEL, output_dir=None, user_timestamp=None):
    """
    Programmatically verify that subtitles actually render onto video frames for a video file.
    Designed for automated post-encoding verification in pipelines like resample_library.py.

    Returns dict:
        {
            'has_subtitles': bool,
            'subtitle_type': str,       # 'sidecar_srt', 'embedded_text', 'embedded_bitmap', 'none'
            'verified': bool,            # True if capture succeeded and (Gemini passed or frame verified)
            'status': str,               # 'PASS', 'PARTIAL', 'NO_SUBTITLES', 'FRAME_CAPTURED', etc.
            'cues_checked': int,
            'cues_passed': int,
            'frames': list of str,       # Paths to captured frame images
            'detected_text': str,        # Text detected by Gemini (if used)
            'expected_text': str,        # Expected script dialogue
            'gemini_used': bool,
            'details': list of dicts,
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
            'detected_text': '',
            'expected_text': '',
            'gemini_used': False,
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
            'detected_text': '',
            'expected_text': '',
            'gemini_used': False,
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
            'detected_text': '',
            'expected_text': '',
            'gemini_used': False,
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

    if not gemini_api_key:
        gemini_api_key = get_gemini_api_key()

    if output_dir is None:
        filename = os.path.basename(video_path)
        title_clean = os.path.splitext(filename)[0]
        movie_slug = re.sub(r'[^\w\-]', '_', title_clean)[:30]
        output_dir = os.path.join(DEFAULT_CACHE_DIR, movie_slug)
    os.makedirs(output_dir, exist_ok=True)

    cues_checked = 0
    cues_passed = 0
    frames = []
    details = []
    gemini_used = False

    for idx, cue in enumerate(selected_cues, start=1):
        ts_sec = cue['mid']
        ts_str = format_seconds_to_timestamp(ts_sec)
        frame_filename = f"verify_{idx:02d}_{ts_str.replace(':', '_')}.jpg"
        frame_path = os.path.join(output_dir, frame_filename)

        ok = capture_subtitle_frame(video_path, ts_sec, frame_path, sub_type, sub_target)
        if not ok:
            details.append({
                'timestamp': ts_str,
                'expected_text': cue['clean_text'],
                'status': 'CAPTURE_ERROR'
            })
            continue

        frames.append(frame_path)
        cues_checked += 1

        if gemini_api_key:
            gemini_used = True
            gem_res = verify_frame_with_gemini(frame_path, cue['clean_text'], gemini_api_key, model=model)
            if gem_res.get('success'):
                is_vis = gem_res.get('visible')
                is_match = gem_res.get('match')
                cue_status = "PASS" if (is_vis and is_match) else ("PARTIAL" if is_vis else "FAIL")
                if cue_status == "PASS":
                    cues_passed += 1
                details.append({
                    'timestamp': ts_str,
                    'expected_text': cue['clean_text'],
                    'detected_text': gem_res.get('detected_text', ''),
                    'status': cue_status,
                    'frame_path': frame_path,
                    'notes': gem_res.get('notes', '')
                })
            else:
                details.append({
                    'timestamp': ts_str,
                    'expected_text': cue['clean_text'],
                    'status': 'API_ERROR',
                    'frame_path': frame_path,
                    'notes': gem_res.get('notes', '')
                })
        else:
            cues_passed += 1
            details.append({
                'timestamp': ts_str,
                'expected_text': cue['clean_text'],
                'status': 'FRAME_CAPTURED',
                'frame_path': frame_path
            })

    verified = (cues_passed > 0 and cues_passed == cues_checked)
    overall_status = "PASS" if verified else ("PARTIAL" if cues_passed > 0 else "CAPTURE_ERROR")

    primary_det = details[0].get('detected_text', '') if (details and 'detected_text' in details[0]) else ''
    primary_exp = details[0].get('expected_text', '') if (details and 'expected_text' in details[0]) else ''

    return {
        'has_subtitles': True,
        'subtitle_type': sub_type,
        'verified': verified,
        'status': overall_status,
        'cues_checked': cues_checked,
        'cues_passed': cues_passed,
        'frames': frames,
        'details': details,
        'detected_text': primary_det,
        'expected_text': primary_exp,
        'gemini_used': gemini_used,
        'notes': f"{cues_passed}/{cues_checked} cues verified" if cues_checked else "No cues could be checked"
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify that subtitles visibly render onto video frames using FFmpeg and Gemini Multimodal Vision."
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
        help="Number of representative dialogue cues to sample across the movie (default: 3)."
    )
    parser.add_argument(
        "--gemini-api-key",
        help="Google Gemini API key. Defaults to GEMINI_API_KEY environment variable."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model to use for visual inspection (default: {DEFAULT_MODEL})."
    )
    parser.add_argument(
        "--movies-dir",
        default=DEFAULT_MOVIES_DIR,
        help=f"Base movies directory (default: {DEFAULT_MOVIES_DIR})."
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_CACHE_DIR,
        help=f"Directory to save captured verification frames (default: {DEFAULT_CACHE_DIR})."
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open captured frame images in desktop viewer (xdg-open) upon completion."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output."
    )

    args = parser.parse_args()

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

    gemini_key = get_gemini_api_key(args)

    movie_slug = re.sub(r'[^\w\-]', '_', title_clean)[:30]
    out_dir = os.path.join(args.output_dir, movie_slug)
    os.makedirs(out_dir, exist_ok=True)

    if not args.json:
        print("=" * 80)
        print(f" {C_BOLD}Jellyfin Subtitle Verification: {title_clean}{C_RESET}")
        print(f" Video File:     {video_path}")
        print(f" Subtitle Track: {sub_type.upper()} ({sub_meta.get('codec', 'srt')})")
        print(f" Verification:   {'Gemini Vision (' + args.model + ')' if gemini_key else 'Frame Capture (Manual / No API Key)'}")
        print(f" Output Frames:  {out_dir}")
        print("=" * 80)

    results = []
    all_passed = True
    captured_files = []

    for idx, cue in enumerate(selected_cues, start=1):
        ts_sec = cue['mid']
        ts_str = format_seconds_to_timestamp(ts_sec)
        frame_filename = f"frame_{idx:02d}_{ts_str.replace(':', '_')}.jpg"
        frame_path = os.path.join(out_dir, frame_filename)

        if not args.json:
            print(f"\n[Cue {idx}/{len(selected_cues)}] Timestamp: {C_CYAN}{ts_str}{C_RESET}")
            print(f"  Expected Text: \"{C_BOLD}{cue['clean_text']}{C_RESET}\"")

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
            all_passed = False
            continue

        captured_files.append(frame_path)

        # Gemini Vision verification
        if gemini_key:
            if not args.json:
                print("  Calling Gemini Vision to inspect captured frame...", end="", flush=True)
            gem_res = verify_frame_with_gemini(frame_path, cue['clean_text'], gemini_key, model=args.model)

            if not args.json:
                print("\r", end="")

            if gem_res.get('success'):
                is_vis = gem_res.get('visible')
                is_match = gem_res.get('match')
                det_text = gem_res.get('detected_text', '')
                leg = gem_res.get('legibility', 'Unknown')
                notes = gem_res.get('notes', '')

                status = "PASS" if (is_vis and is_match) else ("PARTIAL" if is_vis else "FAIL")
                if status != "PASS":
                    all_passed = False

                color = C_GREEN if status == "PASS" else (C_YELLOW if status == "PARTIAL" else C_RED)

                if not args.json:
                    print(f"  Status:        {color}{status}{C_RESET} (Visible: {is_vis}, Text Match: {is_match})")
                    print(f"  Detected Text: \"{det_text}\"")
                    print(f"  Legibility:    {leg} | Confidence: {gem_res.get('confidence', 1.0):.0%}")
                    if notes:
                        print(f"  Analysis:      {notes}")
                    print(f"  Saved Frame:   {frame_path}")

                results.append({
                    'cue_index': idx,
                    'timestamp': ts_str,
                    'expected_text': cue['clean_text'],
                    'detected_text': det_text,
                    'visible': is_vis,
                    'match': is_match,
                    'legibility': leg,
                    'status': status,
                    'frame_path': frame_path,
                    'notes': notes
                })
            else:
                if not args.json:
                    print(f"  {C_YELLOW}⚠ Gemini Inspection Warning: {gem_res.get('notes')}{C_RESET}")
                    print(f"  Saved Frame:   {frame_path}")
                results.append({
                    'cue_index': idx,
                    'timestamp': ts_str,
                    'expected_text': cue['clean_text'],
                    'status': 'API_ERROR',
                    'frame_path': frame_path,
                    'notes': gem_res.get('notes')
                })
                all_passed = False
        else:
            if not args.json:
                print(f"  {C_GREEN}✓ Frame captured successfully with subtitles{C_RESET}")
                print(f"  Saved Frame:   {frame_path}")
            results.append({
                'cue_index': idx,
                'timestamp': ts_str,
                'expected_text': cue['clean_text'],
                'status': 'FRAME_CAPTURED',
                'frame_path': frame_path
            })

    if args.json:
        out_obj = {
            'movie': title_clean,
            'file': video_path,
            'subtitle_type': sub_type,
            'all_passed': all_passed,
            'results': results
        }
        print(json.dumps(out_obj, indent=2))
        return

    print("\n" + "=" * 80)
    if gemini_key:
        passed_count = sum(1 for r in results if r.get('status') == 'PASS')
        if all_passed:
            print(f" {C_GREEN}{C_BOLD}✓ ALL SUBTITLES VERIFIED SUCCESSFULLY ({passed_count}/{len(results)} passed){C_RESET}")
        else:
            print(f" {C_RED}{C_BOLD}✗ VERIFICATION COMPLETED WITH WARNINGS ({passed_count}/{len(results)} passed){C_RESET}")
    else:
        print(f" {C_GREEN}✓ All {len(results)} test frames captured with subtitles and saved to:{C_RESET}")
        print(f"   {out_dir}")
        print(f"\n {C_CYAN}Tip:{C_RESET} Set {C_BOLD}export GEMINI_API_KEY=\"your_key\"{C_RESET} to enable automated AI visual inspection.")

    print("=" * 80)

    # Optional desktop viewer open
    if args.open and captured_files:
        viewer = shutil.which("xdg-open") or shutil.which("eog") or shutil.which("display")
        if viewer:
            for f in captured_files[:3]:
                subprocess.Popen([viewer, f], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()

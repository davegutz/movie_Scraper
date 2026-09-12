#!/usr/bin/env python3
"""
resample_library.py

Crawls the video library (default: /media/daveg/Lib/Movies) and resamples
oversized video files using optimal H.264 (libx264) settings.

Key Features:
  - Universal Compatibility: Encodes with H.264 (High Profile, Level 4.1, yuv420p)
    which natively Direct-Plays on virtually all devices, including older TVs
    (e.g. 2011 Sony Bravia), web browsers, tablets, and Jellyfin/Plex clients.
  - Visually Lossless Compression: Uses Constant Rate Factor (CRF 20) to shrink
    bloated video streams while preserving pristine visual quality at native resolution.
  - Multi-track Audio Copy: Copies original audio streams (AAC, AC3 5.1, DTS) without
    re-encoding (-c:a copy), avoiding audio quality degradation.
  - Streaming Optimization: Adds -movflags +faststart to place the MOOV atom at the
    head of the file for instantaneous playback start over networks.
  - Direct In-Place Replacement with Automatic Backup: Encodes to an isolated temporary file
    and atomically replaces the original file only upon successful encoding verification.
    A backup of the original video file (<filename>.bak) is saved by default.
    Pass --no-backup to disable backups.
  - Subtitle Download for Bitmapped / Missing Subtitles: By default, queries and downloads
    external English .srt subtitles (.en.srt) for videos that have bitmapped DVD subtitles
    or are missing English subtitles using fetch_subtitles.py, ensuring Jellyfin/Roku/web
    clients have text subtitles and won't lose subtitles upon H.264 re-encoding.
    Pass --no-download-srt or --skip-srt to disable.
  - Automatic Subtitle Verification: By default, verifies that subtitles actually
    render onto video frames after re-encoding using verify_jellyfin_subtitles.py.
    Extracts dialogue cues, renders frames with burned-in subtitles, and (if GEMINI_API_KEY
    is set) runs AI multimodal visual QA to ensure captions are visible and legible.
    Pass --no-verify-subtitles or --skip-sub-verify to disable.
  - Cache Synchronization: Automatically updates the ffprobe cache in
    ~/.cache/movie_scraper/video_res_cache.json so check_database_health.py stays current.

Usage Examples:
    # Dry-run: preview oversized files, subtitle status, and estimated space savings
    python3 resample_library.py --dry-run

    # Process only the first oversized movie as a test (backup enabled by default)
    python3 resample_library.py --max-files 1

    # Process only 5 movies, starting with the largest files
    python3 resample_library.py --max-files 5 --sort-by size_desc

    # Process a single specific movie file
    python3 resample_library.py --file "/media/daveg/Lib/Movies/West Side Story (1961).m4v"

    # Disable automatic backup
    python3 resample_library.py --no-backup

    # Disable automatic subtitle download
    python3 resample_library.py --no-download-srt

    # Use higher compression (CRF 22) or faster encoding preset
    python3 resample_library.py --crf 22 --preset fast
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import signal
import subprocess
import sys
import time

DEFAULT_MOVIES_DIR = "/media/daveg/Lib/Movies"
DEFAULT_DB_PATH = "/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db"
DEFAULT_VIDEO_EXTS = {
    ".m4v", ".mp4", ".mkv", ".avi", ".mov", ".wmv",
    ".flv", ".webm", ".ts", ".mpg", ".mpeg"
}

CACHE_DIR = os.path.expanduser("~/.cache/movie_scraper")
CACHE_FILE = os.path.join(CACHE_DIR, "video_res_cache.json")

# Import fetch_subtitles module for automatic subtitle downloads
try:
    import fetch_subtitles
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import fetch_subtitles
    except ImportError:
        fetch_subtitles = None

# Import verify_jellyfin_subtitles module for automatic post-encode subtitle verification
try:
    import verify_jellyfin_subtitles
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import verify_jellyfin_subtitles
    except ImportError:
        verify_jellyfin_subtitles = None


def load_cache():
    if os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def check_srt_file(file_path):
    """
    Quickly check whether an external subtitle .srt file exists on disk for a video file.
    Returns: 'YES' if an external .srt file exists, 'NO' if not, '-' if no video file.
    """
    if not file_path or not os.path.isfile(file_path):
        return '-'
    base, _ = os.path.splitext(file_path)
    srt_exts = (
        '.srt', '.en.srt', '.eng.srt', '.English.srt', '.english.srt',
        '.forced.srt', '.en.forced.srt', '.default.srt', '.en.default.srt',
        '.SRT', '.EN.SRT', '.ENG.SRT'
    )
    if any(os.path.isfile(base + ext) for ext in srt_exts):
        return 'YES'
    try:
        parent_dir = os.path.dirname(file_path)
        base_name = os.path.basename(base).lower()
        for entry in os.listdir(parent_dir):
            entry_lower = entry.lower()
            if entry_lower.endswith('.srt'):
                stem = entry_lower[:-4]
                if stem == base_name or stem.startswith(base_name + '.'):
                    return 'YES'
    except Exception:
        pass
    return 'NO'


def check_subtitles_info(file_path):
    """
    Check subtitle type and Jellyfin playback compatibility for a video:
    1. Check for external subtitle files (.srt, .en.srt, .eng.srt, .vtt, etc.)
    2. Check embedded subtitle streams using ffprobe.
    Returns:
        (sub_type, jf_status, raw_sub, raw_bmp, raw_srt):
          sub_type: 'SRT', 'Text', 'Bitmap', 'None', or '-'
          jf_status: 'DIRECT', 'TRANSCODE', or '-'
          raw_sub, raw_bmp, raw_srt: backward-compatible ('YES' / 'NO')
    """
    if not file_path or not os.path.isfile(file_path):
        return ('-', '-', '-', '-', '-')

    base, _ = os.path.splitext(file_path)
    raw_srt = check_srt_file(file_path)
    has_text = (raw_srt == 'YES') or any(os.path.isfile(base + ext) for ext in ('.vtt', '.en.vtt', '.sub'))
    has_bmp = False
    has_eng = (raw_srt == 'YES')

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "s",
            "-show_entries", "stream=codec_name,nb_frames:stream_tags=language,title",
            "-of", "csv=p=0",
            "-analyzeduration", "500000",
            "-probesize", "500000",
            file_path
        ]
        out = subprocess.check_output(cmd, timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore").strip()
        if out:
            lines = [line.strip() for line in out.splitlines() if line.strip()]
            valid_streams = []
            for line in lines:
                parts = [p.strip().lower() for p in line.split(',') if p.strip()]
                if not parts:
                    continue
                codec = parts[0]
                nb_frames_str = parts[1] if len(parts) >= 2 else None
                # Skip dummy / empty subtitle tracks (e.g. mov_text placeholder with <= 5 frames)
                if nb_frames_str and nb_frames_str.isdigit() and int(nb_frames_str) <= 5:
                    continue
                valid_streams.append((codec, parts[2:] if len(parts) >= 2 else []))

            for codec, tags in valid_streams:
                is_eng_stream = False
                for p in tags:
                    if p in ('eng', 'en', 'english', 'en-us', 'en-gb', 'en-ca') or 'english' in p or 'eng' in p:
                        is_eng_stream = True
                        break
                if not tags or (tags and tags[0] in ('und', '')):
                    is_eng_stream = True

                if is_eng_stream:
                    has_eng = True
                    if codec in ('mov_text', 'subrip', 'text', 'ass', 'ssa', 'webvtt'):
                        has_text = True
                    elif codec in ('dvd_subtitle', 'hdmv_pgs_subtitle', 'dvdsub'):
                        has_bmp = True

            if not has_eng and len(valid_streams) == 1:
                has_eng = True
                single_codec = valid_streams[0][0]
                if single_codec in ('mov_text', 'subrip', 'text', 'ass', 'ssa', 'webvtt'):
                    has_text = True
                elif single_codec in ('dvd_subtitle', 'hdmv_pgs_subtitle', 'dvdsub'):
                    has_bmp = True
    except Exception:
        pass

    raw_sub = 'YES' if has_eng else 'NO'
    raw_bmp = 'YES' if (has_bmp and not has_text and raw_srt != 'YES') else 'NO'

    if raw_srt == 'YES':
        sub_type = 'SRT'
        jf_status = 'DIRECT'
    elif has_text and has_eng:
        sub_type = 'Text'
        jf_status = 'DIRECT'
    elif has_bmp:
        sub_type = 'Bitmap'
        jf_status = 'TRANSCODE'
    elif has_eng:
        sub_type = 'Text'
        jf_status = 'DIRECT'
    else:
        sub_type = 'None'
        jf_status = '-'

    return (sub_type, jf_status, raw_sub, raw_bmp, raw_srt)


def update_cache_entry(cache, file_path):
    """Probe the new file and update the cache entry."""
    try:
        st = os.stat(file_path)
        cache_key = f"{file_path}|{st.st_mtime}|{st.st_size}"
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,height,r_frame_rate:format=duration",
            "-of", "csv=p=0",
            "-analyzeduration", "1000000",
            "-probesize", "1000000",
            file_path
        ]
        out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        codec_str, res_str, fps_str, time_str = "H264", "-", "-", "-"
        for line in lines:
            parts = line.split(',')
            if len(parts) >= 3:
                c = parts[0].upper()
                codec_str = 'H264' if c in ('AVC', 'AVC1') else c
                res_str = f"{parts[1]}p" if parts[1].isdigit() else "-"
                if parts[2] != '-':
                    try:
                        if '/' in parts[2]:
                            n, d = parts[2].split('/')
                            fps_val = float(n) / float(d)
                        else:
                            fps_val = float(parts[2])
                        fps_str = f"{int(round(fps_val))}" if abs(fps_val - round(fps_val)) < 0.01 else f"{fps_val:.2f}"
                    except Exception:
                        pass
            elif len(parts) == 1:
                try:
                    s = float(parts[0])
                    m = round(s / 60)
                    if m > 0:
                        h, rem_m = divmod(m, 60)
                        time_str = f"{h:02d}:{rem_m:02d}"
                except Exception:
                    pass

        sub_type, jf_status, raw_sub, raw_bmp, raw_srt = check_subtitles_info(file_path)
        cache[cache_key] = {
            'format': codec_str,
            'res': res_str,
            'fps': fps_str,
            'time': time_str,
            'sub': sub_type,
            'jellyfin': jf_status,
            'raw_sub': raw_sub,
            'bmp': raw_bmp,
            'srt': raw_srt
        }
        save_cache(cache)
    except Exception:
        pass


def parse_duration_minutes(val):
    """Parse duration into minutes from 'HH:MM', 'H:MM', numeric seconds, or numeric minutes."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str == '-':
        return None
    try:
        if ':' in val_str:
            parts = val_str.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 60 + int(parts[1]) + (float(parts[2]) / 60.0)
        num = float(val_str)
        if num > 1000:
            return num / 60.0
        elif num > 0:
            return num
    except Exception:
        pass
    return None


def is_oversized(res_str, size_gb, duration=None):
    """Check if file exceeds target bitrate/size threshold, scaled by duration."""
    if not isinstance(size_gb, (int, float)):
        return False
    height = None
    if res_str and res_str.endswith('p') and res_str[:-1].isdigit():
        height = int(res_str[:-1])

    if height is None:
        base_thresh = 4.0
    elif height <= 540:
        base_thresh = 2.5
    elif height <= 720:
        base_thresh = 3.5
    elif height <= 1080:
        base_thresh = 6.0
    else:
        base_thresh = 15.0

    dur_m = parse_duration_minutes(duration)
    if dur_m and dur_m > 0:
        scale = max(dur_m / 120.0, 0.5)
        thresh = base_thresh * scale
    else:
        thresh = base_thresh

    return size_gb > thresh


def format_duration_hr_min(seconds):
    """Convert duration in seconds to 'hr:min' format with leading zero for hours (e.g. 5400 -> '01:30')."""
    try:
        if seconds is not None:
            s = float(seconds)
            if s > 0:
                total_m = round(s / 60)
                h, rem_m = divmod(total_m, 60)
                return f"{h:02d}:{rem_m:02d}"
    except Exception:
        pass
    return '-'


def parse_time_str_to_sec(t_str):
    """Convert 'HH:MM:SS.micro' or 'HH:MM:SS' string into float seconds."""
    try:
        if t_str and t_str != 'N/A':
            parts = t_str.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except Exception:
        pass
    return None


def get_file_duration_hr_min(file_path, cache=None):
    """Retrieve duration in 'hr:min' (e.g. '2:31') using cache or ffprobe."""
    if not file_path or not os.path.isfile(file_path):
        return '-'
    try:
        st = os.stat(file_path)
        cache_key = f"{file_path}|{st.st_mtime}|{st.st_size}"
        if cache is not None and cache_key in cache:
            cached = cache[cache_key]
            if isinstance(cached, dict) and cached.get('time', '-') != '-':
                t = str(cached['time']).strip()
                if ':' in t:
                    parts = t.split(':')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                    return t
                m = re.search(r'\d+', t)
                if m:
                    h, rem = divmod(int(m.group(0)), 60)
                    return f"{h:02d}:{rem:02d}"

        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            file_path
        ]
        dur_out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        time_str = format_duration_hr_min(dur_out)
        if time_str != '-':
            if cache is not None:
                if cache_key not in cache or not isinstance(cache[cache_key], dict):
                    cache[cache_key] = {}
                cache[cache_key]['time'] = time_str
                save_cache(cache)
            return time_str
    except Exception:
        pass
    return '-'


def probe_file_meta(file_path, cache):
    """
    Retrieve metadata (codec, resolution, fps, duration, sub, bmp, srt) from cache or ffprobe.
    Returns:
        (codec_str, res_str, fps_str, time_str, sub_str, bmp_str, srt_str)
    """
    try:
        st = os.stat(file_path)
        cache_key = f"{file_path}|{st.st_mtime}|{st.st_size}"
        if cache_key in cache:
            cached = cache[cache_key]
            if isinstance(cached, dict) and 'res' in cached and 'format' in cached:
                cached_time = cached.get('time', '-')
                if cached_time != '-':
                    if ':' in str(cached_time):
                        parts = str(cached_time).split(':')
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            cached_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                    else:
                        m = re.search(r'\d+', str(cached_time))
                        if m:
                            h, rem = divmod(int(m.group(0)), 60)
                            cached_time = f"{h:02d}:{rem:02d}"
                if 'jellyfin' in cached and cached.get('sub') in ('SRT', 'Text', 'Bitmap', 'None', '-'):
                    sub_val = cached['sub']
                    jf_val = cached['jellyfin']
                    bmp_val = cached.get('bmp', 'NO')
                    srt_val = cached.get('srt', 'NO')
                else:
                    srt_flag = cached.get('srt')
                    bmp_flag = cached.get('bmp')
                    sub_flag = cached.get('sub')
                    if srt_flag == 'YES':
                        sub_val = 'SRT'
                        jf_val = 'DIRECT'
                    elif bmp_flag == 'YES':
                        sub_val = 'Bitmap'
                        jf_val = 'TRANSCODE'
                    elif sub_flag == 'YES':
                        sub_val = 'Text'
                        jf_val = 'DIRECT'
                    elif sub_flag in ('NO', 'None'):
                        sub_val = 'None'
                        jf_val = '-'
                    else:
                        sub_val, jf_val, r_sub, bmp_flag, srt_flag = check_subtitles_info(file_path)
                        cached['raw_sub'] = r_sub
                        cached['bmp'] = bmp_flag
                        cached['srt'] = srt_flag
                    bmp_val = bmp_flag or 'NO'
                    srt_val = srt_flag or 'NO'
                    cached['sub'] = sub_val
                    cached['jellyfin'] = jf_val

                if sub_val != 'SRT' and check_srt_file(file_path) == 'YES':
                    sub_val = cached['sub'] = 'SRT'
                    jf_val = cached['jellyfin'] = 'DIRECT'
                    srt_val = cached['srt'] = 'YES'
                    bmp_val = cached['bmp'] = 'NO'

                return cached.get('format', '-'), cached.get('res', '-'), cached.get('fps', '-'), cached_time, sub_val, jf_val, bmp_val, srt_val

        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,height,r_frame_rate:format=duration",
            "-of", "csv=p=0",
            "-analyzeduration", "1000000",
            "-probesize", "1000000",
            file_path
        ]
        out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        lines_out = [line.strip() for line in out.splitlines() if line.strip()]
        codec_str, res_str, fps_str, time_str = "-", "-", "-", "-"
        for line in lines_out:
            parts = line.split(',')
            if len(parts) >= 3:
                c = parts[0].upper()
                codec_str = 'H264' if c in ('AVC', 'AVC1') else c
                res_str = f"{parts[1]}p" if (len(parts) >= 2 and parts[1].isdigit()) else "-"
                fps_str = parts[2] if len(parts) >= 3 else "-"
            elif len(parts) == 1:
                time_str = format_duration_hr_min(parts[0])
        sub_type, jf_status, r_sub, r_bmp, r_srt = check_subtitles_info(file_path)
        cache[cache_key] = {
            'format': codec_str,
            'res': res_str,
            'fps': fps_str,
            'time': time_str,
            'sub': sub_type,
            'jellyfin': jf_status,
            'raw_sub': r_sub,
            'bmp': r_bmp,
            'srt': r_srt
        }
        save_cache(cache)
        return codec_str, res_str, fps_str, time_str, sub_type, jf_status, r_bmp, r_srt
    except Exception:
        return "-", "-", "-", "-", "-", "-", "-", "-"


def download_srt_if_needed(file_info, imdb_mapping=None, db_path=DEFAULT_DB_PATH, dry_run=False, force=False):
    """
    If video has bitmapped subtitles or is missing subtitles entirely,
    query and fetch external English .srt subtitle file.
    Returns: (status, message)
      status: 'downloaded', 'already_exists', 'dry_run', 'failed', or 'not_needed'
    """
    file_path = file_info['path']
    bmp_val = file_info.get('bmp', '-')
    sub_val = file_info.get('sub', '-')
    srt_val = file_info.get('srt', '-')

    # Double-check if subtitle status was not determined
    if bmp_val == '-' or sub_val == '-' or srt_val == '-':
        s, b, sr = check_subtitles_info(file_path)
        if sub_val == '-':
            sub_val = file_info['sub'] = s
        if bmp_val == '-':
            bmp_val = file_info['bmp'] = b
        if srt_val == '-':
            srt_val = file_info['srt'] = sr

    # Check if external .srt already exists on disk
    if check_srt_file(file_path) == 'YES' and not force:
        file_info['srt'] = 'YES'
        file_info['sub'] = 'YES'
        return 'already_exists', "External .srt subtitle already exists on disk."

    # Subtitle is needed if video has bitmap-only subtitles (BMP=YES / Sub=Bitmap)
    # OR if video has NO English subtitles at all (Sub=NO / Sub=None)
    needs_sub = (
        bmp_val == 'YES'
        or sub_val in ('NO', 'None', 'Bitmap')
        or file_info.get('jellyfin') == 'TRANSCODE'
    )
    if not needs_sub:
        return 'not_needed', None

    if fetch_subtitles is None:
        return 'failed', "fetch_subtitles module not available."

    if imdb_mapping is None:
        imdb_mapping = fetch_subtitles.get_imdb_mapping(db_path)

    reason = "bitmapped subtitles (BMP=YES)" if bmp_val == 'YES' else "no subtitles (Sub=NO)"
    print(f"    Subtitle: Video has {reason}. Fetching English .srt...")
    success = fetch_subtitles.process_single_movie(file_path, imdb_mapping, dry_run=dry_run, force=force)
    if success:
        file_info['srt'] = 'YES'
        file_info['bmp'] = 'NO'
        file_info['sub'] = 'YES'
        return ('dry_run' if dry_run else 'downloaded'), "Saved external .en.srt subtitle."
    else:
        return 'failed', "Could not find matching English subtitles online."


# Backward compatibility alias
download_srt_for_bitmap = download_srt_if_needed


def sanitize_srt_utf8(srt_path):
    """Ensures an external .srt file is encoded in valid UTF-8 without BOM so FFmpeg can parse it."""
    if not srt_path or not os.path.isfile(srt_path) or os.path.getsize(srt_path) == 0:
        return False
    try:
        with open(srt_path, 'rb') as f:
            raw = f.read()

        encoding = None
        if raw.startswith(bytes([255, 254, 0, 0])) or raw.startswith(bytes([0, 0, 254, 255])):
            encoding = 'utf-32'
        elif raw.startswith(bytes([255, 254])) or raw.startswith(bytes([254, 255])) or (len(raw) >= 4 and raw[1] == 0 and raw[3] == 0):
            encoding = 'utf-16'
        elif raw.startswith(bytes([239, 187, 191])):
            encoding = 'utf-8-sig'
        else:
            try:
                raw.decode('utf-8')
                return True
            except UnicodeDecodeError:
                encoding = 'cp1252'

        decoded = raw.decode(encoding, errors='replace')
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(decoded)
        return True
    except Exception:
        return False


def get_subtitle_args(file_path, ext):
    """
    Determine subtitle handling for ffmpeg.
    - For MKV: MKV supports virtually all subtitle formats (dvd_subtitle, pgssub, srt, etc.),
      so stream-copying all subtitles works cleanly: ['-map', '0:s?', '-c:s', 'copy']
    - For MP4/M4V/MOV: These containers only support text subtitles ('mov_text').
      Attempting to map bitmap subtitles (such as dvd_subtitle or pgssub) with '-c:s mov_text'
      fails with "Subtitle encoding currently only possible from text to text or bitmap to bitmap"
      because FFmpeg cannot perform OCR on image-based subtitles.
      Therefore, we only map text subtitle streams individually to 'mov_text', and skip bitmap subtitles.
      Corrupted or non-decodable subtitle tracks are verified and skipped.
    """
    if ext.lower() not in ('.mp4', '.m4v', '.mov'):
        return ["-map", "0:s?", "-c:s", "copy"]

    mapped_args = []
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "s",
            "-show_entries", "stream=index,codec_name,nb_frames",
            "-of", "csv=p=0",
            file_path
        ]
        out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        text_codecs = {'mov_text', 'subrip', 'text', 'srt', 'webvtt', 'ass', 'ssa'}
        for line in out.splitlines():
            parts = line.strip().split(',')
            if len(parts) >= 2:
                idx, codec = parts[0], parts[1].lower()
                nb_frames_str = parts[2] if len(parts) >= 3 else None
                # Skip dummy / empty placeholder subtitle tracks
                if nb_frames_str and nb_frames_str.isdigit() and int(nb_frames_str) <= 5:
                    continue
                if codec in text_codecs:
                    # Verify subtitle stream does not error during decoding
                    is_valid = False
                    try:
                        verify_cmd = [
                            "ffmpeg", "-v", "error", "-i", file_path,
                            "-map", f"0:{idx}", "-c:s", "mov_text", "-f", "null", "-"
                        ]
                        vret = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=30)
                        if vret.returncode == 0 and 'Error decoding subtitles' not in vret.stderr and 'invalid UTF-8' not in vret.stderr:
                            is_valid = True
                    except subprocess.TimeoutExpired:
                        # Large file took longer than 30s to demux/scan to the end, but didn't error out
                        is_valid = True
                    except Exception:
                        pass

                    if is_valid:
                        mapped_args.extend(["-map", f"0:{idx}"])
        if mapped_args:
            mapped_args.extend(["-c:s", "mov_text"])
    except Exception:
        pass
    return mapped_args


def get_audio_args(file_path, ext):
    """
    Inspect audio streams, remove corrupt or redundant duplicate stereo tracks,
    and return clean ffmpeg audio arguments.
    """
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index,codec_name,channels",
            "-of", "csv=p=0",
            file_path
        ]
        out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        if not out:
            return ["-map", "0:a?", "-c:a", "copy"]

        audio_streams = []
        for line in out.splitlines():
            parts = line.strip().split(',')
            if len(parts) >= 2:
                idx = parts[0].strip()
                codec = parts[1].strip().lower()
                channels = int(parts[2].strip()) if len(parts) >= 3 and parts[2].strip().isdigit() else 2
                audio_streams.append({'index': idx, 'codec': codec, 'channels': channels})

        if not audio_streams:
            return ["-map", "0:a?", "-c:a", "copy"]

        is_mp4 = ext.lower() in ('.mp4', '.m4v', '.mov')
        if is_mp4:
            incompatible_codecs = ('dts', 'truehd', 'mlp', 'flac')
            has_compatible_audio = any(s['codec'] not in incompatible_codecs for s in audio_streams)
            if has_compatible_audio:
                # Discard streams that crash MP4/M4V container muxers (e.g. DTS with incompatible tags)
                audio_streams = [s for s in audio_streams if s['codec'] not in incompatible_codecs]
            if len(audio_streams) > 1:
                has_stereo_aac = any(s['codec'] == 'aac' and s['channels'] <= 2 for s in audio_streams)
                if has_stereo_aac:
                    # Filter out redundant 2-channel AC3 tracks when 2-channel AAC already exists
                    filtered = [s for s in audio_streams if not (s['codec'] in ('ac3', 'eac3') and s['channels'] <= 2)]
                    if filtered:
                        audio_streams = filtered

        args = []
        needs_transcode = False
        for s in audio_streams:
            args.extend(["-map", f"0:{s['index']}"])
            if is_mp4 and s['codec'] in ('dts', 'truehd', 'mlp', 'flac'):
                needs_transcode = True

        if needs_transcode:
            args.extend(["-c:a", "aac", "-b:a", "384k"])
        else:
            args.extend(["-c:a", "copy"])
        return args
    except Exception:
        return ["-map", "0:a?", "-c:a", "copy"]


def format_time(seconds):
    """Format seconds into human-readable MMm SSs."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"


def get_fps_args(file_path):
    """
    Detect frame rate anomalies (such as container timescale inflating r_frame_rate to 120 fps).
    Returns ffmpeg arguments to normalize frame rate and prevent duplicate frame explosion.
    """
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,avg_frame_rate",
            "-of", "csv=p=0",
            file_path
        ]
        out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        if not out:
            return ["-fps_mode", "passthrough"]
        parts = out.split(',')
        r_str = parts[0].strip() if len(parts) >= 1 else ""
        avg_str = parts[1].strip() if len(parts) >= 2 else ""

        def parse_rate(s):
            if not s or s == '0/0' or s == '-':
                return None
            if '/' in s:
                num, den = s.split('/')
                return float(num) / float(den) if float(den) != 0 else None
            return float(s)

        r_fps = parse_rate(r_str)
        avg_fps = parse_rate(avg_str)

        if r_fps and r_fps > 60:
            cand = avg_fps if (avg_fps and 0 < avg_fps <= 60) else 23.976
            if abs(cand - 23.976) < 0.1 or abs(cand - 24.0) < 0.1:
                target_fps = "24000/1001"
            elif abs(cand - 29.97) < 0.1 or abs(cand - 30.0) < 0.1:
                target_fps = "30000/1001"
            elif abs(cand - 25.0) < 0.1:
                target_fps = "25"
            elif abs(cand - 50.0) < 0.1:
                target_fps = "50"
            elif abs(cand - 59.94) < 0.1 or abs(cand - 60.0) < 0.1:
                target_fps = "60000/1001"
            else:
                target_fps = f"{cand:.3f}"
            return ["-r", target_fps]
        else:
            return ["-fps_mode", "passthrough"]
    except Exception:
        return ["-fps_mode", "passthrough"]


def build_ffmpeg_cmd(input_path, output_path, crf=20, preset='medium', safe_fallback=False):
    """Construct robust ffmpeg command line."""
    _, ext = os.path.splitext(input_path)

    if safe_fallback:
        sub_args = get_subtitle_args(input_path, ext)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-progress", "pipe:1",
            "-y",
            "-fflags", "+genpts+discardcorrupt",
            "-err_detect", "ignore_err",
            "-i", input_path,
            "-map", "0:v:0",
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-map", "0:a:0?",
            "-c:a", "copy"
        ]
        if sub_args:
            cmd.extend(sub_args)
        if ext.lower() in ('.mp4', '.m4v', '.mov'):
            cmd.extend(["-movflags", "+faststart"])
        cmd.append(output_path)
        return cmd

    sub_args = get_subtitle_args(input_path, ext)

    # Check for external sidecar subtitle (.en.srt or .srt) if no text subtitles embedded
    sidecar_srt = None
    if not sub_args:
        base_no_ext, _ = os.path.splitext(input_path)
        if base_no_ext.endswith(('.m4v', '.mp4', '.mkv', '.avi')):
            base_no_ext, _ = os.path.splitext(base_no_ext)
        for cand in [f"{base_no_ext}.en.srt", f"{base_no_ext}.srt", f"{base_no_ext}.en.default.srt"]:
            if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                sanitize_srt_utf8(cand)
                sidecar_srt = cand
                break

    audio_args = get_audio_args(input_path, ext)
    fps_args = get_fps_args(input_path)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-progress", "pipe:1",
        "-y",
        "-fflags", "+genpts+discardcorrupt",
        "-err_detect", "ignore_err",
        "-i", input_path,
    ]
    if sidecar_srt:
        cmd.extend(["-i", sidecar_srt])
    cmd.extend([
        "-map", "0:v:0",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p"
    ])
    cmd.extend(fps_args)
    cmd.extend(audio_args)
    if sub_args:
        cmd.extend(sub_args)
    elif sidecar_srt:
        sub_codec = "mov_text" if ext.lower() in ('.mp4', '.m4v', '.mov') else "srt"
        cmd.extend([
            "-map", "1:0",
            "-c:s", sub_codec,
            "-metadata:s:s:0", "language=eng"
        ])
    if ext.lower() in ('.mp4', '.m4v', '.mov'):
        cmd.extend(["-movflags", "+faststart"])
    cmd.append(output_path)
    return cmd


def run_ffmpeg_with_progress(cmd, total_duration_sec=None, throttle_sec=0.5):
    """
    Execute an FFmpeg command with progress reported via stdout (-progress pipe:1).
    Overwrites a single status line in-place using carriage returns (\r) with flush=True
    and space padding, avoiding thousands of scrolling lines while running in PyCharm's
    standard console without terminal emulation.
    Returns:
        (retcode, stderr_output)
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    cur_stats = {}
    last_print = 0.0
    has_printed = False

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
                    is_end = (cur_stats.get('progress') == 'end')
                    if (now - last_print >= throttle_sec) or is_end:
                        out_time_raw = cur_stats.get('out_time', '')
                        if out_time_raw and out_time_raw != 'N/A':
                            out_time_display = out_time_raw.split('.')[0]
                            fps = cur_stats.get('fps', '0')
                            speed = cur_stats.get('speed', '0x')
                            dur_sec = parse_time_str_to_sec(out_time_raw)
                            pct_str = ""
                            total_str = ""
                            if total_duration_sec and total_duration_sec > 0 and dur_sec is not None:
                                pct = min(100.0, (dur_sec / total_duration_sec) * 100.0)
                                pct_str = f" ({pct:4.1f}%)"
                                tot_h = int(total_duration_sec // 3600)
                                tot_m = int((total_duration_sec % 3600) // 60)
                                tot_s = int(total_duration_sec % 60)
                                total_str = f" / {tot_h:02d}:{tot_m:02d}:{tot_s:02d}"

                            msg = f"    [FFmpeg] time={out_time_display}{total_str}{pct_str} | fps={fps} | speed={speed}"
                            sys.stdout.write("\r" + f"{msg:<85}")
                            sys.stdout.flush()
                            has_printed = True
                            last_print = now

        _, stderr_text = proc.communicate()
        if has_printed:
            sys.stdout.write("\n")
            sys.stdout.flush()
        return proc.returncode, (stderr_text or '')
    except KeyboardInterrupt:
        if has_printed:
            sys.stdout.write("\n")
            sys.stdout.flush()
        proc.kill()
        proc.wait()
        raise


def resample_single_file(file_info, crf=20, preset='medium', cache=None, backup=True):
    """
    Encode a single file to a temporary file, verify integrity,
    and atomically replace the original file.
    Returns:
        dict with success status, old_bytes, new_bytes, elapsed time.
    """
    src_path = file_info['path']
    src_dir = os.path.dirname(src_path)
    src_base, src_ext = os.path.splitext(os.path.basename(src_path))
    temp_path = os.path.join(src_dir, f".{src_base}.resampled_tmp{src_ext}")

    cmd = build_ffmpeg_cmd(src_path, temp_path, crf=crf, preset=preset)

    t_start = time.time()
    try:
        dur_m = parse_duration_minutes(file_info.get('time'))
        total_dur_sec = (dur_m * 60) if (dur_m and dur_m > 0) else None

        ret, err_text = run_ffmpeg_with_progress(cmd, total_duration_sec=total_dur_sec)

        if ret != 0:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

            # Fallback transcode: retry with safe primary stream settings
            print(f"    [!] Initial encode exited with code {ret}. Retrying with safe fallback...")
            fallback_cmd = build_ffmpeg_cmd(src_path, temp_path, crf=crf, preset=preset, safe_fallback=True)
            ret_fallback, err_fallback = run_ffmpeg_with_progress(fallback_cmd, total_duration_sec=total_dur_sec)
            if ret_fallback != 0:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                err_summary = (err_fallback.strip() or err_text.strip())
                return {'success': False, 'error': f"FFmpeg exited with error code {ret} (fallback also failed with {ret_fallback}): {err_summary}"}
            print("    [+] Fallback encode succeeded!")

        # Verify output file
        if not os.path.exists(temp_path):
            return {'success': False, 'error': "Output temp file not found"}

        new_bytes = os.path.getsize(temp_path)
        old_bytes = file_info['size_bytes']

        # Ensure output is reasonable (> 5 MB)
        if new_bytes < 5 * 1024 * 1024:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return {'success': False, 'error': f"Output file too small ({new_bytes} bytes), aborting"}

        # Replacement of original file (with optional backup)
        backup_path = None
        if backup:
            backup_path = f"{src_path}.bak"
            try:
                os.replace(src_path, backup_path)
                try:
                    os.utime(backup_path, None)
                except Exception:
                    pass
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return {'success': False, 'error': f"Failed to create backup file: {e}"}

            try:
                os.replace(temp_path, src_path)
            except Exception as e:
                if os.path.exists(backup_path) and not os.path.exists(src_path):
                    os.replace(backup_path, src_path)
                return {'success': False, 'error': f"Failed to replace original with resampled file: {e}"}
        else:
            os.replace(temp_path, src_path)

        elapsed = time.time() - t_start

        # Subtitle safety net: if resampled file lost text subtitles, auto-rescue from backup into .en.srt
        if backup_path and os.path.isfile(backup_path):
            try:
                base_no_ext, _ = os.path.splitext(src_path)
                has_sidecar = any(os.path.isfile(f"{base_no_ext}{e}") for e in ('.en.srt', '.srt', '.eng.srt'))
                if not has_sidecar:
                    res_sub_args = get_subtitle_args(src_path, src_ext)
                    if not res_sub_args:
                        bak_sub_args = get_subtitle_args(backup_path, src_ext)
                        if bak_sub_args:
                            for idx_a, arg in enumerate(bak_sub_args):
                                if arg == "-map" and idx_a + 1 < len(bak_sub_args):
                                    st_map = bak_sub_args[idx_a + 1]
                                    out_srt = f"{base_no_ext}.en.srt"
                                    ext_cmd = ["ffmpeg", "-y", "-i", backup_path, "-map", st_map, "-c:s", "srt", out_srt]
                                    subprocess.run(ext_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                                    if os.path.isfile(out_srt) and os.path.getsize(out_srt) > 50:
                                        sanitize_srt_utf8(out_srt)
                                        print(f"    Subtitles: [✓] Auto-rescued text subtitle from backup to {os.path.basename(out_srt)}")
                                        break
            except Exception:
                pass

        # Update cache
        if cache is not None:
            update_cache_entry(cache, src_path)

        return {
            'success': True,
            'old_bytes': old_bytes,
            'new_bytes': new_bytes,
            'saved_bytes': old_bytes - new_bytes,
            'elapsed': elapsed,
            'backup_path': backup_path
        }

    except KeyboardInterrupt:
        if proc and proc.poll() is None:
            proc.kill()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return {'success': False, 'error': str(e)}


def prune_backups(movies_dir, max_backups=50):
    """
    Ensure the movies directory holds no more than `max_backups` .bak files.
    Older .bak files are deleted completely (oldest by mtime/ctime first).
    Returns list of dicts with details of pruned backup files.
    """
    if not movies_dir or not os.path.isdir(movies_dir) or max_backups is None or max_backups < 0:
        return []

    bak_files = []
    for root, _, files in os.walk(movies_dir):
        for f in files:
            if f.endswith('.bak'):
                full_p = os.path.join(root, f)
                try:
                    st = os.stat(full_p)
                    ts = max(st.st_mtime, st.st_ctime)
                    bak_files.append({
                        'path': full_p,
                        'filename': f,
                        'timestamp': ts,
                        'size_bytes': st.st_size,
                        'size_gb': st.st_size / (1024 ** 3)
                    })
                except Exception:
                    pass

    bak_files.sort(key=lambda x: x['timestamp'])

    to_prune_count = len(bak_files) - max_backups
    pruned = []
    if to_prune_count > 0:
        for item in bak_files[:to_prune_count]:
            try:
                os.remove(item['path'])
                pruned.append(item)
            except Exception as e:
                print(f"    [!] Failed to delete old backup {item['filename']}: {e}", file=sys.stderr)

    return pruned


def prompt_caffeine_check(movie_count):
    """
    Prompt user with a blocking Tkinter dialog asking 'Have you turned on caffeine?'
    for batch runs of more than 5 movies.
    """
    if movie_count <= 5:
        return True

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        confirmed = messagebox.askokcancel(
            title="Caffeine Check",
            message=f"Batch run: {movie_count} movies queued for resampling.\n\nHave you turned on caffeine and turned off suspend_until (sudo crontab -e)?",
            icon=messagebox.QUESTION
        )
        root.destroy()
        return confirmed
    except Exception:
        print(f"\n[!] Notice: Batch run of {movie_count} movies queued for resampling.")
        try:
            resp = input("Have you turned on caffeine and turned off suspend_until (sudo crontab -e)? (Press Enter/Y for OK, N to cancel): ").strip().lower()
            return resp not in ('n', 'no', 'cancel')
        except (EOFError, KeyboardInterrupt):
            return False


def scan_candidates(movies_dir, extensions, cache, oversized_only=True, min_size_gb=0.0):
    """Scan directory and filter for candidate files."""
    candidates = []
    if not os.path.isdir(movies_dir):
        return candidates

    raw_files = []
    for root, _, files in os.walk(movies_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in extensions:
                p = os.path.join(root, f)
                try:
                    sz = os.path.getsize(p)
                    raw_files.append((p, f, ext, sz))
                except Exception:
                    pass

    for path, filename, ext, sz_bytes in raw_files:
        sz_gb = round(sz_bytes / (1024 ** 3), 2)
        if sz_gb < min_size_gb:
            continue

        fmt, res, fps, time_str, sub_str, jf_str, bmp_str, srt_str = probe_file_meta(path, cache)
        oversized = is_oversized(res, sz_gb, time_str)

        if oversized_only and not oversized:
            continue

        candidates.append({
            'path': path,
            'filename': filename,
            'ext': ext,
            'size_bytes': sz_bytes,
            'size_gb': sz_gb,
            'format': fmt,
            'resolution': res,
            'fps': fps,
            'time': time_str,
            'sub': sub_str,
            'jellyfin': jf_str,
            'bmp': bmp_str,
            'srt': srt_str,
            'oversized': oversized
        })

    return candidates


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
        description="Resample oversized movie files in the Lib folder using optimal H.264 (libx264) settings."
    )
    parser.add_argument(
        "--movies-dir",
        default=DEFAULT_MOVIES_DIR,
        help=f"Directory to scan (default: {DEFAULT_MOVIES_DIR})"
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Process a single specific movie file instead of scanning directory."
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="Constant Rate Factor: 18-23 recommended (default: 20, visually lossless)."
    )
    parser.add_argument(
        "--preset",
        choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'veryslow'],
        default='medium',
        help="x264 encoding preset (default: medium)."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all video files, not just oversized ones."
    )
    parser.add_argument(
        "--min-size-gb",
        type=float,
        default=0.0,
        help="Minimum file size in GB to consider (default: 0.0)."
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Maximum number of files to process before exiting (e.g. 1 or 5 for testing)."
    )
    parser.add_argument(
        "--sort-by",
        choices=['size_desc', 'size_asc', 'name'],
        default='size_desc',
        help="Order to process files: size_desc (largest first, default), size_asc, or name."
    )
    parser.add_argument(
        "--backup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep a backup of the original video file (<filename>.bak) before replacing (default: True)."
    )
    parser.add_argument(
        "--backup-original",
        dest="backup",
        action="store_true",
        help="Alias for --backup: keep a backup of the original video file."
    )
    parser.add_argument(
        "--no-backup-original",
        dest="backup",
        action="store_false",
        help="Alias for --no-backup: do not keep a backup of the original video file."
    )
    parser.add_argument(
        "--download-srt",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download external English .srt subtitles for videos with bitmapped subtitles or missing subtitles (default: True)."
    )
    parser.add_argument(
        "--skip-srt", "--no-srt",
        dest="download_srt",
        action="store_false",
        help="Alias for --no-download-srt: skip downloading .srt subtitles."
    )
    parser.add_argument(
        "--force-srt",
        action="store_true",
        default=False,
        help="Overwrite existing .srt subtitle files when downloading (default: False)."
    )
    parser.add_argument(
        "--verify-subtitles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Visually verify that subtitles render onto video frames after re-encoding (default: True)."
    )
    parser.add_argument(
        "--skip-sub-verify", "--no-sub-verify",
        dest="verify_subtitles",
        action="store_false",
        help="Alias for --no-verify-subtitles: skip visual subtitle verification."
    )
    parser.add_argument(
        "--sub-samples",
        type=int,
        default=1,
        help="Number of dialogue cue frames to verify per movie (default: 1 for fast verification)."
    )
    parser.add_argument(
        "--gemini-api-key",
        help="Google Gemini API key for automated AI visual inspection (defaults to GEMINI_API_KEY environment variable)."
    )
    parser.add_argument(
        "--max-backups",
        type=int,
        default=50,
        help="Maximum number of .bak backup files to retain across the library (default: 50). Older backups are deleted completely."
    )
    parser.add_argument(
        "--caffeine-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prompt with a blocking Tkinter window asking 'Have you turned on caffeine?' for batch runs of > 5 movies (default: True)."
    )
    parser.add_argument(
        "--skip-caffeine-check",
        dest="caffeine_check",
        action="store_false",
        help="Skip the caffeine reminder prompt."
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Path to IMDB_Films.db database for subtitle lookup (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview candidate files and estimated savings without modifying any files."
    )

    args = parser.parse_args(argv)

    cache = load_cache()

    # Case 1: Single file specified
    if args.file:
        if not os.path.isfile(args.file):
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        sz = os.path.getsize(args.file)
        fmt, res, fps, time_str, sub_str, jf_str, bmp_str, srt_str = probe_file_meta(args.file, cache)
        if not time_str or time_str == '-':
            time_str = get_file_duration_hr_min(args.file, cache)
        sz_gb = round(sz / (1024 ** 3), 2)
        oversized = is_oversized(res, sz_gb, time_str)

        file_info = {
            'path': args.file,
            'filename': os.path.basename(args.file),
            'ext': os.path.splitext(args.file)[1].lower(),
            'size_bytes': sz,
            'size_gb': sz_gb,
            'format': fmt,
            'resolution': res,
            'fps': fps,
            'time': time_str,
            'sub': sub_str,
            'jellyfin': jf_str,
            'bmp': bmp_str,
            'srt': srt_str,
            'oversized': oversized
        }

        if not args.all and not oversized:
            print(f"File '{os.path.basename(args.file)}' is already within optimal bounds ({sz_gb} GB, {res}, Sized: YES).")
            print("Skipping re-encoding. (Pass --all to re-encode anyway.)")
            # If subtitle download is enabled, check and download subtitles even if re-encoding was skipped
            if args.download_srt and ((bmp_str == 'YES' or sub_str in ('NO', 'None', 'Bitmap') or jf_str == 'TRANSCODE') and srt_str != 'YES'):
                sub_status, sub_msg = download_srt_if_needed(
                    file_info,
                    db_path=args.db,
                    dry_run=args.dry_run,
                    force=args.force_srt
                )
                if sub_status in ('downloaded', 'already_exists'):
                    print(f"    Subtitle: {sub_msg}")
                elif sub_status == 'failed':
                    print(f"    Subtitle: [-] {sub_msg}")

            # Also perform subtitle verification if requested
            if args.verify_subtitles and verify_jellyfin_subtitles is not None:
                sub_res = verify_jellyfin_subtitles.verify_movie_subtitles(
                    args.file,
                    samples=args.sub_samples,
                    gemini_api_key=args.gemini_api_key
                )
                if sub_res.get('verified'):
                    if sub_res.get('gemini_used'):
                        det_sample = sub_res.get('detected_text') or sub_res.get('expected_text')
                        print(f'    Subtitles: [✓] VERIFIED with Gemini Vision ("{det_sample}")')
                    else:
                        cue_info = f" at {sub_res['details'][0]['timestamp']}" if sub_res.get('details') else ""
                        print(f"    Subtitles: [✓] Verified dialogue cue{cue_info} & frame captured")
                elif sub_res.get('has_subtitles'):
                    print(f"    Subtitles: [!] Warning: {sub_res.get('notes', 'Failed verification')}")
                else:
                    print("    Subtitles: [-] No subtitle track found to verify")

            sys.exit(0)

        candidates = [file_info]
    else:
        if not os.path.isdir(args.movies_dir):
            print(f"Error: Movies directory not found: {args.movies_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"Scanning {args.movies_dir} for video files...")
        candidates = scan_candidates(
            args.movies_dir,
            DEFAULT_VIDEO_EXTS,
            cache,
            oversized_only=(not args.all),
            min_size_gb=args.min_size_gb
        )
        save_cache(cache)

    if not candidates:
        print("No eligible candidate video files found.")
        sys.exit(0)

    # Sort candidates
    if args.sort_by == 'size_desc':
        candidates.sort(key=lambda c: c['size_bytes'], reverse=True)
    elif args.sort_by == 'size_asc':
        candidates.sort(key=lambda c: c['size_bytes'])
    else:
        candidates.sort(key=lambda c: c['filename'].lower())

    if args.max_files and args.max_files > 0:
        candidates = candidates[:args.max_files]

    total_candidate_bytes = sum(c['size_bytes'] for c in candidates)
    total_candidate_gb = total_candidate_bytes / (1024 ** 3)

    print("=" * 90)
    print("  Video Library Resampling Tool (H.264 CRF 20 Direct Replacement)")
    print("=" * 90)
    print(f"  Target Candidates:        {len(candidates):,} files ({total_candidate_gb:,.2f} GB)")
    print(f"  Encoding Configuration:   libx264, CRF {args.crf}, preset '{args.preset}', yuv420p")
    print(f"  Audio Configuration:      -c:a copy (lossless stream copy)")
    print(f"  Streaming Flag:           -movflags +faststart")
    bak_str = f"Enabled (.bak, max {args.max_backups})" if (args.backup and args.max_backups > 0) else ("Enabled (.bak, unlimited)" if args.backup else "Disabled (--no-backup)")
    print(f"  Backup Original:          {bak_str}")
    print(f"  Download SRT Subtitles:   {'Enabled (default)' if args.download_srt else 'Disabled'}")
    print(f"  Verify Subtitles:         {'Enabled (default)' if args.verify_subtitles else 'Disabled'}")
    print(f"  Estimated Space Savings:  ~75% to 85% (~{total_candidate_gb * 0.78:,.2f} GB)")
    print("=" * 90)

    # Dry-run output
    if args.dry_run:
        print("\n[DRY RUN] The following files would be resampled (no files modified):\n")
        print(f"  {'Size (GB)':>9} {'Res':<6} {'Format':<6} {'Time':<7} {'Sub':<8} {'Jellyfin':<11} {'Filename'}")
        print(f"  {'-'*9:>9} {'-'*6:<6} {'-'*6:<6} {'-'*7:<7} {'-'*6:<8} {'-'*8:<11} {'-'*44}")
        for c in candidates[:50]:
            print(f"  {c['size_gb']:>9.2f} {c['resolution']:<6} {c['format']:<6} {c.get('time', '-'):<7} {c.get('sub', '-'):<8} {c.get('jellyfin', '-'):<11} {c['filename']}")
        if len(candidates) > 50:
            print(f"  ... and {len(candidates) - 50} more files.")

        if args.backup and args.max_backups > 0:
            existing_baks = [os.path.join(r, f) for r, _, fs in os.walk(args.movies_dir) for f in fs if f.endswith('.bak')]
            excess = max(0, len(existing_baks) - args.max_backups)
            if excess > 0:
                print(f"\n  Backup Retention:         {len(existing_baks)} existing .bak files ({excess} oldest would be pruned to maintain <= {args.max_backups} limit).")
            else:
                print(f"\n  Backup Retention:         {len(existing_baks)} existing .bak files (within <= {args.max_backups} limit).")

        need_srt = [c for c in candidates if (c.get('bmp') == 'YES' or c.get('sub') in ('NO', 'None', 'Bitmap') or c.get('jellyfin') == 'TRANSCODE') and c.get('srt') != 'YES']
        if args.download_srt:
            if need_srt:
                print(f"\n  Subtitle Download (Default): {len(need_srt)} candidate(s) need .srt subtitles (BMP=YES or Sub=NO).")
                print(f"  External English .en.srt subtitles will be downloaded for them automatically prior to resampling.")
            else:
                print(f"\n  Subtitle Download: No candidates need .srt downloads.")
        else:
            print(f"\n  Subtitle Download: Disabled (--no-download-srt specified).")

        if len(candidates) == 1 and need_srt and args.download_srt and fetch_subtitles is not None:
            print(f"\n  [DRY RUN] Testing subtitle lookup for '{candidates[0]['filename']}':")
            test_mapping = fetch_subtitles.get_imdb_mapping(args.db)
            fetch_subtitles.process_single_movie(candidates[0]['path'], test_mapping, dry_run=True, force=args.force_srt)

        if len(candidates) == 1 and args.verify_subtitles and verify_jellyfin_subtitles is not None:
            print(f"\n  [DRY RUN] Subtitle verification test for '{candidates[0]['filename']}':")
            test_ver = verify_jellyfin_subtitles.verify_movie_subtitles(
                candidates[0]['path'],
                samples=1,
                gemini_api_key=args.gemini_api_key
            )
            if test_ver.get('has_subtitles'):
                cue_txt = f" (cue: \"{test_ver['expected_text']}\")" if test_ver.get('expected_text') else ""
                status_txt = "PASSED" if test_ver.get('verified') else "READY"
                print(f"    Track detected: {test_ver['subtitle_type']}{cue_txt} -> verification {status_txt}")
            else:
                print("    No subtitle track found for candidate.")

        print(f"\nExample FFmpeg command for first file:")
        ex_cmd = build_ffmpeg_cmd(candidates[0]['path'], "/path/to/temp_output.mp4", args.crf, args.preset)
        print(f"  {' '.join(ex_cmd)}\n")
        sys.exit(0)

    # Caffeine check reminder for batch runs (> 5 movies)
    if getattr(args, 'caffeine_check', True) and not args.dry_run:
        if not prompt_caffeine_check(len(candidates)):
            print("\nResampling cancelled by user at caffeine check prompt.")
            sys.exit(0)

    # Prune any old backups exceeding max_backups before beginning
    if args.backup and args.max_backups > 0:
        initial_pruned = prune_backups(args.movies_dir, max_backups=args.max_backups)
        if initial_pruned:
            init_gb = sum(p['size_bytes'] for p in initial_pruned) / (1024 ** 3)
            print(f"Pruned {len(initial_pruned)} old .bak backup(s) exceeding {args.max_backups} limit (freed {init_gb:.2f} GB):\n")
            for p in initial_pruned:
                print(f"  [-] Deleted: {p['filename']} ({p['size_gb']:.2f} GB)")
            print()

    # Actual processing loop
    print(f"\nBeginning resampling of {len(candidates):,} files...\n")

    imdb_mapping = None
    if args.download_srt and any((c.get('bmp') == 'YES' or c.get('sub') in ('NO', 'None', 'Bitmap') or c.get('jellyfin') == 'TRANSCODE') for c in candidates):
        if fetch_subtitles is not None:
            imdb_mapping = fetch_subtitles.get_imdb_mapping(args.db)

    total_saved_bytes = 0
    success_count = 0
    fail_count = 0
    failed_movies = []
    overall_start = time.time()

    for i, file_info in enumerate(candidates, 1):
        fp = file_info['path']
        sz_gb = file_info['size_gb']
        res = file_info['resolution']
        fmt = file_info['format']

        time_str = file_info.get('time', '-')
        if not time_str or time_str == '-':
            time_str = get_file_duration_hr_min(file_info['path'], cache)
            file_info['time'] = time_str

        time_tail = f"  Time: {time_str}" if time_str != '-' else "Time: unknown"
        print(f"[{i}/{len(candidates)}] Processing: {fp}{time_tail}")
        print(f"    Current:  {sz_gb:.2f} GB | {res} | {fmt} | {file_info['fps']} fps")

        # Automatically download external .en.srt for videos with bitmapped or missing subtitles by default
        if args.download_srt and (file_info.get('bmp') == 'YES' or file_info.get('sub') in ('NO', 'None', 'Bitmap') or file_info.get('jellyfin') == 'TRANSCODE'):
            sub_status, sub_msg = download_srt_if_needed(
                file_info,
                imdb_mapping=imdb_mapping,
                db_path=args.db,
                dry_run=False,
                force=args.force_srt
            )
            if sub_status == 'already_exists':
                print(f"    Subtitle: {sub_msg}")
            elif sub_status == 'downloaded':
                print(f"    Subtitle: {sub_msg}")
            elif sub_status == 'failed':
                print(f"    Subtitle: [-] {sub_msg} (continuing video resampling)")

        try:
            result = resample_single_file(file_info, crf=args.crf, preset=args.preset, cache=cache, backup=args.backup)
            if result['success']:
                new_gb = result['new_bytes'] / (1024 ** 3)
                saved_gb = result['saved_bytes'] / (1024 ** 3)
                pct = (result['saved_bytes'] / file_info['size_bytes']) * 100
                total_saved_bytes += result['saved_bytes']
                print(f"    Result:   {new_gb:.2f} GB  (Saved: {saved_gb:.2f} GB, {pct:.1f}%) in {format_time(result['elapsed'])}")
                if result.get('backup_path'):
                    print(f"    Backup:   {result['backup_path']}")
                    if args.backup and args.max_backups > 0:
                        pruned_after = prune_backups(args.movies_dir, max_backups=args.max_backups)
                        if pruned_after:
                            for p in pruned_after:
                                print(f"    Backup Pruned: {p['filename']} ({p['size_gb']:.2f} GB, exceeded {args.max_backups} backups limit)")

                # Visual subtitle verification by default
                sub_failed = False
                sub_fail_reason = None
                if args.verify_subtitles and verify_jellyfin_subtitles is not None:
                    try:
                        sub_res = verify_jellyfin_subtitles.verify_movie_subtitles(
                            fp,
                            samples=args.sub_samples,
                            gemini_api_key=args.gemini_api_key
                        )
                        if sub_res.get('verified'):
                            if sub_res.get('gemini_used'):
                                det_sample = sub_res.get('detected_text') or sub_res.get('expected_text')
                                print(f'    Subtitles: [✓] VERIFIED with Gemini Vision ("{det_sample}")')
                            else:
                                cue_info = f" at {sub_res['details'][0]['timestamp']}" if sub_res.get('details') else ""
                                print(f"    Subtitles: [✓] Verified dialogue cue{cue_info} & frame captured")
                        elif sub_res.get('has_subtitles'):
                            has_api_err = any(d.get('status') == 'API_ERROR' for d in sub_res.get('details', []))
                            if has_api_err or 'Error calling Gemini API' in sub_res.get('notes', ''):
                                print(f"    Subtitles: [!] Gemini API warning ({sub_res.get('notes')}); subtitle track confirmed on disk.")
                            else:
                                sub_fail_reason = f"Subtitle vision check failed ({sub_res.get('notes', 'Failed verification')})"
                                print(f"    Subtitles: [✗] {sub_fail_reason}")
                                sub_failed = True
                        else:
                            print("    Subtitles: [-] No subtitle track to verify")
                    except Exception as ex:
                        print(f"    Subtitles: [!] Subtitle verification warning: {ex}")

                if sub_failed:
                    fail_count += 1
                    failed_movies.append({
                        'path': fp,
                        'filename': file_info.get('filename', os.path.basename(fp)),
                        'size_gb': sz_gb,
                        'error': sub_fail_reason
                    })
                    print(f"    FAILED:   {sub_fail_reason} (new resampled file retained)", file=sys.stderr)
                else:
                    success_count += 1
            else:
                fail_count += 1
                err_msg = result.get('error', 'Unknown error')
                failed_movies.append({
                    'path': fp,
                    'filename': file_info.get('filename', os.path.basename(fp)),
                    'size_gb': sz_gb,
                    'error': err_msg
                })
                print(f"    FAILED:   {err_msg}", file=sys.stderr)
        except KeyboardInterrupt:
            print("\n\nOperation interrupted by user (Ctrl+C). Exiting cleanly...", file=sys.stderr)
            break
        print()

    total_saved_gb = total_saved_bytes / (1024 ** 3)
    total_elapsed = time.time() - overall_start

    print("=" * 90)
    print("  Resampling Summary")
    print("=" * 90)
    print(f"  Successfully Resampled:   {success_count:,} files")
    if fail_count > 0:
        print(f"  Failed / Skipped:         {fail_count:,} files")
    print(f"  Total Disk Space Freed:   {total_saved_gb:,.2f} GB")
    print(f"  Total Time Taken:         {format_time(total_elapsed)}")
    print("=" * 90)

    if failed_movies:
        print(f"\n[!] Failed Movies ({len(failed_movies):,}):")
        print(f"  {'Size (GB)':>9}  {'Filename':<45}  {'Reason'}")
        print(f"  {'-'*9:>9}  {'-'*45:<45}  {'-'*25}")
        for fm in failed_movies:
            err_msg = ' '.join(fm['error'].strip().splitlines())
            if len(err_msg) > 60:
                err_msg = err_msg[:57] + "..."
            print(f"  {fm['size_gb']:>9.2f}  {fm['filename']:<45}  {err_msg}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        main("--max-files 10 --sort-by size_desc")

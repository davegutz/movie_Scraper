#!/usr/bin/env python3
"""
check_database_health.py

Compares the contents of IMDB_Films.db (at the DB location pointed to by
GUI_sqlite_scrape.py when running) against video files in the movies library
(default: /media/daveg/Lib/Movies).

Generates:
  1. Matched Titles: Database entries that have a matching video file in the library.
  2. Missing Titles: Database entries that have no matching video file.
  3. Unmatched Titles/Files: Video files in the library that do not match any database entry.

All output lists:
  - Are alphabetized ignoring leading articles ('The', 'A', 'An', 'Le', 'La', 'Il', 'El', etc.),
    moving the article to the end after a comma (e.g. "Godfather, The", "Beautiful Mind, A").
  - Have the release year appended in parentheses to the end of the Title (e.g. "West Side Story (1961)").
  - For unmatched library items, Filename is kept clean without appending extra year information.
  - Include video file extension (e.g. .mp4, .m4v)
  - Include video codec / format (e.g. H264, H265, MPEG4)
  - Include video resolution in 'p' form (e.g. 1080p, 720p, 480p)
  - Include video frame rate in frames per second (FPS, e.g. 23.98, 29.97, 24)
  - Include video file size in decimal GB (e.g. 3.61 GB)
  - Include duration of the title / video in a column called 'Time' in hr:min format (e.g. 02:00)
  - Include subtitle type indicator in a column called 'Sub' (SRT / Text / Bitmap / None / -)
  - Include Jellyfin compatibility indicator in a column called 'Jellyfin' (DIRECT / TRANSCODE / -)
  - Include oversized flag (YES / NO / -) in a column called 'Oversized' based on resolution vs file size
Columns are placed directly before the filename / title column.
Total GB size and oversized totals are included in the summary header at the beginning.

Usage:
    python3 check_database_health.py [options]

Examples:
    python3 check_database_health.py
    python3 check_database_health.py --show-only matched
    python3 check_database_health.py --show-only missing
    python3 check_database_health.py --show-only unmatched
    python3 check_database_health.py --oversized-only
    python3 check_database_health.py --output-matched matched.csv --format csv
    python3 check_database_health.py -o missing.csv --format csv
    python3 check_database_health.py --output-unmatched unmatched.csv --format csv
    python3 check_database_health.py --quiet --show-only matched
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from configparser import ConfigParser
import csv
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import unicodedata

# Prevent BrokenPipeError stack trace when piping output to head/more/less
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    pass

DEFAULT_MOVIES_DIR = "/media/daveg/Lib/Movies"
DEFAULT_VIDEO_EXTS = {
    ".m4v", ".mp4", ".mkv", ".avi", ".mov", ".wmv",
    ".m4vv", ".flv", ".webm", ".vob", ".ts", ".mpg", ".mpeg", ".iso"
}

CACHE_DIR = os.path.expanduser("~/.cache/movie_scraper")
CACHE_FILE = os.path.join(CACHE_DIR, "video_res_cache.json")
_cache_lock = threading.Lock()

ARTICLE_PATTERN = re.compile(r'^(the|a|an|le|la|les|il|lo|gli|el|los|las|der|das)\s+(.*)$', re.IGNORECASE)
L_APOSTROPHE_PATTERN = re.compile(r"^(l\')\s*(.*)$", re.IGNORECASE)


def move_article_to_end(title):
    """
    If title starts with an article ('The', 'A', 'An', 'Le', 'La', 'Il', 'El', etc.),
    move the article to the end after a comma for alphabetical indexing.
    Examples:
        'The Godfather'        -> 'Godfather, The'
        'A Beautiful Mind'     -> 'Beautiful Mind, A'
        'An American in Paris' -> 'American in Paris, An'
        'Le Mans'              -> 'Mans, Le'
        'Il Divo'              -> 'Divo, Il'
        'El Dorado'            -> 'Dorado, El'
        'Les Misérables'       -> 'Misérables, Les'
        "L'Avventura"          -> "Avventura, L'"
    """
    if not title:
        return ''
    s = str(title).strip()
    m = ARTICLE_PATTERN.match(s)
    if m:
        art = m.group(1)
        rest = m.group(2).strip()
        if art.lower() == 'an':
            art_formatted = 'An'
        elif art.lower() == 'a':
            art_formatted = 'A'
        else:
            art_formatted = art.capitalize()
        return f"{rest}, {art_formatted}"
    m_l = L_APOSTROPHE_PATTERN.match(s)
    if m_l:
        rest = m_l.group(2).strip()
        return f"{rest}, L'"
    return s


def load_resolution_cache():
    """Load cached video metadata from disk."""
    if os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_resolution_cache(cache):
    """Save cached video metadata to disk."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def format_codec(raw_codec):
    """Format raw codec name to standardized representation (e.g. H264, H265, MPEG4)."""
    if not raw_codec or raw_codec == '-':
        return '-'
    c = str(raw_codec).lower().strip()
    if c in ('h264', 'avc', 'avc1'):
        return 'H264'
    elif c in ('hevc', 'h265', 'hev1', 'hvc1'):
        return 'H265'
    elif c in ('mpeg4', 'mp4v'):
        return 'MPEG4'
    elif c in ('mpeg2video', 'mpeg2'):
        return 'MPEG2'
    elif c in ('mpeg1video', 'mpeg1'):
        return 'MPEG1'
    elif c == 'vc1':
        return 'VC1'
    elif c in ('wmv3', 'wmv2', 'wmv1'):
        return 'WMV'
    elif c == 'vp9':
        return 'VP9'
    elif c == 'vp8':
        return 'VP8'
    elif c == 'av1':
        return 'AV1'
    return c.upper()


def parse_fps(val_str):
    """Parse fractional or float frame rate string into clean FPS representation."""
    try:
        if not val_str or val_str == '-':
            return '-'
        if '/' in val_str:
            num, den = val_str.split('/')
            num = float(num)
            den = float(den)
            if den == 0:
                return '-'
            val = num / den
        else:
            val = float(val_str)
        if val <= 0 or val > 240:
            return '-'
        if abs(val - round(val)) < 0.01:
            return f"{int(round(val))}"
        return f"{val:.2f}"
    except Exception:
        return '-'


def format_time_minutes(val):
    """Format runtime minutes into standard 'hr:min' representation (e.g. 120 -> '02:00', 96 -> '01:36', or '-')."""
    if val is None:
        return '-'
    val_str = str(val).strip()
    if not val_str or val_str in ('0', '-'):
        return '-'
    try:
        if ':' in val_str:
            parts = val_str.split(':')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            return val_str
        m = re.search(r'\d+', val_str)
        if m:
            num = int(m.group(0))
            if num > 0:
                h, rem_m = divmod(num, 60)
                return f"{h:02d}:{rem_m:02d}"
    except Exception:
        pass
    return '-'


def format_time_seconds(sec):
    """Convert seconds into standard 'hr:min' representation (e.g. 7200 -> '02:00')."""
    try:
        if sec is not None:
            s = float(sec)
            if s > 0:
                total_m = round(s / 60)
                if total_m > 0:
                    h, rem_m = divmod(total_m, 60)
                    return f"{h:02d}:{rem_m:02d}"
    except Exception:
        pass
    return '-'


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


def check_sized(res_str, size_gb, duration=None):
    """
    Determine if a video file is properly sized based on its resolution, file size, and duration.
    Base thresholds for standard ~2-hour (120 min) movies:
      - SD (<=540p): 2.5 GB
      - 720p (541p - 720p): 3.5 GB
      - 1080p (721p - 1080p): 6.0 GB
      - 4K (>1080p): 15.0 GB
      - Unknown resolution: 4.0 GB
    Threshold scales proportionally with runtime: threshold * max(duration_minutes / 120, 0.5).
    Returns:
      'YES' if within optimal bounds (properly sized), 'NO' if oversized (not properly sized), '-' if no video file.
    """
    if not isinstance(size_gb, (int, float)):
        return "-"
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

    return "NO" if size_gb > thresh else "YES"


def check_oversized(res_str, size_gb, duration=None):
    """
    Backward-compatible wrapper: returns 'YES' if oversized, 'NO' if within bounds, '-' if no video file.
    """
    s = check_sized(res_str, size_gb, duration)
    if s == "YES":
        return "NO"
    elif s == "NO":
        return "YES"
    return s
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

    # 1. External subtitle files
    base, _ = os.path.splitext(file_path)
    raw_srt = check_srt_file(file_path)
    has_text = (raw_srt == 'YES') or any(os.path.isfile(base + ext) for ext in ('.vtt', '.en.vtt', '.sub'))
    has_bmp = False
    has_eng = (raw_srt == 'YES')

    # 2. Embedded subtitle streams via ffprobe
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


def get_video_metadata(file_path, cache=None):
    """
    Extract codec/format ('H264', 'H265', etc.), vertical resolution ('{height}p'),
    frame rate ('{fps}'), duration ('{time}'), subtitle type ('{sub}'), and Jellyfin mode ('{jellyfin}') using ffprobe.
    Uses caching keyed by file path, mtime, and size.
    Returns:
        (codec_str, res_str, fps_str, time_str, sub_type, jf_status)
    """
    if not file_path or not os.path.isfile(file_path):
        return ("-", "-", "-", "-", "-", "-")

    try:
        st = os.stat(file_path)
        cache_key = f"{file_path}|{st.st_mtime}|{st.st_size}"
        if cache is not None:
            with _cache_lock:
                if cache_key in cache:
                    cached_val = cache[cache_key]
                    if isinstance(cached_val, dict) and 'res' in cached_val and 'fps' in cached_val and 'format' in cached_val:
                        # Determine sub and jellyfin
                        if 'jellyfin' in cached_val and cached_val.get('sub') in ('SRT', 'Text', 'Bitmap', 'None', '-'):
                            sub_type = cached_val['sub']
                            jf_status = cached_val['jellyfin']
                        else:
                            # Map legacy cache (sub='YES'/'NO', bmp='YES'/'NO', srt='YES'/'NO')
                            srt_flag = cached_val.get('srt')
                            bmp_flag = cached_val.get('bmp')
                            sub_flag = cached_val.get('sub')
                            if srt_flag == 'YES':
                                sub_type = 'SRT'
                                jf_status = 'DIRECT'
                            elif bmp_flag == 'YES':
                                sub_type = 'Bitmap'
                                jf_status = 'TRANSCODE'
                            elif sub_flag == 'YES':
                                sub_type = 'Text'
                                jf_status = 'DIRECT'
                            elif sub_flag in ('NO', 'None'):
                                sub_type = 'None'
                                jf_status = '-'
                            else:
                                sub_type, jf_status, r_sub, r_bmp, r_srt = check_subtitles_info(file_path)
                                cached_val['raw_sub'] = r_sub
                                cached_val['bmp'] = r_bmp
                                cached_val['srt'] = r_srt

                            cached_val['sub'] = sub_type
                            cached_val['jellyfin'] = jf_status

                        # Check if an external .srt has been added to disk since caching
                        if cached_val.get('sub') != 'SRT' and check_srt_file(file_path) == 'YES':
                            cached_val['sub'] = 'SRT'
                            cached_val['jellyfin'] = 'DIRECT'
                            cached_val['srt'] = 'YES'

                        return (
                            cached_val['format'],
                            cached_val['res'],
                            cached_val['fps'],
                            format_time_minutes(cached_val.get('time', '-')),
                            cached_val['sub'],
                            cached_val['jellyfin']
                        )

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
        codec_str, res_str, fps_str, time_str = "-", "-", "-", "-"
        for line in lines:
            parts = line.split(',')
            if len(parts) >= 3:
                codec_str = format_codec(parts[0])
                res_str = f"{parts[1]}p" if parts[1].isdigit() else "-"
                fps_str = parse_fps(parts[2])
            elif len(parts) == 1:
                time_str = format_time_seconds(parts[0])

        sub_type, jf_status, r_sub, r_bmp, r_srt = check_subtitles_info(file_path)
        if cache is not None:
            with _cache_lock:
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
        return (codec_str, res_str, fps_str, time_str, sub_type, jf_status)
    except Exception:
        return ("-", "-", "-", "-", "-", "-")



def get_entry_colors(sub_val, jf_val, sized_val, has_video=True, use_color=True):
    """
    Determine row color and column colors:
      - If no subtitles will be displayed in jellyfin code it red.
      - If improperly sized (Sized=NO) code it orange.
      - If jellyfin is loaded heavily code it yellow.
      - If clean code green.
    """
    if not use_color:
        return ('', '', '', '', '')

    c_red = '[91m'
    c_orange = '[38;5;208m'
    c_yellow = '[93m'
    c_green = '[92m'
    c_reset = '[0m'

    if not has_video:
        return (c_red, c_red, c_red, '', c_reset)

    # Sub column
    if sub_val in ('None', '-'):
        sub_c = c_red
    elif sub_val == 'Bitmap':
        sub_c = c_yellow
    else:
        sub_c = c_green

    # Jellyfin column
    if jf_val == '-':
        jf_c = c_red
    elif jf_val == 'TRANSCODE':
        jf_c = c_yellow
    else:
        jf_c = c_green

    # Sized column (YES = properly sized/green, NO = improperly sized/orange)
    if sized_val == 'NO':
        sized_c = c_orange
    elif sized_val == 'YES':
        sized_c = c_green
    else:
        sized_c = ''

    # Overall row color (priority: No subs (Red) > Improperly sized (Orange) > Transcode (Yellow) > Clean (Green))
    if sub_val in ('None', '-') or jf_val == '-':
        row_c = c_red
    elif sized_val == 'NO':
        row_c = c_orange
    elif jf_val == 'TRANSCODE':
        row_c = c_yellow
    else:
        row_c = c_green

    return (row_c, sub_c, jf_c, sized_c, c_reset)

def batch_probe_metadata(items, path_getter, max_workers=12, verbose=False):
    """
    Batch probe video format/codec, resolution, frame rate, duration, and subtitles using ThreadPoolExecutor and disk cache.
    """
    cache = load_resolution_cache()
    paths = [path_getter(item) for item in items]

    needed = 0
    for p in paths:
        if p and os.path.isfile(p):
            try:
                st = os.stat(p)
                k = f"{p}|{st.st_mtime}|{st.st_size}"
                cached = cache.get(k)
                if not (isinstance(cached, dict) and 'res' in cached and 'fps' in cached and 'format' in cached and 'sub' in cached and 'bmp' in cached):
                    needed += 1
            except Exception:
                pass

    if needed > 20 and verbose:
        print(f"Probing video stream format/metadata for {needed} files...", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        meta_results = list(executor.map(lambda p: get_video_metadata(p, cache), paths))

    save_resolution_cache(cache)
    return meta_results


def get_default_db_path(script_dir=None):
    """
    Determine the path to IMDB_Films.db using the exact same configuration logic
    as GUI_sqlite_scrape.py.
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    # Determine ini config file path per platform
    if sys.platform == 'linux':
        config_file_path = '/home/daveg/.local/GUI_sqlite_scrape_linux.ini'
        if not os.path.isfile(config_file_path):
            config_file_path = os.path.expanduser('~/.local/GUI_sqlite_scrape_linux.ini')
        default_folder = '/home/daveg/Documents/GitHub/myComputer'
    elif sys.platform == 'darwin':
        config_file_path = '/Users/daveg/.local/GUI_sqlite_scrape_macos.ini'
        if not os.path.isfile(config_file_path):
            config_file_path = os.path.expanduser('~/.local/GUI_sqlite_scrape_macos.ini')
        default_folder = (
            '/Users/daveg/Library/CloudStorage/GoogleDrive-davegutz2006@gmail.com/'
            'My Drive/Movies Stuff'
        )
    else:
        local_app_data = os.getenv('LOCALAPPDATA', '')
        config_file_path = os.path.join(local_app_data, 'GUI_sqlite_scrape.ini')
        default_folder = 'G:/My Drive/Movies Stuff'

    db_name = 'IMDB_Films.db'
    db_folder = default_folder

    # Read ini configuration if available
    if os.path.isfile(config_file_path):
        cp = ConfigParser()
        cp.read(config_file_path)
        if 'path' in cp and 'db_folder' in cp['path']:
            db_folder = cp['path']['db_folder']

    db_path = os.path.join(db_folder, db_name)
    if os.path.isfile(db_path):
        return db_path

    # Fallback 1: Local repository directory
    local_db = os.path.join(script_dir, db_name)
    if os.path.isfile(local_db):
        return local_db

    # Fallback 2: Check default folder directly
    fallback_path = os.path.join(default_folder, db_name)
    return fallback_path


def normalize_title(text):
    """
    Normalize movie title for resilient comparison:
    - Pre-replace unicode punctuation (dashes, dots, curly quotes)
    - Unicode NFKD to strip accents/diacritics
    - Lowercase
    - Replace punctuation, symbols, colons, hyphens, and slashes with space
    - Standardize Roman numerals / words in parts (e.g. 'part ii' -> 'part 2')
    - Replace '&' with 'and'
    - Collapse repeated whitespace
    """
    if not text:
        return ''
    text = str(text).replace('·', ' ').replace('–', ' ').replace('—', ' ').replace('\u2019', "'")
    s = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    s = s.lower()
    # Replace punctuation and special characters with spaces
    s = re.sub(r'[\:\/\?\*\"\<\>\|\!\'\,\.\;\(\)\[\]\_\-]', ' ', s)
    s = s.replace('&', ' and ')

    # Standardize parts / numerals
    part_replacements = {
        r'\bpart\s+i\b': 'part 1', r'\bpart\s+one\b': 'part 1',
        r'\bpart\s+ii\b': 'part 2', r'\bpart\s+two\b': 'part 2',
        r'\bpart\s+iii\b': 'part 3', r'\bpart\s+three\b': 'part 3',
        r'\bpart\s+iv\b': 'part 4', r'\bpart\s+four\b': 'part 4',
        r'\bvol\s+1\b': 'volume 1', r'\bvolume\s+i\b': 'volume 1',
        r'\bvol\s+2\b': 'volume 2', r'\bvolume\s+ii\b': 'volume 2',
    }
    for pattern, rep in part_replacements.items():
        s = re.sub(pattern, rep, s)

    s = re.sub(r'\s+', ' ', s).strip()
    return s


def compact_title(text):
    """
    Produce an alphanumeric-only string for fuzzy/spacing matching
    (e.g., 'Pelham 1 2 3' vs 'Pelham 123', 'WALL-E' vs 'WALL·E').
    """
    return re.sub(r'[^a-z0-9]', '', normalize_title(text))


def strip_article(text):
    """Remove leading 'the ', 'a ', or 'an ' from normalized title."""
    return re.sub(r'^(the|a|an)\s+', '', text).strip()


def format_title_with_year(display_title, year):
    """Append release year inside parentheses to title, e.g. 'West Side Story (1961)'."""
    if year is not None and str(year).isdigit():
        return f"{display_title} ({year})"
    return display_title


def scan_video_files(movies_dir, extensions):
    """
    Recursively scan movies_dir for video files and extract title, year,
    extension, file size in decimal GB, and normalized forms for matching.
    """
    pattern_year = re.compile(r'^(.*?)\s*\(\s*(\d{4})\s*\)(.*)$')
    video_entries = []

    if not os.path.isdir(movies_dir):
        return video_entries

    for root, _, files in os.walk(movies_dir):
        rel_dir = os.path.relpath(root, movies_dir)
        for f in sorted(files):
            base, ext = os.path.splitext(f)
            ext_clean = ext.lower()
            if ext_clean in extensions:
                full_path = os.path.join(root, f)
                try:
                    sz_bytes = os.path.getsize(full_path)
                    size_gb = round(sz_bytes / (1024 ** 3), 2)
                except Exception:
                    sz_bytes = 0
                    size_gb = '-'

                m = pattern_year.match(base)
                if m:
                    raw_title = m.group(1).strip()
                    year = int(m.group(2))
                    suffix = m.group(3).strip()
                    full_title = f"{raw_title} {suffix}".strip() if suffix else raw_title
                else:
                    raw_title = base.strip()
                    full_title = base.strip()
                    year = None

                norm_t = normalize_title(raw_title)
                disp_raw = move_article_to_end(raw_title)
                y_suffix = f" ({year})" if year else ""
                disp_filename = f"{disp_raw}{y_suffix}{ext_clean}" if disp_raw != raw_title else f

                video_entries.append({
                    'filename': f,
                    'display_filename': disp_filename,
                    'rel_dir': rel_dir if rel_dir != '.' else '',
                    'path': full_path,
                    'raw_title': raw_title,
                    'display_raw_title': disp_raw,
                    'year': year,
                    'ext': ext_clean,
                    'format': '-',
                    'resolution': '-',
                    'fps': '-',
                    'time': '-',
                    'sub': '-',
                    'jellyfin': '-',
                    'sized': '-',
                    'oversized': '-',
                    'size_bytes': sz_bytes,
                    'size_gb': size_gb,
                    'norm_title': norm_t,
                    'full_norm_title': normalize_title(full_title),
                    'compact_title': compact_title(raw_title),
                    'no_art_title': strip_article(norm_t),
                    'norm_base': normalize_title(base),
                    'compact_base': compact_title(base)
                })

    return video_entries


def load_db_movies(db_path):
    """Query all movies from the My_Films table in IMDB_Films.db."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "SELECT IMDB_ID, title, year, DVD, WATCHED, my_rating, certification, runtime "
        "FROM My_Films ORDER BY title COLLATE NOCASE"
    )
    rows = c.fetchall()
    conn.close()

    movies = []
    for row in rows:
        imdb_id, title, year, dvd, watched, my_rating, cert, runtime = row
        clean_t = title or ''
        norm_t = normalize_title(clean_t)
        disp_t = move_article_to_end(clean_t)
        y_int = int(year) if year and str(year).isdigit() else None
        time_str = format_time_minutes(runtime)
        movies.append({
            'imdb_id': imdb_id,
            'title': clean_t,
            'display_title': disp_t,
            'display_title_year': format_title_with_year(disp_t, y_int),
            'year': y_int,
            'dvd': dvd,
            'watched': watched or '',
            'my_rating': my_rating,
            'certification': cert or '',
            'runtime': runtime,
            'time': time_str,
            'ext': '-',
            'format': '-',
            'resolution': '-',
            'fps': '-',
            'sub': '-',
            'jellyfin': '-',
            'sized': '-',
            'oversized': '-',
            'size_bytes': 0,
            'size_gb': '-',
            'norm_title': norm_t,
            'compact_title': compact_title(clean_t),
            'no_art_title': strip_article(norm_t)
        })
    return movies


def compare_db_and_videos(db_movies, video_entries):
    """
    Perform bidirectional comparison between database movie records and video files.
    Returns:
      (matched_records, missing_db_movies, unmatched_video_entries)
    """
    matched = []
    missing_db_movies = []
    matched_video_paths = set()

    for movie in db_movies:
        norm_t = movie['norm_title']
        comp_t = movie['compact_title']
        no_art = movie['no_art_title']
        db_y = movie['year']

        match = None

        # Tier 1: Exact normalized title (or title+suffix) and exact release year
        if db_y:
            for ve in video_entries:
                if ve['year'] == db_y and (ve['norm_title'] == norm_t or ve['full_norm_title'] == norm_t):
                    match = ve
                    break

        # Tier 2: Exact normalized title and release year +- 1
        if not match and db_y:
            for ve in video_entries:
                if ve['year'] and abs(ve['year'] - db_y) <= 1:
                    if ve['norm_title'] == norm_t or ve['full_norm_title'] == norm_t:
                        match = ve
                        break

        # Tier 3: Compact title (punctuation/spacing variants) and release year +- 1
        if not match and db_y:
            for ve in video_entries:
                if ve['year'] and abs(ve['year'] - db_y) <= 1:
                    if ve['compact_title'] == comp_t or ve['compact_base'] == comp_t:
                        match = ve
                        break

        # Tier 4: Ignore leading article ('The', 'A', 'An') and release year +- 1
        if not match and db_y and no_art:
            for ve in video_entries:
                if ve['year'] and abs(ve['year'] - db_y) <= 1:
                    if ve['no_art_title'] == no_art:
                        match = ve
                        break

        # Tier 5: Exact normalized title without year requirement
        if not match:
            for ve in video_entries:
                if ve['norm_title'] == norm_t or ve['full_norm_title'] == norm_t:
                    match = ve
                    break

        # Tier 6: Match against full base filename
        if not match:
            for ve in video_entries:
                if ve['norm_base'] == norm_t or ve['compact_base'] == comp_t:
                    match = ve
                    break

        if match:
            movie_copy = dict(movie)
            movie_copy['ext'] = match['ext']
            movie_copy['size_bytes'] = match.get('size_bytes', 0)
            movie_copy['size_gb'] = match.get('size_gb', '-')
            # Synchronize time between DB movie record and matched video file
            if movie_copy.get('time', '-') == '-' and match.get('time', '-') != '-':
                movie_copy['time'] = match['time']
            match['time'] = movie_copy.get('time', '-')
            movie_copy['sub'] = match.get('sub', '-')
            movie_copy['jellyfin'] = match.get('jellyfin', '-')
            matched.append((movie_copy, match))
            matched_video_paths.add(match['path'])
        else:
            missing_db_movies.append(movie)

    # Identify library video files not matched to any database entry
    unmatched_video_entries = [
        ve for ve in video_entries if ve['path'] not in matched_video_paths
    ]

    return matched, missing_db_movies, unmatched_video_entries


def format_size_gb(val):
    """Format size_gb as a 2-decimal place string if numeric, else '-'."""
    if isinstance(val, (int, float)):
        return f"{val:.2f}"
    return "-"


def write_matched_file(output_path, matched_records, output_format):
    """Write the matched database movies to the specified file."""
    if output_format == 'csv':
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['IMDB_ID', 'DVD', 'Ext', 'Fmt', 'Resolution', 'FPS', 'Size', 'Time', 'Sub', 'Jellyfin', 'Sized', 'Title', 'Original_Title', 'Watched', 'Rating', 'Certification', 'Filename', 'FullPath'])
            for movie_item, match_item in matched_records:
                writer.writerow([
                    movie_item['imdb_id'],
                    movie_item['dvd'] if movie_item['dvd'] is not None else '',
                    match_item.get('ext', '-'),
                    match_item.get('format', '-'),
                    match_item.get('resolution', '-'),
                    match_item.get('fps', '-'),
                    format_size_gb(match_item.get('size_gb')),
                    movie_item.get('time', '-'),
                    match_item.get('sub', '-'),
                    match_item.get('jellyfin', '-'),
                    match_item.get('sized', '-'),
                    movie_item.get('display_title_year', movie_item['title']),
                    movie_item['title'],
                    movie_item['watched'],
                    movie_item['my_rating'] if movie_item['my_rating'] is not None else '',
                    movie_item['certification'],
                    match_item['filename'],
                    match_item['path']
                ])
    elif output_format == 'json':
        export_data = []
        for movie_item, match_item in matched_records:
            item = dict(movie_item)
            item['ext'] = match_item.get('ext', '-')
            item['format'] = match_item.get('format', '-')
            item['codec'] = match_item.get('format', '-')
            item['resolution'] = match_item.get('resolution', '-')
            item['fps'] = match_item.get('fps', '-')
            item['size_gb'] = match_item.get('size_gb', '-')
            item['time'] = movie_item.get('time', '-')
            item['sub'] = match_item.get('sub', '-')
            item['jellyfin'] = match_item.get('jellyfin', '-')
            item['sized'] = match_item.get('sized', '-')
            item['oversized'] = match_item.get('oversized', '-')
            item['filename'] = match_item['filename']
            item['path'] = match_item['path']
            export_data.append(item)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
    else:  # txt
        with open(output_path, 'w', encoding='utf-8') as f:
            for movie_item, match_item in matched_records:
                ext_str = f"[{match_item.get('ext', '-')}]"
                fmt_str = f"[{match_item.get('format', '-')}]"
                res_str = f"[{match_item.get('resolution', '-')}]"
                fps_str = f"[{match_item.get('fps', '-')} fps]"
                sz_str = f"[{format_size_gb(match_item.get('size_gb'))} GB]"
                time_str = f"[{movie_item.get('time', '-')}]"
                sub_str = f"[{match_item.get('sub', '-')}]"
                bmp_str = f"[{match_item.get('bmp', '-')}]"
                srt_str = f"[{match_item.get('srt', '-')}]"
                sized_str = f"[{match_item.get('sized', '-')}]"
                title_str = movie_item.get('display_title_year', movie_item['title'])
                f.write(f"{ext_str} {fmt_str} {res_str} {fps_str} {sz_str} {time_str} {sub_str} {bmp_str} {srt_str} {sized_str} {title_str}\n")


def write_missing_file(output_path, missing_movies, output_format):
    """Write the missing database movies to the specified file."""
    if output_format == 'csv':
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['IMDB_ID', 'DVD', 'Ext', 'Fmt', 'Resolution', 'FPS', 'Size', 'Time', 'Sub', 'Jellyfin', 'Sized', 'Title', 'Original_Title', 'Watched', 'Rating', 'Certification'])
            for m in missing_movies:
                writer.writerow([
                    m['imdb_id'],
                    m['dvd'] if m['dvd'] is not None else '',
                    m.get('ext', '-'),
                    m.get('format', '-'),
                    m.get('resolution', '-'),
                    m.get('fps', '-'),
                    format_size_gb(m.get('size_gb')),
                    m.get('time', '-'),
                    m.get('sub', '-'),
                    m.get('jellyfin', '-'),
                    m.get('sized', '-'),
                    m.get('display_title_year', m['title']),
                    m['title'],
                    m['watched'],
                    m['my_rating'] if m['my_rating'] is not None else '',
                    m['certification']
                ])
    elif output_format == 'json':
        export_data = []
        for m in missing_movies:
            item = dict(m)
            item['codec'] = '-'
            item['time'] = m.get('time', '-')
            item['sub'] = m.get('sub', '-')
            item['jellyfin'] = m.get('jellyfin', '-')
            item['sized'] = m.get('sized', '-')
            export_data.append(item)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
    else:  # txt
        with open(output_path, 'w', encoding='utf-8') as f:
            for m in missing_movies:
                ext_str = f"[{m.get('ext', '-')}]"
                fmt_str = f"[{m.get('format', '-')}]"
                res_str = f"[{m.get('resolution', '-')}]"
                fps_str = f"[{m.get('fps', '-')}]"
                sz_str = f"[{format_size_gb(m.get('size_gb'))}]"
                time_str = f"[{m.get('time', '-')}]"
                sub_str = f"[{m.get('sub', '-')}]"
                bmp_str = f"[{m.get('bmp', '-')}]"
                srt_str = f"[{m.get('srt', '-')}]"
                sized_str = f"[{m.get('sized', '-')}]"
                title_str = m.get('display_title_year', m['title'])
                f.write(f"{ext_str} {fmt_str} {res_str} {fps_str} {sz_str} {time_str} {sub_str} {bmp_str} {srt_str} {sized_str} {title_str}\n")


def write_unmatched_file(output_path, unmatched_videos, output_format):
    """Write the unmatched video library files to the specified file."""
    if output_format == 'csv':
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Subfolder', 'Ext', 'Fmt', 'Resolution', 'FPS', 'Size', 'Time', 'Sub', 'Jellyfin', 'Sized', 'Filename', 'Original_Filename', 'FullPath'])
            for v in unmatched_videos:
                writer.writerow([
                    v['rel_dir'],
                    v['ext'],
                    v.get('format', '-'),
                    v['resolution'],
                    v.get('fps', '-'),
                    format_size_gb(v.get('size_gb')),
                    v.get('time', '-'),
                    v.get('sub', '-'),
                    v.get('jellyfin', '-'),
                    v.get('sized', '-'),
                    v.get('display_filename', v['filename']),
                    v['filename'],
                    v['path']
                ])
    elif output_format == 'json':
        export_data = []
        for v in unmatched_videos:
            item = dict(v)
            item['codec'] = v.get('format', '-')
            item['time'] = v.get('time', '-')
            item['sub'] = v.get('sub', '-')
            item['jellyfin'] = v.get('jellyfin', '-')
            item['sized'] = v.get('sized', '-')
            export_data.append(item)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
    else:  # txt
        with open(output_path, 'w', encoding='utf-8') as f:
            for v in unmatched_videos:
                sub = f"[{v['rel_dir']}] " if v['rel_dir'] else ""
                fmt_str = f"[{v.get('format', '-')}]"
                fps_str = f"[{v.get('fps', '-')} fps]"
                sz_str = f"[{format_size_gb(v.get('size_gb'))} GB]"
                time_str = f"[{v.get('time', '-')}]"
                sub_flag_str = f"[{v.get('sub', '-')}]"
                bmp_flag_str = f"[{v.get('bmp', '-')}]"
                srt_flag_str = f"[{v.get('srt', '-')}]"
                sized_str = f"[{v.get('sized', '-')}]"
                fn_str = v.get('display_filename', v['filename'])
                f.write(f"[{v['ext']}] {fmt_str} [{v['resolution']}] {fps_str} {sz_str} {time_str} {sub_flag_str} {bmp_flag_str} {srt_flag_str} {sized_str} {sub}{fn_str}\n")


def main():
    default_db = get_default_db_path()

    parser = argparse.ArgumentParser(
        description="Compare IMDB_Films.db entries with video files in the movies library to find matched, missing, and unmatched titles."
    )
    parser.add_argument(
        "--db",
        default=default_db,
        help=f"Path to IMDB_Films.db (default: {default_db})"
    )
    parser.add_argument(
        "--movies-dir",
        default=DEFAULT_MOVIES_DIR,
        help=f"Path to movies directory (default: {DEFAULT_MOVIES_DIR})"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Optional file path to save the missing titles list (txt, csv, or json)."
    )
    parser.add_argument(
        "--output-matched",
        default=None,
        help="Optional file path to save the matched titles list (txt, csv, or json)."
    )
    parser.add_argument(
        "--output-unmatched",
        default=None,
        help="Optional file path to save the unmatched video files list (txt, csv, or json)."
    )
    parser.add_argument(
        "--format",
        choices=['txt', 'csv', 'json'],
        default=None,
        help="Format for output file. If omitted, inferred from file extension (default: txt)."
    )
    parser.add_argument(
        "--show-only",
        choices=['all', 'matched', 'missing', 'unmatched', 'both'],
        default='all',
        help="Which section(s) to display: 'all' (default: matched, missing, and unmatched), 'matched', 'missing', 'unmatched', or 'both' (missing and unmatched)."
    )
    parser.add_argument(
        "--not-sized-only", "--oversized-only",
        dest="not_sized_only",
        action="store_true",
        help="Filter output to display/export only improperly sized (Sized=NO) video files."
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Quiet mode: prints plain title lists to stdout."
    )
    parser.add_argument(
        "--color",
        choices=['always', 'auto', 'never'],
        default='always',
        help="Colorize terminal output: 'always' (default), 'auto' (only if tty), or 'never'."
    )
    parser.add_argument(
        "--dvd-filter",
        choices=['all', 'dvd_only', 'non_dvd'],
        default='all',
        help="Filter database movies by DVD status (default: all)."
    )
    parser.add_argument(
        "--extensions",
        default=None,
        help="Comma-separated list of video extensions to scan (e.g. .m4v,.mp4,.mkv)."
    )
    parser.add_argument(
        "--skip-resolution",
        action="store_true",
        help="Skip probing video metadata via ffprobe (faster)."
    )

    args = parser.parse_args()

    # Validate database path
    if not os.path.isfile(args.db):
        print(f"Error: Database file not found at: {args.db}", file=sys.stderr)
        sys.exit(1)

    # Validate movies directory
    if not os.path.isdir(args.movies_dir):
        print(f"Error: Movies directory not found at: {args.movies_dir}", file=sys.stderr)
        sys.exit(1)

    # Video extensions
    if args.extensions:
        exts = {e.strip().lower() if e.strip().startswith('.') else f".{e.strip().lower()}"
                for e in args.extensions.split(',')}
    else:
        exts = DEFAULT_VIDEO_EXTS

    # Load data
    use_color = True
    if args.color == 'never' or os.getenv('NO_COLOR'):
        use_color = False
    elif args.color == 'auto':
        use_color = sys.stdout.isatty() or os.getenv('FORCE_COLOR') == '1'

    c_red = '[91m' if use_color else ''
    c_orange = '[38;5;208m' if use_color else ''
    c_yellow = '[93m' if use_color else ''
    c_green = '[92m' if use_color else ''
    c_reset = '[0m' if use_color else ''

    db_movies = load_db_movies(args.db)

    # Apply DVD filter if requested
    if args.dvd_filter == 'dvd_only':
        db_movies = [m for m in db_movies if str(m['dvd']) in ('1', '4', '1, 4')]
    elif args.dvd_filter == 'non_dvd':
        db_movies = [m for m in db_movies if str(m['dvd']) == '0']

    video_entries = scan_video_files(args.movies_dir, exts)

    matched, missing_db, unmatched_videos = compare_db_and_videos(db_movies, video_entries)

    # Alphabetize matched titles ignoring leading articles (using display_title)
    matched.sort(
        key=lambda item: (item[0].get('display_title', '').lower(), item[0].get('year') or 0)
    )

    # Alphabetize missing titles ignoring leading articles (using display_title)
    missing_db.sort(
        key=lambda item: (item.get('display_title', '').lower(), item.get('year') or 0)
    )

    # Alphabetize unmatched videos ignoring leading articles (using display_raw_title or display_filename)
    unmatched_videos.sort(
        key=lambda item: (item.get('display_raw_title', item.get('filename', '')).lower(), item.get('year') or 0)
    )

    # Calculate library size statistics in decimal GB (1 GB = 1024^3 bytes)
    total_library_bytes = sum(v.get('size_bytes', 0) for v in video_entries)
    total_library_gb = total_library_bytes / (1024 ** 3)

    matched_paths = {m[1]['path'] for m in matched}
    matched_bytes = sum(os.path.getsize(p) for p in matched_paths if os.path.isfile(p))
    matched_gb = matched_bytes / (1024 ** 3)

    unmatched_bytes = sum(u.get('size_bytes', 0) for u in unmatched_videos)
    unmatched_gb = unmatched_bytes / (1024 ** 3)

    # Probe format/codec, resolution & fps if needed
    if not args.skip_resolution:
        # Probe matched video files
        if args.show_only in ('all', 'matched') or args.output_matched or True:
            matched_meta = batch_probe_metadata(
                matched, lambda m: m[1]['path'], verbose=(not args.quiet)
            )
            for (movie_item, match_item), (fmt_val, r, fps, t_val, sub_val, jf_val) in zip(matched, matched_meta):
                movie_item['format'] = fmt_val
                movie_item['resolution'] = r
                movie_item['fps'] = fps
                if movie_item.get('time', '-') == '-' and t_val != '-':
                    movie_item['time'] = t_val
                match_item['time'] = movie_item.get('time', '-')
                movie_item['sub'] = sub_val
                match_item['sub'] = sub_val
                movie_item['jellyfin'] = jf_val
                match_item['jellyfin'] = jf_val
                sized_val = check_sized(r, match_item.get('size_gb'), movie_item.get('time'))
                movie_item['sized'] = sized_val
                match_item['sized'] = sized_val
                movie_item['oversized'] = 'YES' if sized_val == 'NO' else ('NO' if sized_val == 'YES' else '-')
                match_item['oversized'] = movie_item['oversized']
                match_item['format'] = fmt_val
                match_item['resolution'] = r
                match_item['fps'] = fps

        # Probe unmatched video files
        if args.show_only in ('all', 'unmatched', 'both') or args.output_unmatched or True:
            unmatched_meta = batch_probe_metadata(
                unmatched_videos, lambda v: v['path'], verbose=(not args.quiet)
            )
            for v, (fmt_val, r, fps, t_val, sub_val, jf_val) in zip(unmatched_videos, unmatched_meta):
                v['format'] = fmt_val
                v['resolution'] = r
                v['fps'] = fps
                if t_val != '-':
                    v['time'] = t_val
                v['sub'] = sub_val
                v['jellyfin'] = jf_val
                v['sized'] = check_sized(r, v.get('size_gb'), v.get('time'))
                v['oversized'] = 'YES' if v['sized'] == 'NO' else ('NO' if v['sized'] == 'YES' else '-')

        # Ensure unmatched videos have duration probed if not already present
        missing_unmatched_dur = [v for v in unmatched_videos if v.get('time', '-') == '-']
        if missing_unmatched_dur:
            cache = load_resolution_cache()
            def _probe_dur_single(v_entry):
                p = v_entry['path']
                try:
                    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]
                    dur = subprocess.check_output(cmd, timeout=5, stderr=subprocess.DEVNULL).decode().strip()
                    t = format_time_seconds(dur)
                    if t != '-':
                        v_entry['time'] = t
                        st = os.stat(p)
                        k = f"{p}|{st.st_mtime}|{st.st_size}"
                        with _cache_lock:
                            if k in cache and isinstance(cache[k], dict):
                                cache[k]['time'] = t
                except Exception:
                    pass
            with ThreadPoolExecutor(max_workers=24) as ex:
                list(ex.map(_probe_dur_single, missing_unmatched_dur))
            save_resolution_cache(cache)
            for v in unmatched_videos:
                v['sized'] = check_sized(v.get('resolution'), v.get('size_gb'), v.get('time'))
                v['oversized'] = 'YES' if v['sized'] == 'NO' else ('NO' if v['sized'] == 'YES' else '-')

    # Calculate sized totals (Sized=NO means improperly sized / oversized)
    matched_not_sized_count = sum(1 for _, match_item in matched if match_item.get('sized') == 'NO')
    matched_not_sized_bytes = sum(
        os.path.getsize(m[1]['path']) for m in matched
        if m[1].get('sized') == 'NO' and os.path.isfile(m[1]['path'])
    )
    matched_not_sized_gb = matched_not_sized_bytes / (1024 ** 3)

    unmatched_not_sized_count = sum(1 for v in unmatched_videos if v.get('sized') == 'NO')
    unmatched_not_sized_bytes = sum(v.get('size_bytes', 0) for v in unmatched_videos if v.get('sized') == 'NO')
    unmatched_not_sized_gb = unmatched_not_sized_bytes / (1024 ** 3)

    total_not_sized_count = matched_not_sized_count + unmatched_not_sized_count
    total_not_sized_gb = (matched_not_sized_bytes + unmatched_not_sized_bytes) / (1024 ** 3)

    # Filter for not-sized-only / oversized-only if requested
    is_filtered_not_sized = getattr(args, 'not_sized_only', False) or getattr(args, 'oversized_only', False)
    if is_filtered_not_sized:
        matched = [(mov, mat) for mov, mat in matched if mat.get('sized') == 'NO']
        missing_db = []  # Missing movies have no file on disk, so they cannot be improperly sized
        unmatched_videos = [v for v in unmatched_videos if v.get('sized') == 'NO']

    # Determine output format for primary output file
    fmt = args.format
    if args.output and not fmt:
        ext = os.path.splitext(args.output)[1].lower()
        if ext == '.csv':
            fmt = 'csv'
        elif ext == '.json':
            fmt = 'json'
        else:
            fmt = 'txt'
    elif not fmt:
        fmt = 'txt'

    # Save to files if requested
    if args.output:
        if args.show_only == 'matched':
            write_matched_file(args.output, matched, fmt)
        elif args.show_only == 'unmatched':
            write_unmatched_file(args.output, unmatched_videos, fmt)
        else:
            write_missing_file(args.output, missing_db, fmt)

    if args.output_matched:
        matched_fmt = args.format
        if not matched_fmt:
            ext = os.path.splitext(args.output_matched)[1].lower()
            if ext == '.csv':
                matched_fmt = 'csv'
            elif ext == '.json':
                matched_fmt = 'json'
            else:
                matched_fmt = 'txt'
        write_matched_file(args.output_matched, matched, matched_fmt)

    if args.output_unmatched:
        unmatched_fmt = args.format
        if not unmatched_fmt:
            ext = os.path.splitext(args.output_unmatched)[1].lower()
            if ext == '.csv':
                unmatched_fmt = 'csv'
            elif ext == '.json':
                unmatched_fmt = 'json'
            else:
                unmatched_fmt = 'txt'
        write_unmatched_file(args.output_unmatched, unmatched_videos, unmatched_fmt)

    # Output to stdout
    try:
        if args.quiet:
            if args.show_only in ('all', 'matched'):
                if args.show_only == 'all':
                    print("=== MATCHED TITLES (IN DB AND VIDEO LIBRARY) ===")
                for movie_item, match_item in matched:
                    fmt_str = match_item.get('format', '-')
                    sz_str = f"{format_size_gb(match_item.get('size_gb'))}GB"
                    fps_str = f"{match_item.get('fps', '-')}fps"
                    time_str = movie_item.get('time', '-')
                    sub_str = match_item.get('sub', '-')
                    jf_str = match_item.get('jellyfin', '-')
                    sized_str = match_item.get('sized', '-')
                    disp_title = movie_item.get('display_title_year', movie_item['title'])
                    print(f"{match_item.get('ext', '-'):<5} {fmt_str:<6} {match_item.get('resolution', '-'):<7} {fps_str:<9} {sz_str:<9} {time_str:<9} {sub_str:<8} {jf_str:<11} {sized_str:<6} {disp_title}")
            if args.show_only in ('all', 'missing', 'both') and not is_filtered_not_sized:
                if args.show_only in ('all', 'both'):
                    print("\n=== MISSING TITLES (IN DB, NO VIDEO FILE) ===")
                for m in missing_db:
                    time_str = m.get('time', '-')
                    disp_title = m.get('display_title_year', m['title'])
                    print(f"{m.get('ext', '-'):<5} {'-':<6} {m.get('resolution', '-'):<7} {'-':<9} {'-':<9} {time_str:<9} {'-':<8} {'-':<11} {'-':<6} {disp_title}")
            if args.show_only in ('all', 'unmatched', 'both'):
                if args.show_only in ('all', 'both'):
                    print("\n=== UNMATCHED TITLES (VIDEO FILE ON DISK, NOT IN DB) ===")
                for v in unmatched_videos:
                    sub = f"[{v['rel_dir']}] " if v['rel_dir'] else ""
                    fmt_str = v.get('format', '-')
                    sz_str = f"{format_size_gb(v.get('size_gb'))}GB"
                    fps_str = f"{v.get('fps', '-')}fps"
                    time_str = v.get('time', '-')
                    sub_str = v.get('sub', '-')
                    jf_str = v.get('jellyfin', '-')
                    sized_str = v.get('sized', '-')
                    disp_fn = f"{sub}{v.get('display_filename', v['filename'])}"
                    print(f"{v['ext']:<5} {fmt_str:<6} {v['resolution']:<7} {fps_str:<9} {sz_str:<9} {time_str:<9} {sub_str:<8} {jf_str:<11} {sized_str:<6} {disp_fn}")
        else:
            banner_len = 134
            print("=" * banner_len)
            print("  IMDB_Films.db vs Video Library Comparison")
            print("=" * banner_len)
            print(f"  Database Path:            {args.db}")
            print(f"  Movies Directory:         {args.movies_dir}")
            print(f"  Total Video Library Size: {total_library_gb:,.2f} GB")
            print(f"  Improperly Sized Files:   {total_not_sized_count:,} files  ({total_not_sized_gb:,.2f} GB)")
            print(f"  DB Titles Total:          {len(db_movies):,}")
            print(f"  Video Files Total:        {len(video_entries):,}  ({total_library_gb:,.2f} GB)")
            print(f"  Matched DB Titles:        {len(matched):,}  ({matched_gb:,.2f} GB, {matched_not_sized_count:,} improperly sized)")
            print(f"  Missing in Video Library: {len(missing_db):,}  (in DB, no video file)")
            print(f"  Unmatched Library Videos: {len(unmatched_videos):,}  (video on disk, not in DB, {unmatched_gb:,.2f} GB, {unmatched_not_sized_count:,} improperly sized)")
            print("-" * banner_len)
            print("  Notes:")
            print("    1. Format:    H264 is best for older hardware such as 2011 Sony Bravia.")
            print("    2. Sized:     resample_library could be run on Sized=NO to dramatically save space.")
            print("    3. Missing:   Missing titles could be restored by re-ripping hard DVD in storage.")
            print("    4. Resample:  Running resample_library is time-consuming.")
            print("    5. Subtitles: Running fetch_subtitles is not time-consuming.")
            print("-" * banner_len)
            print("  Color Key:")
            print(f"    {c_green}● Green:{c_reset}   Clean (Sized=YES & Jellyfin DIRECT text subtitles)")
            print(f"    {c_yellow}● Yellow:{c_reset}  Heavy Jellyfin load (TRANSCODE for bitmap subs; fix: run resample_library or fetch_subtitles)")
            print(f"    {c_orange}● Orange:{c_reset}  Improperly Sized (Sized=NO; fix: run resample_library)")
            print(f"    {c_red}● Red:{c_reset}     No subtitles (no English subs in Jellyfin; fix: run resample_library or fetch_subtitles)")
            print("=" * banner_len)

            # Section 1: Matched Titles (Output before Missing Titles)
            if args.show_only in ('all', 'matched'):
                sized_label = f", {matched_not_sized_count:,} improperly sized" if not is_filtered_not_sized else " [ALL IMPROPERLY SIZED]"
                print(f"\n[1] Matched Titles in Video Library ({len(matched):,} items, {matched_gb:,.2f} GB{sized_label}):\n")
                print(f"  {'IMDB ID':<10} {'DVD':<5} {'Ext':<6} {'Fmt':<6} {'Res':<7} {'FPS':<6} {'Size':>6}   {'Time':<6} {'Sub':<8} {'Jellyfin':<11} {'Sized':<7} {'Title'}")
                print(f"  {'-'*8:<10} {'-'*3:<5} {'-'*4:<6} {'-'*4:<6} {'-'*5:<7} {'-'*4:<6} {'-'*5:>6}   {'-'*5:<6} {'-'*6:<8} {'-'*8:<11} {'-'*5:<7} {'-'*46}")
                for movie_item, match_item in matched:
                    dvd_display = str(movie_item['dvd']) if movie_item['dvd'] is not None else "-"
                    ext_display = match_item.get('ext', '-')
                    fmt_display = match_item.get('format', '-')
                    res_display = match_item.get('resolution', '-')
                    fps_display = match_item.get('fps', '-')
                    sz_display = format_size_gb(match_item.get('size_gb'))
                    time_display = movie_item.get('time', '-')
                    sub_display = match_item.get('sub', '-')
                    jf_display = match_item.get('jellyfin', '-')
                    sized_display = match_item.get('sized', '-')
                    title_display = movie_item.get('display_title_year', movie_item['title'])
                    r_c, s_c, j_c, sz_c, rst = get_entry_colors(sub_display, jf_display, sized_display, True, use_color)
                    sub_p = f"{s_c}{sub_display:<8}{r_c}" if use_color else f"{sub_display:<8}"
                    jf_p = f"{j_c}{jf_display:<11}{r_c}" if use_color else f"{jf_display:<11}"
                    sized_p = f"{sz_c}{sized_display:<7}{r_c}" if use_color else f"{sized_display:<7}"
                    print(f"{r_c}  {movie_item['imdb_id']:<10} {dvd_display:<5} {ext_display:<6} {fmt_display:<6} {res_display:<7} {fps_display:<6} {sz_display:>6}   {time_display:<6} {sub_p} {jf_p} {sized_p} {title_display}{rst}")

            # Section 2: Missing DB Titles
            if args.show_only in ('all', 'missing', 'both') and not is_filtered_not_sized:
                sec_num = 2 if args.show_only == 'all' else 1
                print(f"\n[{sec_num}] Missing Titles in Video Library ({len(missing_db):,} items in DB without video):\n")
                print(f"  {'IMDB ID':<10} {'DVD':<5} {'Ext':<6} {'Fmt':<6} {'Res':<7} {'FPS':<6} {'Size':>6}   {'Time':<6} {'Sub':<8} {'Jellyfin':<11} {'Sized':<7} {'Title'}")
                print(f"  {'-'*8:<10} {'-'*3:<5} {'-'*4:<6} {'-'*4:<6} {'-'*5:<7} {'-'*4:<6} {'-'*5:>6}   {'-'*5:<6} {'-'*6:<8} {'-'*8:<11} {'-'*5:<7} {'-'*46}")
                for m in missing_db:
                    dvd_display = str(m['dvd']) if m['dvd'] is not None else "-"
                    ext_display = m.get('ext', '-')
                    fmt_display = m.get('format', '-')
                    res_display = m.get('resolution', '-')
                    fps_display = m.get('fps', '-')
                    sz_display = format_size_gb(m.get('size_gb'))
                    time_display = m.get('time', '-')
                    sub_display = m.get('sub', '-')
                    jf_display = m.get('jellyfin', '-')
                    sized_display = m.get('sized', '-')
                    title_display = m.get('display_title_year', m['title'])
                    r_c, s_c, j_c, sz_c, rst = get_entry_colors('-', '-', '-', False, use_color)
                    sub_p = f"{s_c}{sub_display:<8}{r_c}" if use_color else f"{sub_display:<8}"
                    jf_p = f"{j_c}{jf_display:<11}{r_c}" if use_color else f"{jf_display:<11}"
                    sized_p = f"{sz_c}{sized_display:<7}{r_c}" if use_color else f"{sized_display:<7}"
                    print(f"{r_c}  {m['imdb_id']:<10} {dvd_display:<5} {ext_display:<6} {fmt_display:<6} {res_display:<7} {fps_display:<6} {sz_display:>6}   {time_display:<6} {sub_p} {jf_p} {sized_p} {title_display}{rst}")

            # Section 3: Unmatched Library Video Files
            if args.show_only in ('all', 'unmatched', 'both'):
                sec_num = 3 if (args.show_only == 'all' and not is_filtered_not_sized) else (2 if args.show_only in ('all', 'both') else 1)
                sized_label = f", {unmatched_not_sized_count:,} improperly sized" if not is_filtered_not_sized else " [ALL IMPROPERLY SIZED]"
                print(f"\n[{sec_num}] Unmatched Titles in Video Library ({len(unmatched_videos):,} video files not in DB, {unmatched_gb:,.2f} GB{sized_label}):\n")
                print(f"  {'Subfolder':<16} {'Ext':<6} {'Fmt':<6} {'Res':<7} {'FPS':<6} {'Size':>6}   {'Time':<6} {'Sub':<8} {'Jellyfin':<11} {'Sized':<7} {'Filename'}")
                print(f"  {'-'*14:<16} {'-'*4:<6} {'-'*4:<6} {'-'*5:<7} {'-'*4:<6} {'-'*5:>6}   {'-'*5:<6} {'-'*6:<8} {'-'*8:<11} {'-'*5:<7} {'-'*46}")
                for v in unmatched_videos:
                    subfolder_display = v['rel_dir'] if v['rel_dir'] else "-"
                    fmt_display = v.get('format', '-')
                    fps_display = v.get('fps', '-')
                    sz_display = format_size_gb(v.get('size_gb'))
                    time_display = v.get('time', '-')
                    sub_display = v.get('sub', '-')
                    jf_display = v.get('jellyfin', '-')
                    sized_display = v.get('sized', '-')
                    fn_display = v.get('display_filename', v['filename'])
                    r_c, s_c, j_c, sz_c, rst = get_entry_colors(sub_display, jf_display, sized_display, True, use_color)
                    sub_p = f"{s_c}{sub_display:<8}{r_c}" if use_color else f"{sub_display:<8}"
                    jf_p = f"{j_c}{jf_display:<11}{r_c}" if use_color else f"{jf_display:<11}"
                    sized_p = f"{sz_c}{sized_display:<7}{r_c}" if use_color else f"{sized_display:<7}"
                    print(f"{r_c}  {subfolder_display:<16} {v['ext']:<6} {fmt_display:<6} {v['resolution']:<7} {fps_display:<6} {sz_display:>6}   {time_display:<6} {sub_p} {jf_p} {sized_p} {fn_display}{rst}")

            if args.output_matched:
                print(f"\n[+] Matched list saved to: {os.path.abspath(args.output_matched)}")
            if args.output:
                print(f"[+] Missing list saved to: {os.path.abspath(args.output)} ({fmt.upper()} format)")
            if args.output_unmatched:
                print(f"[+] Unmatched list saved to: {os.path.abspath(args.output_unmatched)}")
            print()
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()

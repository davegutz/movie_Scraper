#!/usr/bin/env python3
"""
checks_subtitles_vision.py - Visual Subtitle Verification Tool.

Performs visual verification of subtitles across movie files using FFmpeg frame
capture and Google Gemini Multimodal Vision API.

Outputs the filename and PASS or FAIL status for each movie.
If it is not possible to run the visual check on a file (e.g., no subtitle track,
dialogue cues cannot be parsed, frame capture failed, or Gemini API key missing),
the file is categorized as FAIL.

By default, output is sorted by date of file (most recent modified date first),
with an option to sort by name (--name / --sort-by name).

Usage Examples:
  # Check all movies in the default library directory (sorted by file date by default)
  python3 checks_subtitles_vision.py

  # Check movies sorted by name
  python3 checks_subtitles_vision.py --name
  python3 checks_subtitles_vision.py --sort-by name

  # Check the 5 most recently modified movies
  python3 checks_subtitles_vision.py --max-files 5

  # Check the first 5 movies alphabetically by name
  python3 checks_subtitles_vision.py --name --max-files 5

  # Check a specific movie file
  python3 checks_subtitles_vision.py --file "/media/daveg/Lib/Movies/The Sting (1973).m4v"

  # Supply Gemini API key directly (or export GEMINI_API_KEY="...")
  python3 checks_subtitles_vision.py --gemini-api-key "AIzaSy..."

  # Output simple format (plain filename and status)
  python3 checks_subtitles_vision.py --format simple

  # Display only failed movies
  python3 checks_subtitles_vision.py --failures-only
"""

import argparse
import os
import re
import sys
import time
from typing import Dict, Any, List, Optional

# Ensure repository directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    import verify_jellyfin_subtitles as vjs
except ImportError as err:
    print(f"Error: Failed to import verify_jellyfin_subtitles module: {err}", file=sys.stderr)
    sys.exit(1)

DEFAULT_MOVIES_DIR = "/media/daveg/Lib/Movies"
DEFAULT_VIDEO_EXTS = ('.mp4', '.m4v', '.mkv', '.avi', '.mov', '.wmv')

ARTICLE_PATTERN = re.compile(r'^(the|a|an|le|la|les|il|lo|gli|el|los|las|der|das)\s+(.*)$', re.IGNORECASE)
L_APOSTROPHE_PATTERN = re.compile(r"^(l\')\s*(.*)$", re.IGNORECASE)


def get_entry_colors(use_color: bool = True):
    if not use_color:
        return "", "", ""
    green = "\033[92m"
    red = "\033[91m"
    reset = "\033[0m"
    return green, red, reset


def name_sort_key(file_path: str):
    """
    Produce a sort key for a movie filename ignoring leading articles
    ('The', 'A', 'An', 'Le', 'La', etc.) and case.
    """
    filename = os.path.basename(file_path)
    base, _ = os.path.splitext(filename)
    s = base.strip()
    m = ARTICLE_PATTERN.match(s)
    if m:
        s = m.group(2).strip()
    else:
        m_l = L_APOSTROPHE_PATTERN.match(s)
        if m_l:
            s = m_l.group(2).strip()
    return s.lower(), filename.lower()


def get_file_mtime(file_path: str) -> float:
    """Return modification time (st_mtime) of file, or 0.0 on error."""
    try:
        return os.path.getmtime(file_path)
    except Exception:
        return 0.0


def sort_video_files(video_files: List[str], sort_by: str = 'date') -> List[str]:
    """
    Sort video files:
      - 'date' / 'mtime' / 'recent': most recent file modified date first (default).
      - 'name' / 'title' / 'alpha': alphabetical by movie name ignoring leading articles.
    """
    if sort_by in ('name', 'title', 'alpha'):
        return sorted(video_files, key=name_sort_key)
    else:
        # Default: date of file (most recent first)
        return sorted(
            video_files,
            key=lambda p: (-get_file_mtime(p), name_sort_key(p))
        )


def find_video_files(movies_dir: str, extensions=DEFAULT_VIDEO_EXTS, sort_by: str = 'date') -> List[str]:
    """Recursively find all valid video files in the movies directory, excluding backups and temp files."""
    video_files = []
    if not os.path.isdir(movies_dir):
        return video_files

    for root, _, files in os.walk(movies_dir):
        for f in files:
            if f.endswith('.bak') or f.endswith('.part') or f.startswith('.'):
                continue
            _, ext = os.path.splitext(f)
            if ext.lower() in extensions:
                video_files.append(os.path.join(root, f))
    return sort_video_files(video_files, sort_by=sort_by)


def check_single_movie_vision(
    video_path: str,
    gemini_api_key: Optional[str] = None,
    samples: int = 1,
    model: str = vjs.DEFAULT_MODEL
) -> Dict[str, Any]:
    """
    Perform visual verification of subtitles for a single video file.
    Categorizes the result as PASS or FAIL.
    If it is not possible to run the visual check, it returns FAIL with the reason.
    """
    filename = os.path.basename(video_path)
    mtime = get_file_mtime(video_path)
    modified_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime)) if mtime > 0 else '-'

    # 1. Existence check
    if not os.path.isfile(video_path):
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': 'File not found on disk',
            'details': {}
        }

    # 2. Check subtitle track presence
    try:
        sub_type, sub_target, sub_meta = vjs.get_subtitle_source(video_path)
    except Exception as ex:
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': f'Error probing subtitle tracks: {ex}',
            'details': {}
        }

    if sub_type == 'none':
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': 'No subtitles found (sidecar or embedded)',
            'details': {'sub_type': 'none'}
        }

    # 3. Check if dialogue cues can be extracted
    try:
        cues = vjs.extract_cues(video_path, sub_type, sub_target)
    except Exception as ex:
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': f'Error extracting subtitle cues: {ex}',
            'details': {'sub_type': sub_type}
        }

    if not cues and sub_type != 'embedded_bitmap':
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': 'No dialogue cues could be parsed from subtitle track',
            'details': {'sub_type': sub_type}
        }

    # 4. Check Gemini API key for vision verification
    api_key = gemini_api_key or vjs.get_gemini_api_key()
    if not api_key:
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': 'Gemini API key not configured (cannot perform visual vision check)',
            'details': {'sub_type': sub_type, 'cues_available': len(cues)}
        }

    # 5. Perform visual verification
    try:
        verify_res = vjs.verify_movie_subtitles(
            video_path=video_path,
            samples=samples,
            gemini_api_key=api_key,
            model=model
        )
    except Exception as ex:
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': f'Visual verification failed with error: {ex}',
            'details': {}
        }

    if verify_res.get('verified'):
        detected = verify_res.get('detected_text') or verify_res.get('expected_text') or ''
        sample_info = f' (cue: "{detected[:40]}")' if detected else ""
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'PASS',
            'reason': f'Subtitles verified with Gemini Vision{sample_info}',
            'details': verify_res
        }
    else:
        notes = verify_res.get('notes') or verify_res.get('status') or 'Unknown verification failure'
        return {
            'filename': filename,
            'path': video_path,
            'mtime': mtime,
            'modified': modified_str,
            'status': 'FAIL',
            'reason': f'Vision check failed ({notes})',
            'details': verify_res
        }


def main():
    parser = argparse.ArgumentParser(
        description="Visual subtitle verification tool. Checks whether subtitles are rendered and legible on video frames using Gemini Multimodal Vision API."
    )
    parser.add_argument(
        "--movies-dir",
        default=DEFAULT_MOVIES_DIR,
        help=f"Directory to scan for movies (default: {DEFAULT_MOVIES_DIR})."
    )
    parser.add_argument(
        "--file", "-f",
        dest="specific_file",
        default=None,
        help="Check a single specific video file instead of scanning directory."
    )
    parser.add_argument(
        "--max-files", "-n",
        type=int,
        default=None,
        help="Maximum number of files to check."
    )
    parser.add_argument(
        "--sort-by",
        choices=['date', 'mtime', 'recent', 'name', 'title', 'alpha'],
        default='date',
        help="Sort order: 'date' / 'mtime' / 'recent' (most recent file modified date first, default), or 'name' / 'title' / 'alpha' (alphabetical by name ignoring leading articles)."
    )
    parser.add_argument(
        "--sort-by-date", "--date", "--sort-by-mtime", "--recent",
        dest="sort_by",
        action="store_const",
        const="date",
        help="Alias for --sort-by date: sort movies by file modified date (most recent first, default)."
    )
    parser.add_argument(
        "--sort-by-name", "--name", "--sort-by-title", "--title",
        dest="sort_by",
        action="store_const",
        const="name",
        help="Alias for --sort-by name: sort movies alphabetically by name ignoring leading articles."
    )
    parser.add_argument(
        "--gemini-api-key",
        default=None,
        help="Google Gemini API key for visual inspection (defaults to GEMINI_API_KEY environment variable or ~/.config/gemini/api_key)."
    )
    parser.add_argument(
        "--model",
        default=vjs.DEFAULT_MODEL,
        help=f"Gemini vision model to use (default: {vjs.DEFAULT_MODEL})."
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=1,
        help="Number of dialogue cue frames to sample per movie (default: 1)."
    )
    parser.add_argument(
        "--format",
        choices=['standard', 'simple', 'table', 'csv', 'json'],
        default='standard',
        help="Output format: 'standard' (filename: STATUS with reason), 'simple' (filename STATUS), 'table', 'csv', or 'json'."
    )
    parser.add_argument(
        "--failures-only",
        action="store_true",
        help="Only display files that FAIL."
    )
    parser.add_argument(
        "--pass-only",
        action="store_true",
        help="Only display files that PASS."
    )
    parser.add_argument(
        "--color",
        choices=['always', 'auto', 'never'],
        default='auto',
        help="Colorize terminal output: 'always', 'auto' (default: if tty), or 'never'."
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress summary banner and print only results."
    )

    args = parser.parse_args()

    use_color = (args.color == 'always') or (args.color == 'auto' and sys.stdout.isatty())
    c_green, c_red, c_reset = get_entry_colors(use_color)

    # Resolve files to process
    if args.specific_file:
        raw_target = os.path.abspath(args.specific_file)
        if not os.path.exists(raw_target):
            # Try finding within movies_dir
            cand = vjs.find_video_file(args.specific_file, args.movies_dir)
            if cand:
                raw_target = cand
            else:
                print(f"Error: Specified movie file not found: {args.specific_file}", file=sys.stderr)
                sys.exit(1)
        video_files = [raw_target]
    else:
        if not os.path.isdir(args.movies_dir):
            print(f"Error: Movies directory not found: {args.movies_dir}", file=sys.stderr)
            sys.exit(1)
        video_files = find_video_files(args.movies_dir, sort_by=args.sort_by)
        if args.max_files and args.max_files > 0:
            video_files = video_files[:args.max_files]

    total_files = len(video_files)
    if total_files == 0:
        print("No video files found to check.")
        sys.exit(0)

    api_key = args.gemini_api_key or vjs.get_gemini_api_key()

    if not args.quiet and args.format in ('standard', 'table'):
        sort_desc = "Most Recent File Modified Date" if args.sort_by in ('date', 'mtime', 'recent') else "Alphabetical by Name"
        print("=" * 80)
        print("  Subtitle Visual Vision Verification")
        print("=" * 80)
        print(f"  Target Directory:  {args.movies_dir}")
        print(f"  Files Queued:      {total_files:,}")
        print(f"  Sort Order:        {sort_desc}")
        print(f"  Samples per Movie: {args.samples}")
        print(f"  Gemini Vision API: {'Configured (' + args.model + ')' if api_key else 'Missing (all checks will FAIL)'}")
        print("=" * 80)
        print()

    results = []
    pass_count = 0
    fail_count = 0
    t0 = time.time()

    if args.format == 'csv':
        import csv
        writer = csv.writer(sys.stdout)
        writer.writerow(['Filename', 'Status', 'Reason', 'Path'])

    for idx, fpath in enumerate(video_files, 1):
        res = check_single_movie_vision(
            video_path=fpath,
            gemini_api_key=api_key,
            samples=args.samples,
            model=args.model
        )
        results.append(res)
        status = res['status']
        fn = res['filename']
        reason = res['reason']

        if status == 'PASS':
            pass_count += 1
        else:
            fail_count += 1

        if args.failures_only and status != 'FAIL':
            continue
        if args.pass_only and status != 'PASS':
            continue

        # Format printing
        if args.format == 'simple':
            print(f"{fn} {status}")
        elif args.format == 'standard':
            if status == 'PASS':
                print(f"{fn}: {c_green}PASS{c_reset}")
            else:
                print(f"{fn}: {c_red}FAIL{c_reset} ({reason})")
        elif args.format == 'table':
            status_disp = f"{c_green}PASS{c_reset}" if status == 'PASS' else f"{c_red}FAIL{c_reset}"
            print(f"  [{idx:>4}/{total_files:<4}] {fn:<48}  {status_disp}  {reason}")
        elif args.format == 'csv':
            writer.writerow([fn, status, reason, fpath])

        sys.stdout.flush()

    elapsed = time.time() - t0

    if args.format == 'json':
        import json
        out_data = {
            'total_files': total_files,
            'pass_count': pass_count,
            'fail_count': fail_count,
            'elapsed_seconds': round(elapsed, 2),
            'results': results
        }
        print(json.dumps(out_data, indent=2))
        sys.exit(0 if fail_count == 0 else 1)

    if not args.quiet and args.format in ('standard', 'table'):
        print()
        print("=" * 80)
        print("  Subtitle Visual Vision Verification Summary")
        print("=" * 80)
        print(f"  Total Checked:  {total_files:,}")
        print(f"  Passed:         {c_green}{pass_count:,}{c_reset}")
        print(f"  Failed:         {c_red}{fail_count:,}{c_reset}")
        print(f"  Elapsed Time:   {vjs.format_seconds_to_timestamp(elapsed)}")
        print("=" * 80)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()

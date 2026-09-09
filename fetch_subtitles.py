#!/usr/bin/env python3
"""
fetch_subtitles.py - Fetch English .srt subtitles for movie library files.

Specifically targeted at movies that only have bitmap DVD subtitles (e.g., Fitzcarraldo)
or movies missing subtitles completely, making them fully compatible with Jellyfin, Roku,
and web clients without requiring server transcoding.

Usage:
  python3 fetch_subtitles.py "Fitzcarraldo"
  python3 fetch_subtitles.py "/media/daveg/Lib/Movies/Fitzcarraldo (1982).m4v"
  python3 fetch_subtitles.py --all-bmp              # Fetch .en.srt for all movies that only have bitmap subtitles
  python3 fetch_subtitles.py --all-bmp --dry-run    # Preview matches without downloading
  python3 fetch_subtitles.py --all-missing          # Fetch .en.srt for all movies missing subtitles
"""

import argparse
import base64
import io
import json
import os
import re
import sqlite3
import sys
import time
import zipfile

try:
    import requests
except ImportError:
    requests = None

# Default paths
DEFAULT_MOVIES_DIR = "/media/daveg/Lib/Movies"
DEFAULT_DB_PATH = "/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db"
CACHE_PATH = os.path.expanduser("~/.cache/movie_scraper/video_res_cache.json")

VIDEO_EXTENSIONS = {'.m4v', '.mp4', '.mkv', '.avi', '.mov', '.mpg', '.mpeg', '.ts', '.m2ts', '.wmv', '.webm'}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0"


def get_http(url, timeout=12):
    """Fetch URL content using requests (preferred) or urllib."""
    headers = {"User-Agent": USER_AGENT}
    if requests is not None:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.content
        return None
    else:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            return None


def normalize_title(title):
    if not title:
        return ""
    import unicodedata
    title = unicodedata.normalize('NFKD', title).encode('ASCII', 'ignore').decode('utf-8')
    title = re.sub(r'[^\w\s]', ' ', title)
    return ' '.join(title.lower().split())


def get_imdb_mapping(db_path):
    """
    Query IMDB_Films.db and return dictionaries:
    mapping by normalized title, with year, and base title -> imdb_id ('tt0083946')
    """
    mapping = {}
    if not os.path.isfile(db_path):
        return mapping

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT IMDB_ID, title, year FROM My_Films WHERE IMDB_ID IS NOT NULL")
        for row in cur.fetchall():
            imdb_int, title, year = row[0], row[1], row[2]
            if not title:
                continue
            imdb_id = f"tt{int(imdb_int):07d}" if str(imdb_int).isdigit() else str(imdb_int)
            clean_t = title.strip()
            norm_t = normalize_title(clean_t)
            mapping[norm_t] = imdb_id
            if year:
                mapping[f"{norm_t} {year}"] = imdb_id
                mapping[f"{norm_t} ({year})"] = imdb_id
                mapping[normalize_title(f"{clean_t} {year}")] = imdb_id
        conn.close()
    except Exception as e:
        print(f"Warning: Could not read DB '{db_path}': {e}", file=sys.stderr)
    return mapping


def match_movie_imdb(file_path, imdb_mapping):
    """Extract movie title from filename and look up IMDb ID."""
    base = os.path.splitext(os.path.basename(file_path))[0].strip()
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", base).strip()

    # Try normalized base
    norm_base = normalize_title(cleaned)
    if norm_base in imdb_mapping:
        return imdb_mapping[norm_base], cleaned

    # Try extracting title and year: "Title (YYYY)"
    m = re.match(r"^(.*?)\s*\((\d{4})\)", cleaned)
    if m:
        raw_t = m.group(1).strip()
        yr = m.group(2)
        norm_t = normalize_title(raw_t)
        if f"{norm_t} {yr}" in imdb_mapping:
            return imdb_mapping[f"{norm_t} {yr}"], cleaned
        if norm_t in imdb_mapping:
            return imdb_mapping[norm_t], cleaned

    # Clean disc/part notations
    no_part = re.sub(r"\s*(?:part|pt|disc|side|cd)\s*\d+.*$", "", cleaned, flags=re.IGNORECASE).strip()
    norm_no_part = normalize_title(no_part)
    if norm_no_part in imdb_mapping:
        return imdb_mapping[norm_no_part], no_part

    return None, cleaned


def search_yts_subs_by_imdb(imdb_id):
    """Search yts-subs.com using IMDb ID and return list of download page URLs for English."""
    url = f"https://yts-subs.com/movie-imdb/{imdb_id}"
    html_bytes = get_http(url)
    if not html_bytes:
        return []

    html = html_bytes.decode("utf-8", errors="ignore")
    rows = re.findall(r'<tr[^>]*data-id="(\d+)"[^>]*>(.*?)</tr>', html, re.DOTALL)
    english_pages = []

    for _, row_content in rows:
        # Check if English
        if '<span class="sub-lang">English</span>' in row_content:
            m_link = re.search(r'<a[^>]+href="(/subtitles/[^"]+)"', row_content)
            if m_link:
                english_pages.append(f"https://yts-subs.com{m_link.group(1)}")

    return english_pages


def search_yts_subs_by_title(title):
    """Search yts-subs.com by movie title."""
    import urllib.parse
    query = urllib.parse.quote_plus(title)
    url = f"https://yts-subs.com/search?q={query}"
    html_bytes = get_http(url)
    if not html_bytes:
        return []

    html = html_bytes.decode("utf-8", errors="ignore")
    movie_links = re.findall(r'<div class="media-body">\s*<a href="(/movie-imdb/[^"]+)"', html)
    if not movie_links:
        return []

    # Take first movie match
    first_movie_url = f"https://yts-subs.com{movie_links[0]}"
    m_imdb = re.search(r'/movie-imdb/(tt\d+)', first_movie_url)
    if m_imdb:
        return search_yts_subs_by_imdb(m_imdb.group(1))
    return []


def download_srt_from_yts_page(page_url):
    """
    Given a subtitle detail page on yts-subs.com, extract base64 zip link,
    download zip in memory, and extract the raw .srt string.
    """
    html_bytes = get_http(page_url)
    if not html_bytes:
        return None

    html = html_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'data-link="([a-zA-Z0-9+/=]+)"', html)
    if not m:
        return None

    try:
        zip_url = base64.b64decode(m.group(1)).decode("utf-8")
        zip_bytes = get_http(zip_url)
        if not zip_bytes:
            return None

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for fname in z.namelist():
                if fname.lower().endswith(".srt"):
                    return z.read(fname).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    [Error decoding/extracting subtitle]: {e}", file=sys.stderr)

    return None


def fetch_english_srt(imdb_id=None, title=None):
    """Attempt to find and download English SRT text for a movie."""
    page_urls = []
    if imdb_id:
        page_urls = search_yts_subs_by_imdb(imdb_id)
    if not page_urls and title:
        page_urls = search_yts_subs_by_title(title)

    for page_url in page_urls:
        srt_text = download_srt_from_yts_page(page_url)
        if srt_text and len(srt_text.strip()) > 50:
            return srt_text

    return None


def update_cache_for_file(file_path):
    """Update cache entry for file_path so sub='YES' and bmp='NO'."""
    if not os.path.isfile(CACHE_PATH):
        return
    try:
        st = os.stat(file_path)
        cache_key = f"{file_path}|{st.st_mtime}|{st.st_size}"
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if cache_key in cache:
            cache[cache_key]["sub"] = "YES"
            cache[cache_key]["bmp"] = "NO"
            cache[cache_key]["srt"] = "YES"
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
    except Exception:
        pass


def find_candidate_movies(movies_dir, mode="all_bmp"):
    """
    Find movie files matching criteria:
      - mode='all_bmp': only movies with bitmap DVD subtitles and no text subtitles
      - mode='all_missing': movies with no subtitles at all
    """
    candidates = []
    if not os.path.isfile(CACHE_PATH):
        print(f"Notice: Cache file '{CACHE_PATH}' not found. Run check_database_health.py first to scan library.", file=sys.stderr)
        return candidates

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)

    for key, info in cache.items():
        file_path = key.split("|")[0]
        if not os.path.isfile(file_path):
            continue
        if not file_path.startswith(movies_dir):
            continue

        base, _ = os.path.splitext(file_path)
        # Check if external .srt already exists on disk
        has_ext_srt = any(os.path.isfile(base + ext) for ext in (".srt", ".en.srt", ".eng.srt", ".English.srt"))
        if has_ext_srt:
            continue

        bmp_val = info.get("bmp", "NO")
        sub_val = info.get("sub", "NO")
        jf_val = info.get("jellyfin", "-")

        if mode == "all_bmp" and (bmp_val == "YES" or sub_val == "Bitmap" or jf_val == "TRANSCODE"):
            candidates.append(file_path)
        elif mode == "all_missing" and (sub_val in ("NO", "None", "-") and bmp_val != "YES"):
            candidates.append(file_path)

    candidates.sort(key=lambda p: os.path.basename(p))
    return candidates


def process_single_movie(file_path, imdb_mapping, dry_run=False, force=False):
    """
    Fetch and write .en.srt for a single movie file.
    Returns True if downloaded / found, False otherwise.
    """
    base, _ = os.path.splitext(file_path)
    target_srt = f"{base}.en.srt"

    if os.path.isfile(target_srt) and not force:
        print(f"  [SKIPPED] Subtitle file already exists: {os.path.basename(target_srt)}")
        return True

    imdb_id, title = match_movie_imdb(file_path, imdb_mapping)
    id_str = f"({imdb_id})" if imdb_id else "(no IMDb ID found, searching by title)"
    print(f"  Searching subtitles for: {os.path.basename(file_path)} {id_str}...")

    srt_text = fetch_english_srt(imdb_id=imdb_id, title=title)
    if not srt_text:
        print(f"  [-] No matching English subtitles found online.")
        return False

    line_count = len(srt_text.splitlines())
    if dry_run:
        print(f"  [DRY-RUN] Found subtitle ({line_count} lines) -> would save to {os.path.basename(target_srt)}")
        return True

    try:
        with open(target_srt, "w", encoding="utf-8") as f:
            f.write(srt_text)
        print(f"  [+] SAVED: {os.path.basename(target_srt)} ({line_count} lines)")
        update_cache_for_file(file_path)
        return True
    except Exception as e:
        print(f"  [!] Error saving subtitle: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch external English .srt subtitles for movies with bitmap-only DVD subtitles or missing subtitles."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Movie title, filename, or file path (e.g. 'Fitzcarraldo' or '/media/daveg/Lib/Movies/Fitzcarraldo (1982).m4v')"
    )
    parser.add_argument(
        "--all-bmp",
        action="store_true",
        help="Fetch .en.srt for all library movies that currently have ONLY bitmap DVD subtitles."
    )
    parser.add_argument(
        "--all-missing",
        action="store_true",
        help="Fetch .en.srt for all library movies that currently have NO subtitles."
    )
    parser.add_argument(
        "--movies-dir",
        default=DEFAULT_MOVIES_DIR,
        help=f"Path to movies directory (default: {DEFAULT_MOVIES_DIR})"
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Path to IMDB_Films.db database (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of movies to process in batch mode."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .en.srt files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and preview without saving any files to disk."
    )

    args = parser.parse_args()

    if not args.query and not args.all_bmp and not args.all_missing:
        parser.print_help()
        sys.exit(1)

    print("Loading IMDb mapping from database...")
    imdb_mapping = get_imdb_mapping(args.db)
    print(f"Loaded {len(imdb_mapping):,} title/year entries from DB.")

    if args.query:
        # Single movie lookup
        target_path = None
        if os.path.isfile(args.query):
            target_path = os.path.abspath(args.query)
        else:
            # Search in movies_dir
            for root, _, files in os.walk(args.movies_dir):
                for f in files:
                    if args.query.lower() in f.lower():
                        _, ext = os.path.splitext(f)
                        if ext.lower() in VIDEO_EXTENSIONS:
                            target_path = os.path.join(root, f)
                            break
                if target_path:
                    break

        if not target_path:
            print(f"Error: Could not locate movie file matching '{args.query}' in '{args.movies_dir}'", file=sys.stderr)
            sys.exit(1)

        print(f"\nProcessing movie: {target_path}")
        success = process_single_movie(target_path, imdb_mapping, dry_run=args.dry_run, force=args.force)
        sys.exit(0 if success else 1)

    # Batch mode
    mode = "all_bmp" if args.all_bmp else "all_missing"
    mode_desc = "ONLY bitmap DVD subtitles (BMP=YES)" if mode == "all_bmp" else "NO subtitles at all (Sub=NO)"
    print(f"\nScanning library cache for movies with {mode_desc}...")

    candidates = find_candidate_movies(args.movies_dir, mode=mode)
    print(f"Found {len(candidates):,} candidate movies needing .en.srt subtitles.")

    if args.limit and len(candidates) > args.limit:
        candidates = candidates[:args.limit]
        print(f"Applying limit: processing first {len(candidates)} movies.")

    if not candidates:
        print("Nothing to do!")
        sys.exit(0)

    success_count = 0
    fail_count = 0

    print("=" * 80)
    for i, file_path in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {os.path.basename(file_path)}")
        ok = process_single_movie(file_path, imdb_mapping, dry_run=args.dry_run, force=args.force)
        if ok:
            success_count += 1
        else:
            fail_count += 1
        # Gentle rate limit delay between requests to be polite to subtitle servers
        time.sleep(1.0)

    print("=" * 80)
    print(f"Summary: {success_count} succeeded, {fail_count} failed / not found out of {len(candidates)} total.")


if __name__ == "__main__":
    main()

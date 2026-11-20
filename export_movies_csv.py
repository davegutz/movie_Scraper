#!/usr/bin/env python3
"""
export_movies_csv.py

Exports My_Films database table to a CSV file ('movies.csv') in movie collection format
(leading articles moved after a comma, e.g. "Godfather, The", "Beautiful Mind, A"),
alphabetized by the formatted title.
Optionally stages, commits, and pushes to GitHub with --push or -p.
"""

import argparse
import csv
import os
import re
import sqlite3
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_LOCATIONS = [
    "/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db",
    os.path.join(SCRIPT_DIR, "IMDB_Films.db")
]
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "movies.csv")

ARTICLE_PATTERN = re.compile(r'^(the|a|an|le|la|les|il|lo|gli|el|los|las|der|das)\s+(.*)$', re.IGNORECASE)
L_APOSTROPHE_PATTERN = re.compile(r"^(l\')\s*(.*)$", re.IGNORECASE)


def move_article_to_end(title):
    """
    If title starts with an article ('The', 'A', 'An', 'Le', 'La', 'Il', 'El', etc.),
    move the article to the end after a comma for alphabetical indexing in movie collection format.
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


def get_db_path():
    for p in DEFAULT_DB_LOCATIONS:
        if os.path.exists(p):
            return p
    return os.path.join(SCRIPT_DIR, "IMDB_Films.db")


def parse_dvd_filter(dvd):
    """
    Parse dvd parameter into (values_list, include_null_zero_bool).
    Returns None if dvd is None or 'all'.
    """
    if dvd is None:
        return None

    if isinstance(dvd, str):
        val_str = dvd.strip().lower()
        if not val_str or val_str == 'all':
            return None
        if val_str in ('owned', 'owned_only', 'any'):
            return ([1, 2, 3, 4], False)
        if val_str in ('dvd', 'dvd_only'):
            return ([1], False)
        if val_str in ('screencast', 'screencast_only'):
            return ([2, 4], False)
        if val_str in ('both', 'both_only'):
            return ([3], False)
        if val_str in ('none', 'not_owned', 'not_owned_only', 'unowned'):
            return ([0], True)

        raw_parts = [p.strip() for p in dvd.split(',') if p.strip()]
        vals = []
        include_zero = False
        for p in raw_parts:
            try:
                num = int(p)
                vals.append(num)
                if num == 0:
                    include_zero = True
            except ValueError:
                vals.append(p)
        return (vals, include_zero)

    if isinstance(dvd, (int, float)):
        num = int(dvd)
        return ([num], num == 0)

    if isinstance(dvd, (list, tuple, set)):
        vals = []
        include_zero = False
        for item in dvd:
            try:
                num = int(item)
                vals.append(num)
                if num == 0:
                    include_zero = True
            except (ValueError, TypeError):
                vals.append(item)
        return (vals, include_zero)

    return ([dvd], False)


def export_csv(db_path=None, output_path=None, dvd=None, sort_by="title", order=None):
    db_path = db_path or get_db_path()
    output_path = output_path or OUTPUT_CSV

    if not os.path.exists(db_path):
        print(f"[!] Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(My_Films);")
    cols = [c[1] for c in cur.fetchall()]
    has_added = "ADDED" in cols
    has_watched = "WATCHED" in cols

    cols_select = "IMDB_ID, title, year, rating, my_rating, director, actors, generes, summary, cover, DVD, runtime, certification"
    cols_select += ", ADDED" if has_added else ", NULL"
    cols_select += ", WATCHED" if has_watched else ", NULL"

    # WHERE clause for DVD filter
    where_parts = []
    params = []
    dvd_spec = parse_dvd_filter(dvd)
    if dvd_spec is not None:
        vals, include_null_zero = dvd_spec
        non_zero_vals = [v for v in vals if v != 0 and v != '0']
        clause_items = []
        if non_zero_vals:
            placeholders = ", ".join("?" for _ in non_zero_vals)
            clause_items.append(f"DVD IN ({placeholders})")
            params.extend(non_zero_vals)
            clause_items.append(f"CAST(DVD AS INTEGER) IN ({placeholders})")
            params.extend(non_zero_vals)
        if include_null_zero:
            clause_items.append("DVD = 0")
            clause_items.append("DVD = '0'")
            clause_items.append("DVD = ''")
            clause_items.append("DVD IS NULL")
            clause_items.append("CAST(DVD AS INTEGER) = 0")

        if clause_items:
            combined = " OR ".join(clause_items)
            if not include_null_zero:
                where_parts.append(f"({combined}) AND DVD IS NOT NULL AND DVD != ''")
            else:
                where_parts.append(f"({combined})")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    cur.execute(f"""
        SELECT {cols_select} 
        FROM My_Films
        {where_sql};
    """, params)
    rows = cur.fetchall()

    movies = []
    for r in rows:
        imdb_id, raw_title, year, rating, my_rating, director, actors, genres, summary, cover, dvd_val, runtime, cert, added, watched = r
        clean_title = (raw_title or "").strip()
        formatted_title = move_article_to_end(clean_title)
        movies.append({
            "id": imdb_id if imdb_id is not None else "",
            "title": formatted_title,
            "year": year if (year and year > 1890) else "",
            "rating": rating if rating is not None else "",
            "my_rating": my_rating if my_rating is not None else "",
            "director": (director or "").strip(),
            "actors": (actors or "").strip(),
            "genres": (genres or "").strip(),
            "summary": (summary or "").strip(),
            "cover": (cover or "").strip(),
            "dvd": dvd_val if dvd_val is not None else "",
            "runtime": (runtime or "").strip(),
            "cert": (cert or "").strip(),
            "added": (added or "").strip() if added else "",
            "watched": (watched or "").strip() if watched else ""
        })

    # Sort movies
    norm_sort = str(sort_by or 'title').strip().lower().replace('-', '_')
    if order is not None:
        is_desc = str(order).strip().lower() == 'desc'
    else:
        is_desc = norm_sort in ('my_rating', 'my_rate', 'rating', 'imdb', 'year', 'added', 'watched')

    def to_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return float('-inf') if is_desc else float('inf')

    if norm_sort in ('my_rating', 'my_rate', 'rating_mine', 'myrate'):
        movies.sort(key=lambda m: (-to_float(m["my_rating"]) if is_desc else to_float(m["my_rating"]), m["title"].lower()))
    elif norm_sort in ('rating', 'imdb'):
        movies.sort(key=lambda m: (-to_float(m["rating"]) if is_desc else to_float(m["rating"]), m["title"].lower()))
    elif norm_sort in ('year', 'release_year'):
        movies.sort(key=lambda m: (-int(m["year"]) if is_desc and str(m["year"]).isdigit() else (int(m["year"]) if str(m["year"]).isdigit() else 9999), m["title"].lower()))
    elif norm_sort in ('dvd', 'dvd_number'):
        movies.sort(key=lambda m: (-to_float(m["dvd"]) if is_desc else to_float(m["dvd"]), m["title"].lower()))
    else:
        # Default: Alphabetize by movie collection format title (case-insensitive)
        movies.sort(
            key=lambda m: (m["title"].lower(), int(m["year"]) if str(m["year"]).isdigit() else 0),
            reverse=is_desc if order is not None else False
        )

    fieldnames = [
        "id", "title", "year", "rating", "my_rating", "director",
        "actors", "genres", "summary", "cover", "dvd", "runtime", "cert"
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for movie in movies:
            writer.writerow(movie)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    info_parts = []
    if dvd_spec is not None:
        info_parts.append(f"DVD: {dvd}")
    if norm_sort not in ('title', ''):
        info_parts.append(f"Sorted by: {sort_by}")
    info_str = f" ({', '.join(info_parts)})" if info_parts else ""
    print(f"  [✓] Exported {len(movies):,} movies{info_str} to: {output_path} ({size_mb:.2f} MB)")
    return len(movies), output_path


def git_commit_and_push(target_file):
    print(f"\nStaging and pushing {os.path.basename(target_file)} to GitHub...")
    repo_dir = SCRIPT_DIR

    # Check git status for changes
    status_cmd = ["git", "status", "--porcelain", os.path.basename(target_file)]
    res = subprocess.run(status_cmd, cwd=repo_dir, capture_output=True, text=True)
    if not res.stdout.strip():
        print(f"  [i] No changes detected in {os.path.basename(target_file)}. Already up to date on git.")
        return True

    # Git add
    add_cmd = ["git", "add", os.path.basename(target_file)]
    res_add = subprocess.run(add_cmd, cwd=repo_dir, capture_output=True, text=True)
    if res_add.returncode != 0:
        print(f"[!] git add failed: {res_add.stderr}", file=sys.stderr)
        return False

    # Git commit
    commit_cmd = ["git", "commit", "-m", "Update movies database CSV"]
    res_commit = subprocess.run(commit_cmd, cwd=repo_dir, capture_output=True, text=True)
    print(res_commit.stdout.strip())
    if res_commit.returncode != 0:
        print(f"[!] git commit failed: {res_commit.stderr}", file=sys.stderr)
        return False

    # Git push
    push_cmd = ["git", "push"]
    print("Running 'git push'...")
    res_push = subprocess.run(push_cmd, cwd=repo_dir, capture_output=True, text=True)
    print(res_push.stdout.strip())
    if res_push.stderr:
        print(res_push.stderr.strip())

    if res_push.returncode == 0:
        print(f"  [✓] Successfully pushed {os.path.basename(target_file)} to GitHub!")
        return True
    else:
        print(f"[!] git push failed with exit code {res_push.returncode}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Export My_Films database table to CSV in movie collection format (articles moved after comma), alphabetized."
    )
    parser.add_argument("--db", default=None, help="Path to SQLite database file.")
    parser.add_argument("--output", "-o", default=None, help="Output CSV path (default: movies.csv).")
    parser.add_argument("--dvd", "--dvd-number", dest="dvd", default=None,
                        help="Filter by DVD number (e.g. 1, 2, '1,2', or 'owned'). Default: all.")
    parser.add_argument("--sort", "--sort-by", dest="sort_by", default="title",
                        choices=["title", "my_rating", "rating", "year", "dvd"],
                        help="Sort field (default: title).")
    parser.add_argument("--sort-my-rating", dest="sort_my_rating", action="store_true",
                        help="Shortcut to sort by my_rating descending.")
    parser.add_argument("--order", choices=["asc", "desc"], default=None,
                        help="Sort direction (asc or desc).")
    parser.add_argument("--push", "-p", action="store_true", help="Automatically commit and push movies.csv to GitHub.")
    args = parser.parse_args()

    sort_field = "my_rating" if args.sort_my_rating else args.sort_by
    count, out_file = export_csv(
        db_path=args.db,
        output_path=args.output,
        dvd=args.dvd,
        sort_by=sort_field,
        order=args.order
    )
    if args.push:
        git_commit_and_push(out_file)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
export_movies_json.py

Exports My_Films database table to a compact JSON file ('movies.json')
that can be committed to GitHub and fetched live by the movie search web app.
Supports filtering by DVD number and sorting by my_rating (or title, year, rating, etc.).
Optionally stages, commits, and pushes to GitHub with --push or -p.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_LOCATIONS = [
    "/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db",
    os.path.join(SCRIPT_DIR, "IMDB_Films.db")
]
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "movies.json")


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


def build_order_clause(sort_by="title", order=None):
    """
    Build SQL ORDER BY clause given sort_by field and order ('asc'/'desc').
    """
    s = str(sort_by or 'title').strip().lower().replace('-', '_')
    if order is not None:
        order_dir = str(order).strip().upper()
        if order_dir not in ('ASC', 'DESC'):
            order_dir = 'ASC'
    else:
        order_dir = None

    if s in ('my_rating', 'my_rate', 'rating_mine', 'myrate'):
        direction = order_dir if order_dir else 'DESC'
        return f"CASE WHEN my_rating IS NULL OR my_rating = '' THEN 1 ELSE 0 END, my_rating {direction}, title COLLATE NOCASE ASC"
    elif s in ('rating', 'imdb_rating', 'imdb'):
        direction = order_dir if order_dir else 'DESC'
        return f"CASE WHEN rating IS NULL OR rating = '' THEN 1 ELSE 0 END, rating {direction}, title COLLATE NOCASE ASC"
    elif s in ('year', 'release_year'):
        direction = order_dir if order_dir else 'DESC'
        return f"CASE WHEN year IS NULL OR year = '' THEN 1 ELSE 0 END, year {direction}, title COLLATE NOCASE ASC"
    elif s in ('added', 'date_added'):
        direction = order_dir if order_dir else 'DESC'
        return f"CASE WHEN ADDED IS NULL OR ADDED = '' THEN 1 ELSE 0 END, ADDED {direction}, title COLLATE NOCASE ASC"
    elif s in ('watched', 'date_watched'):
        direction = order_dir if order_dir else 'DESC'
        return f"CASE WHEN WATCHED IS NULL OR WATCHED = '' THEN 1 ELSE 0 END, WATCHED {direction}, title COLLATE NOCASE ASC"
    elif s in ('dvd', 'dvd_number'):
        direction = order_dir if order_dir else 'ASC'
        return f"CASE WHEN DVD IS NULL OR DVD = '' THEN 1 ELSE 0 END, CAST(DVD AS INTEGER) {direction}, title COLLATE NOCASE ASC"
    else:
        direction = order_dir if order_dir else 'ASC'
        return f"title COLLATE NOCASE {direction}"


def export_json(db_path=None, output_path=None, dvd=None, sort_by="title", order=None):
    db_path = db_path or get_db_path()
    output_path = output_path or OUTPUT_JSON

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

    # Check if requested sort column exists in database schema
    norm_sort = str(sort_by or 'title').strip().lower().replace('-', '_')
    if norm_sort in ('added', 'date_added') and not has_added:
        sort_by = 'title'
    elif norm_sort in ('watched', 'date_watched') and not has_watched:
        sort_by = 'title'

    order_sql = build_order_clause(sort_by=sort_by, order=order)

    query = f"""
        SELECT {cols_select} 
        FROM My_Films
        {where_sql}
        ORDER BY {order_sql};
    """
    cur.execute(query, params)
    rows = cur.fetchall()

    movies = []
    for r in rows:
        imdb_id, title, year, rating, my_rating, director, actors, genres, summary, cover, dvd_val, runtime, cert, added, watched = r
        movies.append({
            "id": imdb_id,
            "title": (title or "").strip(),
            "year": year if (year and year > 1890) else None,
            "rating": rating,
            "my_rating": my_rating,
            "director": (director or "").strip(),
            "actors": (actors or "").strip(),
            "genres": (genres or "").strip(),
            "summary": (summary or "").strip(),
            "cover": (cover or "").strip(),
            "dvd": dvd_val,
            "runtime": (runtime or "").strip(),
            "cert": (cert or "").strip(),
            "added": (added or "").strip(),
            "watched": (watched or "").strip()
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(movies, f, separators=(',', ':'), ensure_ascii=False)

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
    add_cmd = ["git", "add", os.path.basename(target_file), "movie_search_app.html"]
    res_add = subprocess.run(add_cmd, cwd=repo_dir, capture_output=True, text=True)
    if res_add.returncode != 0:
        print(f"[!] git add failed: {res_add.stderr}", file=sys.stderr)
        return False

    # Git commit
    commit_cmd = ["git", "commit", "-m", "Update movies database JSON for web app"]
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
        print("  [✓] Successfully pushed movies.json to GitHub!")
        return True
    else:
        print(f"[!] git push failed with exit code {res_push.returncode}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Export My_Films database table to JSON for web app.")
    parser.add_argument("--db", default=None, help="Path to SQLite database file.")
    parser.add_argument("--output", "-o", default=None, help="Output JSON path (default: movies.json).")
    parser.add_argument("--dvd", "--dvd-number", dest="dvd", default=None,
                        help="Filter by DVD number (e.g. 1, 2, '1,2', or 'owned'). Default: all.")
    parser.add_argument("--sort", "--sort-by", dest="sort_by", default="title",
                        choices=["title", "my_rating", "rating", "year", "added", "watched", "dvd"],
                        help="Sort field (default: title).")
    parser.add_argument("--sort-my-rating", dest="sort_my_rating", action="store_true",
                        help="Shortcut to sort by my_rating descending.")
    parser.add_argument("--order", choices=["asc", "desc"], default=None,
                        help="Sort direction (asc or desc).")
    parser.add_argument("--push", "-p", action="store_true", help="Automatically commit and push movies.json to GitHub.")
    args = parser.parse_args()

    sort_field = "my_rating" if args.sort_my_rating else args.sort_by
    count, out_file = export_json(
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

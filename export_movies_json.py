#!/usr/bin/env python3
"""
export_movies_json.py

Exports My_Films database table to a compact JSON file ('movies.json')
that can be committed to GitHub and fetched live by the movie search web app.
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


def export_json(db_path=None, output_path=None):
    db_path = db_path or get_db_path()
    output_path = output_path or OUTPUT_JSON

    if not os.path.exists(db_path):
        print(f"[!] Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT IMDB_ID, title, year, rating, my_rating, director, actors, generes, summary, cover, DVD, runtime, certification 
        FROM My_Films
        ORDER BY title COLLATE NOCASE ASC;
    """)
    rows = cur.fetchall()

    movies = []
    for r in rows:
        imdb_id, title, year, rating, my_rating, director, actors, genres, summary, cover, dvd, runtime, cert = r
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
            "dvd": dvd,
            "runtime": (runtime or "").strip(),
            "cert": (cert or "").strip()
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(movies, f, separators=(',', ':'), ensure_ascii=False)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  [✓] Exported {len(movies):,} movies to: {output_path} ({size_mb:.2f} MB)")
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
    parser.add_argument("--push", "-p", action="store_true", help="Automatically commit and push movies.json to GitHub.")
    args = parser.parse_args()

    count, out_file = export_json(args.db, args.output)
    if args.push:
        git_commit_and_push(out_file)


if __name__ == "__main__":
    main()

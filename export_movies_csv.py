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


def export_csv(db_path=None, output_path=None):
    db_path = db_path or get_db_path()
    output_path = output_path or OUTPUT_CSV

    if not os.path.exists(db_path):
        print(f"[!] Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT IMDB_ID, title, year, rating, my_rating, director, actors, generes, summary, cover, DVD, runtime, certification 
        FROM My_Films;
    """)
    rows = cur.fetchall()

    movies = []
    for r in rows:
        imdb_id, raw_title, year, rating, my_rating, director, actors, genres, summary, cover, dvd, runtime, cert = r
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
            "dvd": dvd if dvd is not None else "",
            "runtime": (runtime or "").strip(),
            "cert": (cert or "").strip()
        })

    # Alphabetize by movie collection format title (case-insensitive)
    movies.sort(key=lambda m: (m["title"].lower(), int(m["year"]) if str(m["year"]).isdigit() else 0))

    fieldnames = [
        "id", "title", "year", "rating", "my_rating", "director",
        "actors", "genres", "summary", "cover", "dvd", "runtime", "cert"
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for movie in movies:
            writer.writerow(movie)

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
    parser.add_argument("--push", "-p", action="store_true", help="Automatically commit and push movies.csv to GitHub.")
    args = parser.parse_args()

    count, out_file = export_csv(args.db, args.output)
    if args.push:
        git_commit_and_push(out_file)


if __name__ == "__main__":
    main()

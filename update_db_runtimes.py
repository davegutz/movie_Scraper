#!/usr/bin/env python3
"""
update_db_runtimes.py

Update IMDB_Films.db runtime values with actual probed video file runtimes.
Focuses on movies with duration discrepancies or missing runtimes, while
preserving complete-film runtimes for split/partial rips (e.g. Disc 1, Part 1, truncated).
"""

import os
import sys
import sqlite3
import argparse

DEFAULT_DB = "/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db"
DEFAULT_MOVIES_DIR = "/media/daveg/Lib/Movies"

# Specific verified updates for movies with incorrect/corrupt runtimes in the DB:
# (imdb_id: (new_runtime_min, description))
VERIFIED_RUNTIME_UPDATES = {
    18423288: (134, "Twelve Years A Slave (2013) - DB was 9m -> correct 134m (02:14)"),
    24736286: (133, "The Magnificent Seven (2016) - DB was 14m -> correct 133m (02:13)"),
    4212300:  (119, "Birdman: Or (The Unexpected Virtue of Ignorance) (2014) - DB was 34m -> correct 119m (01:59)"),
    34589645: (132, "Emilia Perez (2024) - DB was 26m -> correct 132m (02:12)"),
    8335218:  (115, "No Man's Land (2020) - DB was 45m -> correct 115m (01:55)"),
    10366460: (128, "CODA (2022) - DB was 111m -> correct 128m (02:08)"),
    246578:   (134, "Donnie Darko (2001) - DB was 113m -> correct 134m (02:14, Director's Cut)"),
    5153288:  (87,  "Backstabbing for Beginners (2018) - DB was 108m -> correct 87m (01:27)"),
    50379:    (110, "A Farewell to Arms (1957) - DB was 152m -> correct 110m (01:50)"),
    348150:   (112, "Superman Returns (2006) - DB was 154m -> correct 112m (01:52)"),
    460522:   (24,  "An Occurrence at Owl Creek Bridge (2005) - DB was 51m -> set to 24m (00:24)"),
    14718126: (106, "The Pilot (2022) - DB was 74m -> correct 106m (01:46)"),
    9742794:  (92,  "The Vault (2021) - DB was 118m -> correct 92m (01:32)"),
    5761544:  (125, "Kandahar (2023) - DB was empty -> correct 125m (02:05)"),
    # Blank/missing runtimes in DB for matched films
    21191806: (120, "Back in Action (2025) - DB was empty -> probed 120m (02:00)"),
    1799349:  (53,  "Birds of the Gods (2011) - DB was empty -> probed 53m (00:53)"),
    30988739: (100, "Black Bag (2025) - DB was empty -> probed 100m (01:40)"),
    13452446: (120, "Damsel (2024) - DB was empty -> probed 120m (02:00)"),
    4257072:  (57,  "El Capitan (1978) - DB was empty -> probed 57m (00:57)"),
    12711948: (106, "Every Breath You Take (2021) - DB was empty -> probed 106m (01:46)"),
    1571403:  (146, "Harry Potter and the Deathly Hallows: Part I (2010) - DB was empty -> probed 146m (02:26)"),
    1680310:  (130, "Harry Potter and the Deathly Hallows: Part II (2011) - DB was empty -> probed 130m (02:10)"),
    29741175: (122, "Le fabuleux destin d'Amélie Poulain (2001) - DB was empty -> probed 122m (02:02)"),
    12747748: (150, "Leave the World Behind (2023) - DB was empty -> probed 150m (02:30)"),
    7047254:  (119, "My All American (2015) - DB was empty -> probed 119m (01:59)"),
    120780:   (120, "Out of Sight (1998) - DB was empty -> probed 120m (02:00)"),
    9731386:  (122, "Rogue Agent (2022) - DB was empty -> probed 122m (02:02)"),
    29895189: (134, "Rogue One: A Star Wars Story (2016) - DB was empty -> probed 134m (02:14)"),
    28082769: (97,  "September 5 (2024) - DB was empty -> probed 97m (01:37)"),
    2463208:  (120, "The Adam Project (2022) - DB was empty -> probed 120m (02:00)"),
    899043:   (125, "The Amateur (2025) - DB was empty -> probed 125m (02:05)"),
    1649418:  (135, "The Gray Man (2022) - DB was empty -> probed 135m (02:15)"),
    1094925:  (138, "The Lives of Others (2007) - DB was empty -> probed 138m (02:18)"),
    6968614:  (120, "The Mother (2023) - DB was empty -> probed 120m (02:00)"),
    10518758: (114, "X-Men: Dark Phoenix (2019) - DB was empty -> probed 114m (01:54)"),
    594963:   (134, "X2: X-Men United (2003) - DB was empty -> probed 134m (02:14)"),
}


def update_database_runtimes(db_path=DEFAULT_DB, dry_run=False):
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    updated_count = 0
    unchanged_count = 0

    print(f"{'[DRY RUN] ' if dry_run else ''}Updating database runtimes in: {db_path}\n")

    for imdb_id, (new_rt, note) in sorted(VERIFIED_RUNTIME_UPDATES.items(), key=lambda x: x[0]):
        cur.execute("SELECT title, year, runtime FROM My_Films WHERE IMDB_ID = ?", (imdb_id,))
        row = cur.fetchone()
        if not row:
            print(f"  [!] IMDB_ID {imdb_id} not found in database! ({note})")
            continue

        title, year, old_rt = row
        old_rt_str = str(old_rt or '').strip()
        new_rt_str = str(new_rt).strip()

        if old_rt_str == new_rt_str:
            unchanged_count += 1
            continue

        print(f"  [{'PLAN' if dry_run else 'UPDATE'}] ID {imdb_id:<8} | {title} ({year})")
        print(f"           Old runtime: '{old_rt_str}' -> New runtime: '{new_rt_str}'")
        print(f"           Details: {note}")

        if not dry_run:
            cur.execute("UPDATE My_Films SET runtime = ? WHERE IMDB_ID = ?", (new_rt_str, imdb_id))
            updated_count += 1
        else:
            updated_count += 1

    if not dry_run:
        conn.commit()
        print(f"\nSuccessfully committed {updated_count} runtime update(s) to {db_path}.")
    else:
        print(f"\nDry run complete: {updated_count} record(s) would be updated, {unchanged_count} unchanged.")

    conn.close()
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Update film runtimes in IMDB_Films.db")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"Path to IMDB_Films.db (default: {DEFAULT_DB})")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying the database")
    args = parser.parse_args()

    success = update_database_runtimes(db_path=args.db, dry_run=args.dry_run)
    sys.exit(0 if success else 1)

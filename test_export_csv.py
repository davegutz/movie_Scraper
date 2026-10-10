"""
Unit tests for export_movies_csv.py and CSV export button in GUI_sqlite_scrape.py.
"""

import csv
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import export_movies_csv

# Mock Tkinter to allow importing GUI_sqlite_scrape
with patch('tkinter.Tk'):
    import GUI_sqlite_scrape


class TestExportMoviesCSV(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_films.db")
        self.csv_path = os.path.join(self.tmp_dir.name, "test_movies.csv")

        # Create temporary database with test movies
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE My_Films (
                IMDB_ID integer PRIMARY KEY,
                title text,
                year integer,
                rating real,
                my_rating real,
                director text,
                actors text,
                generes text,
                summary text,
                cover text,
                WATCHED text,
                DVD integer,
                runtime text,
                certification text,
                ADDED text
            )
        """)
        # Insert out of alphabetical order
        cur.executemany("""
            INSERT INTO My_Films (IMDB_ID, title, year, rating, my_rating, director, actors, generes, summary, cover, DVD, runtime, certification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (2, "Zodiac", 2007, 7.7, 8.5, "David Fincher", "Jake Gyllenhaal", "Crime, Drama", "A cartoonist tracks a killer", "http://cover2", 1, "157", "R"),
            (1, "Alien", 1979, 8.5, 9.0, "Ridley Scott", "Sigourney Weaver", "Horror, Sci-Fi", "In space no one can hear you scream", "http://cover1", 1, "117", "R"),
            (3, "Casablanca", 1942, 8.5, 8.5, "Michael Curtiz", "Humphrey Bogart", "Drama, Romance", "Here's looking at you kid", "http://cover3", 0, "102", "PG"),
        ])
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_export_csv_alphabetical_order(self):
        """Verify export_csv outputs in alphabetical order by title."""
        count, out_file = export_movies_csv.export_csv(db_path=self.db_path, output_path=self.csv_path)
        self.assertEqual(count, 3)
        self.assertTrue(os.path.isfile(out_file))

        with open(out_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 3)
        # Verify alphabetical order: Alien, Casablanca, Zodiac
        self.assertEqual(rows[0]["title"], "Alien")
        self.assertEqual(rows[0]["year"], "1979")
        self.assertEqual(rows[0]["director"], "Ridley Scott")

        self.assertEqual(rows[1]["title"], "Casablanca")
        self.assertEqual(rows[1]["year"], "1942")

        self.assertEqual(rows[2]["title"], "Zodiac")
        self.assertEqual(rows[2]["year"], "2007")

    def test_export_csv_columns_match_json_structure(self):
        """Verify CSV columns match the fields exported in JSON."""
        expected_fields = [
            "id", "title", "year", "rating", "my_rating", "director",
            "actors", "genres", "summary", "cover", "dvd", "runtime", "cert"
        ]
        export_movies_csv.export_csv(db_path=self.db_path, output_path=self.csv_path)

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)

        self.assertEqual(header, expected_fields)

    def test_gui_export_movies_to_csv_launches(self):
        """Test export_movies_to_csv launches Toplevel window and worker thread."""
        app = MagicMock()
        app.root = MagicMock()
        app.db_path = self.db_path

        with patch('GUI_sqlite_scrape.tk.Toplevel') as mock_top, \
             patch('GUI_sqlite_scrape.scrolledtext.ScrolledText') as mock_st, \
             patch('threading.Thread') as mock_thread:

            mock_thread.return_value = MagicMock()
            GUI_sqlite_scrape.IMDBdataBase.export_movies_to_csv(app)

            mock_top.assert_called_once_with(app.root)
            mock_top.return_value.title.assert_called_with("Export Movies.csv")
            mock_thread.return_value.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()

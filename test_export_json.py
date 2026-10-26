"""
Unit tests for export_movies_json.py and export_movies_to_web in GUI_sqlite_scrape.py.
"""

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import export_movies_json

# Mock Tkinter to allow importing GUI_sqlite_scrape
with patch('tkinter.Tk'):
    import GUI_sqlite_scrape


class TestExportMoviesJSON(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_films.db")
        self.json_path = os.path.join(self.tmp_dir.name, "test_movies.json")

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
        cur.executemany("""
            INSERT INTO My_Films (IMDB_ID, title, year, rating, my_rating, director, actors, generes, summary, cover, WATCHED, DVD, runtime, certification, ADDED)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (2, "The Godfather", 1972, 9.2, 9.5, "Francis Ford Coppola", "Marlon Brando", "Crime, Drama", "The aging patriarch...", "http://cover2", "2021-10-27", 1, "175", "R", "2024-07-26"),
            (1, "Alien", 1979, 8.5, 9.0, "Ridley Scott", "Sigourney Weaver", "Horror, Sci-Fi", "In space...", "http://cover1", " ", 1, "117", "R", "2024-07-26"),
            (3, "A Beautiful Mind", 2001, 8.2, 8.5, "Ron Howard", "Russell Crowe", "Biography, Drama", "Mathematical genius...", "http://cover3", None, 0, "135", "PG-13", None),
        ])
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_export_json_fields_and_date_handling(self):
        """Verify export_json exports all expected fields including added and watched."""
        count, out_file = export_movies_json.export_json(db_path=self.db_path, output_path=self.json_path)
        self.assertEqual(count, 3)
        self.assertTrue(os.path.isfile(out_file))

        with open(out_file, "r", encoding="utf-8") as f:
            movies = json.load(f)

        self.assertEqual(len(movies), 3)

        # Movies sorted by title COLLATE NOCASE ASC: A Beautiful Mind -> Alien -> The Godfather
        m_mind = movies[0]
        self.assertEqual(m_mind["title"], "A Beautiful Mind")
        self.assertEqual(m_mind["added"], "")
        self.assertEqual(m_mind["watched"], "")

        m_alien = movies[1]
        self.assertEqual(m_alien["title"], "Alien")
        self.assertEqual(m_alien["added"], "2024-07-26")
        self.assertEqual(m_alien["watched"], "")  # Stripped whitespace ' '

        m_godfather = movies[2]
        self.assertEqual(m_godfather["title"], "The Godfather")
        self.assertEqual(m_godfather["added"], "2024-07-26")
        self.assertEqual(m_godfather["watched"], "2021-10-27")

        # Verify all expected keys are present
        expected_keys = {
            "id", "title", "year", "rating", "my_rating", "director",
            "actors", "genres", "summary", "cover", "dvd", "runtime",
            "cert", "added", "watched"
        }
        for m in movies:
            self.assertEqual(set(m.keys()), expected_keys)

    def test_export_json_missing_columns_fallback(self):
        """Verify export_json works gracefully if ADDED or WATCHED columns are absent."""
        alt_db_path = os.path.join(self.tmp_dir.name, "legacy_films.db")
        conn = sqlite3.connect(alt_db_path)
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
                DVD integer,
                runtime text,
                certification text
            )
        """)
        cur.execute("""
            INSERT INTO My_Films (IMDB_ID, title, year, rating, my_rating, director, actors, generes, summary, cover, DVD, runtime, certification)
            VALUES (1, "Casablanca", 1942, 8.5, 8.5, "Michael Curtiz", "Humphrey Bogart", "Drama", "Story", "cover", 1, "102", "PG")
        """)
        conn.commit()
        conn.close()

        count, out_file = export_movies_json.export_json(db_path=alt_db_path, output_path=self.json_path)
        self.assertEqual(count, 1)

        with open(out_file, "r", encoding="utf-8") as f:
            movies = json.load(f)

        self.assertEqual(movies[0]["added"], "")
        self.assertEqual(movies[0]["watched"], "")

    def test_gui_export_movies_to_web_launches(self):
        """Test export_movies_to_web launches Toplevel window and worker thread."""
        app = MagicMock()
        app.root = MagicMock()
        app.db_path = self.db_path

        with patch('GUI_sqlite_scrape.tk.Toplevel') as mock_top, \
             patch('GUI_sqlite_scrape.scrolledtext.ScrolledText') as mock_st, \
             patch('threading.Thread') as mock_thread:

            mock_thread.return_value = MagicMock()
            GUI_sqlite_scrape.IMDBdataBase.export_movies_to_web(app)

            mock_top.assert_called_once_with(app.root)
            mock_top.return_value.title.assert_called_with("Export movies.json")
            mock_thread.return_value.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()

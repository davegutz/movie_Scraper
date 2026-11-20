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

    def test_export_json_filter_by_dvd_number(self):
        """Verify export_json filters correctly by DVD number."""
        # DVD=1 (The Godfather, Alien)
        count, out_file = export_movies_json.export_json(db_path=self.db_path, output_path=self.json_path, dvd=1)
        self.assertEqual(count, 2)
        with open(out_file, "r", encoding="utf-8") as f:
            movies = json.load(f)
        self.assertEqual([m["title"] for m in movies], ["Alien", "The Godfather"])

        # DVD=0 (A Beautiful Mind)
        count, out_file = export_movies_json.export_json(db_path=self.db_path, output_path=self.json_path, dvd=0)
        self.assertEqual(count, 1)
        with open(out_file, "r", encoding="utf-8") as f:
            movies = json.load(f)
        self.assertEqual(movies[0]["title"], "A Beautiful Mind")

        # DVD=2 (None exist)
        count, out_file = export_movies_json.export_json(db_path=self.db_path, output_path=self.json_path, dvd=2)
        self.assertEqual(count, 0)

    def test_export_json_sort_by_my_rating(self):
        """Verify export_json sorts correctly by my_rating (descending and ascending)."""
        # Descending (default for ratings: 9.5 -> 9.0 -> 8.5)
        count, out_file = export_movies_json.export_json(
            db_path=self.db_path, output_path=self.json_path, sort_by="my_rating"
        )
        self.assertEqual(count, 3)
        with open(out_file, "r", encoding="utf-8") as f:
            movies = json.load(f)
        self.assertEqual([m["title"] for m in movies], ["The Godfather", "Alien", "A Beautiful Mind"])
        self.assertEqual([m["my_rating"] for m in movies], [9.5, 9.0, 8.5])

        # Ascending (8.5 -> 9.0 -> 9.5)
        count, out_file = export_movies_json.export_json(
            db_path=self.db_path, output_path=self.json_path, sort_by="my_rating", order="asc"
        )
        self.assertEqual(count, 3)
        with open(out_file, "r", encoding="utf-8") as f:
            movies = json.load(f)
        self.assertEqual([m["title"] for m in movies], ["A Beautiful Mind", "Alien", "The Godfather"])
        self.assertEqual([m["my_rating"] for m in movies], [8.5, 9.0, 9.5])

    def test_export_json_filter_dvd_and_sort_my_rating_combined(self):
        """Verify export_json correctly filters by DVD and sorts by my_rating simultaneously."""
        count, out_file = export_movies_json.export_json(
            db_path=self.db_path, output_path=self.json_path, dvd=1, sort_by="my_rating"
        )
        self.assertEqual(count, 2)
        with open(out_file, "r", encoding="utf-8") as f:
            movies = json.load(f)
        self.assertEqual([m["title"] for m in movies], ["The Godfather", "Alien"])
        self.assertEqual(movies[0]["dvd"], 1)
        self.assertEqual(movies[1]["dvd"], 1)
        self.assertGreater(movies[0]["my_rating"], movies[1]["my_rating"])

    def test_cli_dvd_and_sort_my_rating(self):
        """Verify export_movies_json CLI handles --dvd and --sort-my-rating options."""
        test_args = [
            "export_movies_json.py",
            "--db", self.db_path,
            "-o", self.json_path,
            "--dvd", "1",
            "--sort-my-rating"
        ]
        with patch('sys.argv', test_args):
            export_movies_json.main()

        self.assertTrue(os.path.isfile(self.json_path))
        with open(self.json_path, "r", encoding="utf-8") as f:
            movies = json.load(f)
        self.assertEqual(len(movies), 2)
        self.assertEqual([m["title"] for m in movies], ["The Godfather", "Alien"])

    def test_gui_export_movies_to_web_passes_filter_and_sort(self):
        """Verify GUI export_movies_to_web reads export_dvd_var and export_sort_rating_var."""
        app = MagicMock()
        app.root = MagicMock()
        app.db_path = self.db_path
        app.export_dvd_var = MagicMock(get=lambda: "1")
        app.export_sort_rating_var = MagicMock(get=lambda: True)

        with patch('GUI_sqlite_scrape.tk.Toplevel') as mock_top, \
             patch('GUI_sqlite_scrape.scrolledtext.ScrolledText') as mock_st, \
             patch('threading.Thread') as mock_thread, \
             patch('subprocess.Popen') as mock_popen:

            mock_inst = MagicMock()
            mock_thread.return_value = mock_inst
            mock_inst.start.side_effect = lambda: mock_thread.call_args[1]['target']()
            mock_proc = MagicMock()
            mock_proc.stdout.readline.side_effect = ['']
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            GUI_sqlite_scrape.IMDBdataBase.export_movies_to_web(app)

            call_args = mock_popen.call_args[0][0]
            self.assertIn('--dvd', call_args)
            self.assertIn('1', call_args)
            self.assertIn('--sort-my-rating', call_args)


if __name__ == '__main__':
    unittest.main()

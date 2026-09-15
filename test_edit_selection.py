"""
Unit tests for 'Edit Selection' feature and database field synchronization in GUI_sqlite_scrape.py.
"""

import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import sqlite3

# Mock Tkinter to allow importing GUI_sqlite_scrape without initializing GUI window
with patch('tkinter.Tk'):
    import GUI_sqlite_scrape


class TestEditSelection(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock()
        self.app.root = MagicMock()
        self.app.tree = MagicMock()
        self.app.c = MagicMock()
        self.app.conn = MagicMock()
        self.app.DB_FIELDS = GUI_sqlite_scrape.IMDBdataBase.DB_FIELDS
        self.app.picked = None
        self.app.select_display = MagicMock()
        self.app.poster = MagicMock()
        self.app.fetch_image_from_url = GUI_sqlite_scrape.IMDBdataBase.fetch_image_from_url

    def test_db_fields_covers_all_columns(self):
        """Ensure all 15 columns from My_Films schema are covered in DB_FIELDS."""
        expected_cols = {
            'IMDB_ID', 'title', 'year', 'rating', 'my_rating',
            'director', 'actors', 'generes', 'summary', 'cover',
            'WATCHED', 'DVD', 'runtime', 'certification', 'ADDED'
        }
        actual_cols = {col for col, _, _ in GUI_sqlite_scrape.IMDBdataBase.DB_FIELDS}
        self.assertEqual(actual_cols, expected_cols)
        self.assertEqual(len(GUI_sqlite_scrape.IMDBdataBase.DB_FIELDS), 15)

    def test_edit_selection_no_item_selected_shows_blocking_box(self):
        """If no film is selected, a blocking box saying 'choose entry to edit' should be displayed."""
        self.app.tree.focus.return_value = ""
        self.app.tree.selection.return_value = ()
        self.app.picked = '<search and select something above>'

        with patch('GUI_sqlite_scrape.tk.messagebox.showinfo') as mock_showinfo:
            GUI_sqlite_scrape.IMDBdataBase.edit_selection(self.app)
            mock_showinfo.assert_called_once()
            call_kwargs = mock_showinfo.call_args[1]
            self.assertEqual(call_kwargs.get('message'), 'choose entry to edit')
            self.assertEqual(call_kwargs.get('parent'), self.app.root)

    def test_edit_selection_item_selected_opens_window(self):
        """If a film is selected, open_edit_entry_window is called with the item."""
        self.app.tree.focus.return_value = "I001"
        self.app.tree.selection.return_value = ("I001",)
        sample_item = {'values': [12345, 'Sample Movie', 2024, 7.5, 8.0]}
        self.app.tree.item.return_value = sample_item

        with patch.object(self.app, 'open_edit_entry_window') as mock_open_edit:
            GUI_sqlite_scrape.IMDBdataBase.edit_selection(self.app)
            mock_open_edit.assert_called_once_with(sample_item)

    def test_open_edit_entry_window_prepopulation_and_update(self):
        """Test that edit window pre-populates fields and the 'Update' button executes the update."""
        fake_db_row = (
            59113, 'Doctor Zhivago', 1965, 7.9, 9.0, 'David Lean',
            'Omar Sharif, Julie Christie', 'Drama, Romance, War',
            'The life of a Russian physician...', 'http://example.com/cover.jpg',
            '2026-09-14', '1', '197', 'PG-13', '2026-09-14'
        )
        self.app.c.fetchone.return_value = fake_db_row

        item = {'values': [59113, 'Doctor Zhivago', 1965]}

        mock_win = MagicMock()
        entry_instances = []

        def mock_entry_factory(*args, **kwargs):
            m = MagicMock()
            entry_instances.append(m)
            return m

        buttons_created = {}

        def mock_button_factory(*args, **kwargs):
            text = kwargs.get('text')
            cmd = kwargs.get('command')
            buttons_created[text] = cmd
            return MagicMock()

        with patch('GUI_sqlite_scrape.tk.Toplevel', return_value=mock_win), \
             patch('GUI_sqlite_scrape.tk.Label'), \
             patch('GUI_sqlite_scrape.tk.Entry', side_effect=mock_entry_factory), \
             patch('GUI_sqlite_scrape.tk.Frame'), \
             patch('GUI_sqlite_scrape.tk.Button', side_effect=mock_button_factory):

            GUI_sqlite_scrape.IMDBdataBase.open_edit_entry_window(self.app, item)

            # Verify that query was executed to fetch DB record
            query = self.app.c.execute.call_args[0][0]
            self.assertIn("SELECT", query)
            self.assertIn("WHERE IMDB_ID = ?", query)

            # Verify buttons
            self.assertIn("Update", buttons_created)
            self.assertIn("Cancel", buttons_created)

            # Set mock entry values for when save_entry is invoked
            cols = [c[0] for c in self.app.DB_FIELDS]
            for i, col in enumerate(cols):
                val = str(fake_db_row[i])
                if col == 'my_rating':
                    val = '9.5'  # simulate user changing My Rating
                entry_instances[i].get.return_value = val

            # Trigger "Update" button command
            update_command = buttons_created["Update"]
            update_command()

            # Verify UPDATE query was executed
            last_sql = self.app.c.execute.call_args[0][0]
            last_params = self.app.c.execute.call_args[0][1]
            self.assertIn("UPDATE My_Films SET", last_sql)
            self.assertIn("WHERE IMDB_ID=?", last_sql)
            self.assertEqual(last_params[4], 9.5)  # my_rating as float
            self.assertEqual(last_params[-1], 59113)  # original_imdb_id

            # Verify commit, treeview refresh, and window destroy
            self.app.conn.commit.assert_called()
            self.app.fill_tree_view.assert_called()
            self.app.highlight_film.assert_called_with(('doctor zhivago', 1965))
            mock_win.destroy.assert_called()

    def test_fetch_image_from_url_handles_http_error(self):
        """fetch_image_from_url should return None instead of raising HTTPError on 403 Forbidden."""
        with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError(
                'https://example.com/bad', 403, 'Forbidden', {}, None)):
            result = GUI_sqlite_scrape.IMDBdataBase.fetch_image_from_url('https://example.com/bad')
            self.assertIsNone(result)

    def test_raise_it_handles_http_error_gracefully(self):
        """raise_it should not crash when urlopen throws HTTPError 403, and should fall back to blank.png."""
        item = {
            'text': '', 'image': '',
            'values': [
                11564570, 'Knives Out:  Glass Onion', 2022, '7.1', '8.5',
                'Rian Johnson', 'Daniel Craig', 'Crime', 'Summary...',
                'https://www.imdb.com/title/tt11564570/mediaviewer/rm3894230529/?ref_=tt_ov_i'
            ]
        }

        with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError(
                'https://example.com', 403, 'Forbidden', {}, None)), \
             patch('GUI_sqlite_scrape.Image.open') as mock_img_open, \
             patch('GUI_sqlite_scrape.ImageTk.PhotoImage') as mock_photo:

            # Should execute cleanly without raising HTTPError
            GUI_sqlite_scrape.IMDBdataBase.raise_it(self.app, item)

            # Confirm fallback to blank.png was attempted
            mock_img_open.assert_called_with("blank.png")
            self.app.poster.configure.assert_called()


if __name__ == '__main__':
    unittest.main()

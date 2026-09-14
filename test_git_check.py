"""
Unit tests for git database and repository version checking in GitHub_util.py and GUI_sqlite_scrape.py.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
import GitHub_util

# Mock Tkinter to allow importing GUI_sqlite_scrape without initializing display
with patch('tkinter.Tk'):
    import GUI_sqlite_scrape


class TestGitHubUtilCheck(unittest.TestCase):
    def test_current_database_status(self):
        db_path = '/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db'
        if os.path.exists(db_path):
            is_newer, info = GitHub_util.check_newer_git_database(db_path, print_status=False)
            self.assertFalse(is_newer)
            self.assertEqual(info.get('status'), 'up-to-date')

    def test_current_repo_status(self):
        app_dir = os.path.dirname(os.path.abspath(__file__))
        is_newer, info = GitHub_util.check_newer_git_repo(repo_dir=app_dir, print_status=False)
        self.assertFalse(is_newer)
        self.assertEqual(info.get('status'), 'up-to-date')
        self.assertEqual(info.get('repo_name'), 'movie_Scraper')

    def test_nonexistent_file(self):
        is_newer, info = GitHub_util.check_newer_git_database('/invalid/path/nonexistent_test.db', print_status=False)
        self.assertFalse(is_newer)
        self.assertIn('error', info)

    def test_simulated_database_behind(self):
        db_path = '/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db'
        if not os.path.exists(db_path):
            self.skipTest(f"Database {db_path} not found")

        real_run = GitHub_util.subprocess.run

        def mock_run(cmd, *args, **kwargs):
            if 'rev-list' in cmd:
                m = MagicMock()
                m.returncode = 0
                m.stdout = '2\n'
                return m
            return real_run(cmd, *args, **kwargs)

        with patch('GitHub_util.subprocess.run', side_effect=mock_run):
            is_newer, info = GitHub_util.check_newer_git_database(db_path, print_status=False)
            self.assertTrue(is_newer)
            self.assertEqual(info.get('method'), 'git')
            self.assertEqual(info.get('behind_count'), 2)
            self.assertTrue(len(info.get('remote_sha', '')) > 0)

    def test_simulated_repo_behind(self):
        app_dir = os.path.dirname(os.path.abspath(__file__))
        real_run = GitHub_util.subprocess.run

        def mock_run(cmd, *args, **kwargs):
            if 'rev-list' in cmd:
                m = MagicMock()
                m.returncode = 0
                m.stdout = '3\n'
                return m
            return real_run(cmd, *args, **kwargs)

        with patch('GitHub_util.subprocess.run', side_effect=mock_run):
            is_newer, info = GitHub_util.check_newer_git_repo(repo_dir=app_dir, print_status=False)
            self.assertTrue(is_newer)
            self.assertEqual(info.get('method'), 'git')
            self.assertEqual(info.get('behind_count'), 3)
            self.assertEqual(info.get('repo_name'), 'movie_Scraper')

    def test_simulated_github_api_newer(self):
        fake_db = '/tmp/fake_folder_test/IMDB_Films.db'
        os.makedirs('/tmp/fake_folder_test', exist_ok=True)
        with open(fake_db, 'w') as f:
            f.write('fake database content')
        os.utime(fake_db, (1000000000, 1000000000))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{
            'sha': '11223344556677889900aabbccddeeff12345678',
            'commit': {
                'author': {'date': '2026-09-14T10:00:00Z'},
                'message': 'New DB commit from another machine'
            }
        }]

        with patch('GitHub_util.requests.get', return_value=mock_resp):
            is_newer, info = GitHub_util.check_newer_git_database(fake_db, print_status=False)
            self.assertTrue(is_newer)
            self.assertEqual(info.get('method'), 'github_api')
            self.assertEqual(info.get('remote_sha'), '1122334')
            self.assertEqual(info.get('remote_msg'), 'New DB commit from another machine')


class TestGUIGitCheck(unittest.TestCase):
    def test_check_git_newer_version_warnings(self):
        imdb_mock = MagicMock()
        imdb_mock.db_path = '/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db'
        imdb_mock.root = MagicMock()

        fake_app_info = {
            'remote_date': '2026-09-14 11:30:00',
            'remote_msg': 'Update movie_Scraper features',
            'remote_sha': '2b3c4d5',
            'behind_count': 1,
            'local_date': '2026-09-14 07:08:13',
        }
        fake_db_info = {
            'remote_date': '2026-09-14 12:00:00',
            'remote_msg': 'Update film ratings',
            'remote_sha': '1a2b3c4',
            'behind_count': 2,
            'local_date': '2026-09-13 17:58:45',
        }

        with patch('GUI_sqlite_scrape.check_newer_git_repo', return_value=(True, fake_app_info)), \
             patch('GUI_sqlite_scrape.check_newer_git_database', return_value=(True, fake_db_info)), \
             patch('GUI_sqlite_scrape.tk.messagebox.showwarning') as mock_warn:
            GUI_sqlite_scrape.IMDBdataBase.check_git_newer_version(imdb_mock, verbose=False)
            self.assertEqual(mock_warn.call_count, 2)
            # First call is app warning
            app_call = mock_warn.call_args_list[0][1]
            self.assertIn('movie_Scraper', app_call['title'])
            self.assertIn('Update movie_Scraper features', app_call['message'])
            # Second call is db warning
            db_call = mock_warn.call_args_list[1][1]
            self.assertIn('IMDB_Films.db', db_call['message'])
            self.assertIn('Update film ratings', db_call['message'])

    def test_check_git_newer_version_uptodate_silent(self):
        imdb_mock = MagicMock()
        imdb_mock.db_path = '/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db'
        imdb_mock.root = MagicMock()

        with patch('GUI_sqlite_scrape.check_newer_git_repo', return_value=(False, {'status': 'up-to-date'})), \
             patch('GUI_sqlite_scrape.check_newer_git_database', return_value=(False, {'status': 'up-to-date'})), \
             patch('GUI_sqlite_scrape.tk.messagebox.showwarning') as mock_warn, \
             patch('GUI_sqlite_scrape.tk.messagebox.showinfo') as mock_info:
            GUI_sqlite_scrape.IMDBdataBase.check_git_newer_version(imdb_mock, verbose=False)
            self.assertFalse(mock_warn.called)
            self.assertFalse(mock_info.called)

    def test_check_git_newer_version_uptodate_verbose(self):
        imdb_mock = MagicMock()
        imdb_mock.db_path = '/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db'
        imdb_mock.root = MagicMock()

        with patch('GUI_sqlite_scrape.check_newer_git_repo', return_value=(False, {'status': 'up-to-date'})), \
             patch('GUI_sqlite_scrape.check_newer_git_database', return_value=(False, {'status': 'up-to-date'})), \
             patch('GUI_sqlite_scrape.tk.messagebox.showinfo') as mock_info:
            GUI_sqlite_scrape.IMDBdataBase.check_git_newer_version(imdb_mock, verbose=True)
            self.assertTrue(mock_info.called)
            self.assertIn('up to date', mock_info.call_args[1]['message'])


if __name__ == '__main__':
    unittest.main()

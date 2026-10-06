"""
Unit tests for Google Drive Backup feature in GUI_sqlite_scrape.py
"""

import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import subprocess

# Mock Tkinter to allow importing GUI_sqlite_scrape without initializing GUI window
with patch('tkinter.Tk'):
    import GUI_sqlite_scrape


class TestGoogleDriveBackup(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock()
        self.app.root = MagicMock()
        self.app.movies_dir = '/media/daveg/Lib/Movies'
        self.app.rclone_remote = 'gdrive:Movies'
        self.app.rclone_tpslimit = '8'
        self.app.rclone_transfers = '2'
        self.app.rclone_checkers = '4'
        self.app.rclone_chunk_size = '512M'
        self.app.rclone_stats = '5s'
        self.app.rclone_log_file = '/tmp/test_rclone_error.log'

    @patch('subprocess.Popen')
    @patch('GUI_sqlite_scrape.tk.Toplevel')
    @patch('GUI_sqlite_scrape.scrolledtext.ScrolledText')
    @patch('GUI_sqlite_scrape.tk.Label')
    @patch('GUI_sqlite_scrape.tk.Button')
    @patch('GUI_sqlite_scrape.tk.Frame')
    @patch('GUI_sqlite_scrape.tk.Scrollbar')
    def test_google_drive_backup_launches_rclone_and_opens_monitor(
            self, mock_scrollbar, mock_frame, mock_btn, mock_lbl, mock_scrolled, mock_toplevel, mock_popen):
        fake_proc = MagicMock()
        fake_proc.pid = 9999
        fake_proc.poll.return_value = 0
        mock_popen.return_value = fake_proc

        mock_win = MagicMock()
        mock_toplevel.return_value = mock_win

        buttons_created = {}

        def mock_btn_side_effect(*args, **kwargs):
            txt = kwargs.get('text', '')
            cmd = kwargs.get('command', None)
            buttons_created[txt] = cmd
            return MagicMock()

        mock_btn.side_effect = mock_btn_side_effect

        with patch('builtins.open', mock_open()) as mocked_file, \
             patch('os.path.exists', return_value=True):
            GUI_sqlite_scrape.IMDBdataBase.google_drive_backup(self.app)

            mock_popen.assert_called_once()
            called_cmd = mock_popen.call_args[0][0]

            self.assertEqual(called_cmd[0], 'rclone')
            self.assertEqual(called_cmd[1], 'sync')
            self.assertEqual(called_cmd[2], '/media/daveg/Lib/Movies/')
            self.assertEqual(called_cmd[3], 'gdrive:Movies')
            self.assertIn('--tpslimit', called_cmd)
            self.assertIn('8', called_cmd)
            self.assertIn('--transfers', called_cmd)
            self.assertIn('2', called_cmd)
            self.assertIn('--checkers', called_cmd)
            self.assertIn('4', called_cmd)
            self.assertIn('--drive-chunk-size', called_cmd)
            self.assertIn('512M', called_cmd)
            self.assertIn('--stats', called_cmd)
            self.assertIn('5s', called_cmd)
            self.assertIn('-vv', called_cmd)
            self.assertIn('--log-file', called_cmd)
            self.assertIn('/tmp/test_rclone_error.log', called_cmd)

            # Check kwargs for hidden background process execution
            call_kwargs = mock_popen.call_args[1]
            self.assertEqual(call_kwargs.get('stdout'), subprocess.DEVNULL)
            self.assertEqual(call_kwargs.get('stderr'), subprocess.DEVNULL)

            # Monitor window check
            mock_toplevel.assert_called_once_with(self.app.root)
            mock_win.title.assert_called_with("Google Drive Backup Monitor (tail -f rclone-error.log)")


if __name__ == '__main__':
    unittest.main()

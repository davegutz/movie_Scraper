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
        fake_proc.wait.return_value = 0
        fake_proc.returncode = 0
        mock_popen.return_value = fake_proc

        mock_win = MagicMock()
        mock_toplevel.return_value = mock_win

        with patch('builtins.open', mock_open()) as mocked_file, \
             patch('os.path.exists', return_value=True):
            win = GUI_sqlite_scrape.IMDBdataBase.google_drive_backup(self.app)
            if hasattr(win, 'runner_thread'):
                win.runner_thread.join(timeout=1.0)

            self.assertEqual(mock_popen.call_count, 2)
            cmd1 = mock_popen.call_args_list[0][0][0]
            cmd2 = mock_popen.call_args_list[1][0][0]

            # Pass 1: Download from Google Drive (remote -> local)
            self.assertEqual(cmd1[0], 'rclone')
            self.assertEqual(cmd1[1], 'copy')
            self.assertEqual(cmd1[2], 'gdrive:Movies')
            self.assertEqual(cmd1[3], '/media/daveg/Lib/Movies/')
            self.assertIn('--update', cmd1)
            self.assertIn('--tpslimit', cmd1)
            self.assertIn('8', cmd1)
            self.assertIn('--transfers', cmd1)
            self.assertIn('2', cmd1)
            self.assertIn('--checkers', cmd1)
            self.assertIn('4', cmd1)
            self.assertIn('--drive-chunk-size', cmd1)
            self.assertIn('512M', cmd1)
            self.assertIn('--stats', cmd1)
            self.assertIn('5s', cmd1)
            self.assertIn('-vv', cmd1)
            self.assertIn('--log-file', cmd1)
            self.assertIn('/tmp/test_rclone_error.log', cmd1)

            # Pass 2: Upload to Google Drive (local -> remote)
            self.assertEqual(cmd2[0], 'rclone')
            self.assertEqual(cmd2[1], 'copy')
            self.assertEqual(cmd2[2], '/media/daveg/Lib/Movies/')
            self.assertEqual(cmd2[3], 'gdrive:Movies')
            self.assertIn('--update', cmd2)

            mock_toplevel.assert_called_once_with(self.app.root)
            mock_win.title.assert_called_with("Google Drive Movies Backup Monitor (tail -f rclone-error.log)")

    @patch('subprocess.Popen')
    @patch('GUI_sqlite_scrape.tk.Toplevel')
    @patch('GUI_sqlite_scrape.scrolledtext.ScrolledText')
    @patch('GUI_sqlite_scrape.tk.Label')
    @patch('GUI_sqlite_scrape.tk.Button')
    @patch('GUI_sqlite_scrape.tk.Frame')
    @patch('GUI_sqlite_scrape.tk.Scrollbar')
    def test_google_drive_backup_music_launches_rclone_and_opens_monitor(
            self, mock_scrollbar, mock_frame, mock_btn, mock_lbl, mock_scrolled, mock_toplevel, mock_popen):
        fake_proc = MagicMock()
        fake_proc.pid = 8888
        fake_proc.poll.return_value = 0
        fake_proc.wait.return_value = 0
        fake_proc.returncode = 0
        mock_popen.return_value = fake_proc

        mock_win = MagicMock()
        mock_toplevel.return_value = mock_win

        self.app.music_dir = '/media/daveg/Lib/Music'
        self.app.rclone_music_remote = 'gdrive:Music'
        self.app.rclone_music_log_file = '/tmp/test_rclone_music_error.log'

        with patch('builtins.open', mock_open()) as mocked_file, patch('os.path.exists', return_value=True):
            win = GUI_sqlite_scrape.IMDBdataBase.google_drive_backup_music(self.app)
            if hasattr(win, 'runner_thread'):
                win.runner_thread.join(timeout=1.0)

            self.assertEqual(mock_popen.call_count, 2)
            cmd1 = mock_popen.call_args_list[0][0][0]
            cmd2 = mock_popen.call_args_list[1][0][0]

            # Pass 1: Download
            self.assertEqual(cmd1[0], 'rclone')
            self.assertEqual(cmd1[1], 'copy')
            self.assertEqual(cmd1[2], 'gdrive:Music')
            self.assertEqual(cmd1[3], '/media/daveg/Lib/Music/')
            self.assertIn('--update', cmd1)
            self.assertIn('/tmp/test_rclone_music_error.log', cmd1)

            # Pass 2: Upload
            self.assertEqual(cmd2[0], 'rclone')
            self.assertEqual(cmd2[1], 'copy')
            self.assertEqual(cmd2[2], '/media/daveg/Lib/Music/')
            self.assertEqual(cmd2[3], 'gdrive:Music')
            self.assertIn('--update', cmd2)

            mock_toplevel.assert_called_once_with(self.app.root)
            mock_win.title.assert_called_with("Google Drive Music Backup Monitor (tail -f rclone-music-error.log)")

    @patch('subprocess.Popen')
    @patch('GUI_sqlite_scrape.tk.Toplevel')
    @patch('GUI_sqlite_scrape.scrolledtext.ScrolledText')
    @patch('GUI_sqlite_scrape.tk.Label')
    @patch('GUI_sqlite_scrape.tk.Button')
    @patch('GUI_sqlite_scrape.tk.Frame')
    @patch('GUI_sqlite_scrape.tk.Scrollbar')
    def test_google_drive_backup_tv_shows_launches_rclone_and_opens_monitor(
            self, mock_scrollbar, mock_frame, mock_btn, mock_lbl, mock_scrolled, mock_toplevel, mock_popen):
        fake_proc = MagicMock()
        fake_proc.pid = 7777
        fake_proc.poll.return_value = 0
        fake_proc.wait.return_value = 0
        fake_proc.returncode = 0
        mock_popen.return_value = fake_proc

        mock_win = MagicMock()
        mock_toplevel.return_value = mock_win

        self.app.tv_shows_dir = '/media/daveg/Lib/TV Shows'
        self.app.rclone_tv_shows_remote = 'gdrive:TV Shows'
        self.app.rclone_tv_shows_log_file = '/tmp/test_rclone_tv_shows_error.log'

        with patch('builtins.open', mock_open()) as mocked_file, patch('os.path.exists', return_value=True):
            win = GUI_sqlite_scrape.IMDBdataBase.google_drive_backup_tv_shows(self.app)
            if hasattr(win, 'runner_thread'):
                win.runner_thread.join(timeout=1.0)

            self.assertEqual(mock_popen.call_count, 2)
            cmd1 = mock_popen.call_args_list[0][0][0]
            cmd2 = mock_popen.call_args_list[1][0][0]

            # Pass 1: Download
            self.assertEqual(cmd1[0], 'rclone')
            self.assertEqual(cmd1[1], 'copy')
            self.assertEqual(cmd1[2], 'gdrive:TV Shows')
            self.assertEqual(cmd1[3], '/media/daveg/Lib/TV Shows/')
            self.assertIn('--update', cmd1)
            self.assertIn('/tmp/test_rclone_tv_shows_error.log', cmd1)

            # Pass 2: Upload
            self.assertEqual(cmd2[0], 'rclone')
            self.assertEqual(cmd2[1], 'copy')
            self.assertEqual(cmd2[2], '/media/daveg/Lib/TV Shows/')
            self.assertEqual(cmd2[3], 'gdrive:TV Shows')
            self.assertIn('--update', cmd2)

            mock_toplevel.assert_called_once_with(self.app.root)
            mock_win.title.assert_called_with("Google Drive TV Shows Backup Monitor (tail -f rclone-tv-shows-error.log)")

    @patch('subprocess.Popen')
    @patch('GUI_sqlite_scrape.tk.Toplevel')
    @patch('GUI_sqlite_scrape.scrolledtext.ScrolledText')
    @patch('GUI_sqlite_scrape.tk.Label')
    @patch('GUI_sqlite_scrape.tk.Button')
    @patch('GUI_sqlite_scrape.tk.Frame')
    @patch('GUI_sqlite_scrape.tk.Scrollbar')
    def test_google_drive_backup_videos_launches_rclone_and_opens_monitor(
            self, mock_scrollbar, mock_frame, mock_btn, mock_lbl, mock_scrolled, mock_toplevel, mock_popen):
        fake_proc = MagicMock()
        fake_proc.pid = 6666
        fake_proc.poll.return_value = 0
        fake_proc.wait.return_value = 0
        fake_proc.returncode = 0
        mock_popen.return_value = fake_proc

        mock_win = MagicMock()
        mock_toplevel.return_value = mock_win

        self.app.videos_dir = '/media/daveg/Lib/Videos'
        self.app.rclone_videos_remote = 'gdrive:Videos'
        self.app.rclone_videos_log_file = '/tmp/test_rclone_videos_error.log'

        with patch('builtins.open', mock_open()) as mocked_file, patch('os.path.exists', return_value=True):
            win = GUI_sqlite_scrape.IMDBdataBase.google_drive_backup_videos(self.app)
            if hasattr(win, 'runner_thread'):
                win.runner_thread.join(timeout=1.0)

            self.assertEqual(mock_popen.call_count, 2)
            cmd1 = mock_popen.call_args_list[0][0][0]
            cmd2 = mock_popen.call_args_list[1][0][0]

            # Pass 1: Download
            self.assertEqual(cmd1[0], 'rclone')
            self.assertEqual(cmd1[1], 'copy')
            self.assertEqual(cmd1[2], 'gdrive:Videos')
            self.assertEqual(cmd1[3], '/media/daveg/Lib/Videos/')
            self.assertIn('--update', cmd1)
            self.assertIn('/tmp/test_rclone_videos_error.log', cmd1)

            # Pass 2: Upload
            self.assertEqual(cmd2[0], 'rclone')
            self.assertEqual(cmd2[1], 'copy')
            self.assertEqual(cmd2[2], '/media/daveg/Lib/Videos/')
            self.assertEqual(cmd2[3], 'gdrive:Videos')
            self.assertIn('--update', cmd2)

            mock_toplevel.assert_called_once_with(self.app.root)
            mock_win.title.assert_called_with("Google Drive Videos Backup Monitor (tail -f rclone-videos-error.log)")

    @patch('GUI_sqlite_scrape.filedialog.askdirectory')
    def test_enter_lib_folder_updates_paths_and_persists(self, mock_askdirectory):
        mock_askdirectory.return_value = '/new/media/Lib'
        self.app.lib_folder = '/old/media/Lib'
        self.app.cf = MagicMock()
        self.app.destination_lib_butt = MagicMock()

        GUI_sqlite_scrape.IMDBdataBase.enter_lib_folder(self.app)

        self.assertEqual(self.app.lib_folder, '/new/media/Lib')
        self.assertEqual(self.app.movies_dir, '/new/media/Lib/Movies')
        self.assertEqual(self.app.music_dir, '/new/media/Lib/Music')
        self.assertEqual(self.app.tv_shows_dir, '/new/media/Lib/TV Shows')
        self.assertEqual(self.app.videos_dir, '/new/media/Lib/Videos')
        self.app.cf.put_item.assert_called_once_with('path', 'lib_folder', '/new/media/Lib')
        self.app.destination_lib_butt.config.assert_called_once_with(text='/new/media/Lib')

    @patch('GUI_sqlite_scrape.filedialog.askdirectory')
    def test_enter_lib_folder_cancelled_keeps_existing(self, mock_askdirectory):
        mock_askdirectory.return_value = ''
        self.app.lib_folder = '/old/media/Lib'
        self.app.cf = MagicMock()
        self.app.destination_lib_butt = MagicMock()

        GUI_sqlite_scrape.IMDBdataBase.enter_lib_folder(self.app)

        self.assertEqual(self.app.lib_folder, '/old/media/Lib')
        self.app.cf.put_item.assert_not_called()
        self.app.destination_lib_butt.config.assert_not_called()


    def test_reset_rclone_token_expiry(self):
        import tempfile
        sample_conf = """[gdrive]
type = drive
scope = drive
#token = {"access_token":"old","expiry":"2026-10-22T07:32:52"}
client_id = test_id
token = {"access_token": "abc", "expiry": "2026-10-29T15:00:00Z", "refresh_token": "xyz"}

[other]
type = drive
token = {"access_token": "def", "expiry": "2026-10-29T15:00:00Z"}
"""
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(sample_conf)
            tname = f.name
        try:
            res = GUI_sqlite_scrape.IMDBdataBase._reset_rclone_token_expiry("gdrive:Movies", tname)
            self.assertTrue(res)
            with open(tname) as f:
                new_text = f.read()
            self.assertIn('"expiry": "2000-01-01T00:00:00Z"', new_text)
            self.assertIn('[other]\ntype = drive\ntoken = {"access_token": "def", "expiry": "2026-10-29T15:00:00Z"}', new_text)
        finally:
            if os.path.exists(tname):
                os.unlink(tname)

    @patch('GUI_sqlite_scrape.IMDBdataBase._reset_rclone_token_expiry')
    @patch('subprocess.Popen')
    @patch('GUI_sqlite_scrape.tk.Toplevel')
    @patch('GUI_sqlite_scrape.scrolledtext.ScrolledText')
    @patch('GUI_sqlite_scrape.tk.Label')
    @patch('GUI_sqlite_scrape.tk.Button')
    @patch('GUI_sqlite_scrape.tk.Frame')
    @patch('GUI_sqlite_scrape.tk.Scrollbar')
    def test_auth_error_auto_recovery_retries(
            self, mock_scrollbar, mock_frame, mock_btn, mock_lbl, mock_scrolled, mock_toplevel, mock_popen, mock_reset_expiry):
        proc_fail = MagicMock()
        proc_fail.pid = 1111
        def fake_wait():
            with open(test_log, "a") as f:
                f.write("\nError 401: Request had invalid authentication credentials. authError Invalid Credentials\n")
            return 1
        proc_fail.wait.side_effect = fake_wait
        proc_fail.returncode = 1

        proc_pass1 = MagicMock()
        proc_pass1.pid = 2222
        proc_pass1.wait.return_value = 0
        proc_pass1.returncode = 0

        proc_pass2 = MagicMock()
        proc_pass2.pid = 3333
        proc_pass2.wait.return_value = 0
        proc_pass2.returncode = 0

        mock_popen.side_effect = [proc_fail, proc_pass1, proc_pass2]

        mock_win = MagicMock()
        mock_toplevel.return_value = mock_win

        test_log = "/tmp/test_rclone_auth_recovery.log"
        with open(test_log, "w") as f:
            f.write("Some log before\nError 401: Invalid Credentials authError\n")

        self.app.rclone_log_file = test_log

        try:
            win = GUI_sqlite_scrape.IMDBdataBase.google_drive_backup(self.app)
            if hasattr(win, "runner_thread"):
                win.runner_thread.join(timeout=1.0)

            self.assertEqual(mock_popen.call_count, 3)
            mock_reset_expiry.assert_called_once_with("gdrive:Movies")
        finally:
            if os.path.exists(test_log):
                os.unlink(test_log)

    @patch("GUI_sqlite_scrape.tk.messagebox.showerror")
    @patch("os.path.isdir", return_value=False)
    @patch("os.path.exists", return_value=False)
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_backup_aborts_cleanly_when_directory_unmounted(self, mock_popen, mock_run, mock_exists, mock_isdir, mock_showerror):
        res = GUI_sqlite_scrape.IMDBdataBase.google_drive_backup(self.app)
        self.assertIsNone(res)
        mock_popen.assert_not_called()
        mock_showerror.assert_called_once()

if __name__ == '__main__':
    unittest.main()

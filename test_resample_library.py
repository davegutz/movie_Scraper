import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import resample_library as rl


class TestResampleLibraryRestore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache = {}

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_restore_larger_backups_restores_when_active_is_larger(self):
        # Create an original .bak file (1000 bytes) and a larger active file (2000 bytes)
        movie_path = os.path.join(self.test_dir, "Bloated Movie (2020).mp4")
        bak_path = f"{movie_path}.bak"

        with open(bak_path, "wb") as f:
            f.write(b"O" * 1000)  # Original smaller content

        with open(movie_path, "wb") as f:
            f.write(b"B" * 2000)  # Bloated resampled content

        restored = rl.restore_larger_backups(self.test_dir, cache=self.cache, dry_run=False)

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]['path'], movie_path)
        self.assertEqual(restored[0]['bak_bytes'], 1000)
        self.assertEqual(restored[0]['active_bytes'], 2000)

        # Active file should now have restored original content (1000 bytes)
        self.assertTrue(os.path.isfile(movie_path))
        self.assertEqual(os.path.getsize(movie_path), 1000)
        with open(movie_path, "rb") as f:
            self.assertEqual(f.read(), b"O" * 1000)

        # .bak file was moved back to active file
        self.assertFalse(os.path.exists(bak_path))

    def test_restore_larger_backups_does_not_restore_when_active_is_smaller(self):
        # Successfully compressed: active (500 bytes) < bak (1000 bytes)
        movie_path = os.path.join(self.test_dir, "Compressed Movie (2020).mp4")
        bak_path = f"{movie_path}.bak"

        with open(bak_path, "wb") as f:
            f.write(b"O" * 1000)

        with open(movie_path, "wb") as f:
            f.write(b"C" * 500)

        restored = rl.restore_larger_backups(self.test_dir, cache=self.cache, dry_run=False)

        self.assertEqual(len(restored), 0)
        self.assertEqual(os.path.getsize(movie_path), 500)
        self.assertTrue(os.path.isfile(bak_path))

    def test_restore_larger_backups_dry_run_leaves_files_untouched(self):
        movie_path = os.path.join(self.test_dir, "Bloated Movie (2020).mp4")
        bak_path = f"{movie_path}.bak"

        with open(bak_path, "wb") as f:
            f.write(b"O" * 1000)

        with open(movie_path, "wb") as f:
            f.write(b"B" * 2000)

        restored = rl.restore_larger_backups(self.test_dir, cache=self.cache, dry_run=True)

        self.assertEqual(len(restored), 1)
        # Files should NOT have changed on disk
        self.assertTrue(os.path.isfile(bak_path))
        self.assertEqual(os.path.getsize(movie_path), 2000)
        self.assertEqual(os.path.getsize(bak_path), 1000)

    def test_restore_larger_backups_target_file(self):
        movie1 = os.path.join(self.test_dir, "Movie1.mp4")
        movie2 = os.path.join(self.test_dir, "Movie2.mp4")

        with open(f"{movie1}.bak", "wb") as f:
            f.write(b"O" * 1000)
        with open(movie1, "wb") as f:
            f.write(b"B" * 2000)

        with open(f"{movie2}.bak", "wb") as f:
            f.write(b"O" * 1000)
        with open(movie2, "wb") as f:
            f.write(b"B" * 2000)

        # Restore only target_file movie1
        restored = rl.restore_larger_backups(
            self.test_dir,
            cache=self.cache,
            dry_run=False,
            target_file=movie1
        )

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]['path'], movie1)
        self.assertEqual(os.path.getsize(movie1), 1000)
        # movie2 was not target_file, so should remain untouched
        self.assertEqual(os.path.getsize(movie2), 2000)
        self.assertTrue(os.path.isfile(f"{movie2}.bak"))

    def test_resample_single_file_restores_when_resampled_is_larger_than_bak(self):
        movie_path = os.path.join(self.test_dir, "Sample Movie (2020).mp4")
        orig_content = b"ORIGINAL_VIDEO_DATA" * 500000  # ~9.5 MB
        with open(movie_path, "wb") as f:
            f.write(orig_content)

        file_info = {
            'path': movie_path,
            'filename': os.path.basename(movie_path),
            'size_bytes': len(orig_content),
            'time': '01:30:00'
        }

        # Mock run_ffmpeg_with_progress to write a larger file (> 9.5 MB)
        def mock_run_ffmpeg(cmd, total_duration_sec=None):
            # cmd is: [ffmpeg, -y, -i, src, ..., temp_path]
            out_file = cmd[-1]
            with open(out_file, "wb") as f:
                # Write 15 MB (larger than original ~9.5 MB)
                f.write(b"LARGER_ENCODED_DATA" * 800000)
            return 0, ""

        with patch('resample_library.run_ffmpeg_with_progress', side_effect=mock_run_ffmpeg):
            with patch('resample_library.update_cache_entry'):
                result = rl.resample_single_file(file_info, crf=20, backup=True)

        self.assertFalse(result['success'])
        self.assertTrue(result.get('restored'))
        self.assertEqual(result['old_bytes'], len(orig_content))
        self.assertGreater(result['new_bytes'], result['old_bytes'])

        # Original file must be restored at movie_path
        self.assertTrue(os.path.isfile(movie_path))
        self.assertEqual(os.path.getsize(movie_path), len(orig_content))
        with open(movie_path, "rb") as f:
            self.assertEqual(f.read(), orig_content)

        # .bak and temp files must not remain
        self.assertFalse(os.path.exists(f"{movie_path}.bak"))
        temp_path = os.path.join(self.test_dir, f".{os.path.splitext(os.path.basename(movie_path))[0]}.resampled_tmp.mp4")
        self.assertFalse(os.path.exists(temp_path))

    def test_resample_single_file_replaces_when_resampled_is_smaller(self):
        movie_path = os.path.join(self.test_dir, "Sample Movie (2020).mp4")
        orig_content = b"ORIGINAL_VIDEO_DATA" * 800000  # ~15.2 MB
        with open(movie_path, "wb") as f:
            f.write(orig_content)

        file_info = {
            'path': movie_path,
            'filename': os.path.basename(movie_path),
            'size_bytes': len(orig_content),
            'time': '01:30:00'
        }

        # Mock run_ffmpeg_with_progress to write a smaller file (~6 MB, which is > 5 MB threshold)
        compressed_content = b"COMPRESSED_DATA" * 400000
        def mock_run_ffmpeg(cmd, total_duration_sec=None):
            out_file = cmd[-1]
            with open(out_file, "wb") as f:
                f.write(compressed_content)
            return 0, ""

        with patch('resample_library.run_ffmpeg_with_progress', side_effect=mock_run_ffmpeg):
            with patch('resample_library.get_subtitle_args', return_value=[]):
                with patch('resample_library.update_cache_entry'):
                    result = rl.resample_single_file(file_info, crf=20, backup=True)

        self.assertTrue(result['success'])
        self.assertFalse(result.get('restored', False))
        self.assertEqual(result['new_bytes'], len(compressed_content))
        self.assertEqual(result['old_bytes'], len(orig_content))

        # movie_path should now have the compressed content
        self.assertTrue(os.path.isfile(movie_path))
        self.assertEqual(os.path.getsize(movie_path), len(compressed_content))

        # .bak should exist with original content
        bak_path = f"{movie_path}.bak"
        self.assertTrue(os.path.isfile(bak_path))
        self.assertEqual(os.path.getsize(bak_path), len(orig_content))


    def test_main_summary_reports_new_file_size(self):
        import io
        from contextlib import redirect_stdout

        candidates = [{
            'path': os.path.join(self.test_dir, "Demo (2020).mp4"),
            'filename': "Demo (2020).mp4",
            'size_bytes': 4 * 1024 * 1024 * 1024,  # 4 GB
            'size_gb': 4.0,
            'format': 'mp4',
            'resolution': '1080p',
            'fps': 24.0,
            'time': '01:45:00',
            'sub': 'None',
            'jellyfin': 'DIRECT',
            'bmp': 'NO',
            'srt': 'NO',
            'oversized': True
        }]

        mock_result = {
            'success': True,
            'old_bytes': 4 * 1024 * 1024 * 1024,
            'new_bytes': 1 * 1024 * 1024 * 1024,  # 1 GB
            'saved_bytes': 3 * 1024 * 1024 * 1024,
            'elapsed': 120.0,
            'backup_path': None
        }

        f = io.StringIO()
        with redirect_stdout(f):
            with patch('resample_library.load_cache', return_value={}):
                with patch('resample_library.save_cache'):
                    with patch('resample_library.scan_candidates', return_value=candidates):
                        with patch('resample_library.resample_single_file', return_value=mock_result):
                            rl.main(
                                "--movies-dir", self.test_dir,
                                "--no-caffeine-check",
                                "--no-download-srt",
                                "--no-verify-subtitles",
                                "--all"
                            )

        output = f.getvalue()
        self.assertIn("Original Total Size:      4.00 GB", output)
        self.assertIn("New Resampled Size:       1.00 GB", output)
        self.assertIn("Total Disk Space Freed:   3.00 GB (75.0% reduction)", output)
        self.assertIn("[✓] Successfully Resampled Files (1):", output)
        self.assertIn("Orig (GB)", output)
        self.assertIn("New (GB)", output)
        self.assertIn("Saved (GB)", output)
        self.assertIn("4.00", output)
        self.assertIn("1.00", output)
        self.assertIn("3.00", output)
        self.assertIn("Demo (2020).mp4", output)


if __name__ == '__main__':
    unittest.main()


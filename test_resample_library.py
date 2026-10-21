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
            'backup_path': None,
            'format': 'H264',
            'fps': '24'
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
        self.assertIn("Result:   1.00 GB", output)
        self.assertIn("| H264 | 24 fps", output)
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


class TestEquivalentRatioCriteria(unittest.TestCase):
    def test_get_resolution_target_rate_defaults(self):
        # <= 540p -> 1.25 GB/hr
        self.assertEqual(rl.get_resolution_target_rate('404p'), 1.25)
        self.assertEqual(rl.get_resolution_target_rate('480p'), 1.25)
        self.assertEqual(rl.get_resolution_target_rate('540p'), 1.25)
        # <= 720p -> 1.75 GB/hr
        self.assertEqual(rl.get_resolution_target_rate('720p'), 1.75)
        # <= 1080p -> 3.00 GB/hr
        self.assertEqual(rl.get_resolution_target_rate('1080p'), 3.00)
        # > 1080p -> 7.50 GB/hr
        self.assertEqual(rl.get_resolution_target_rate('2160p'), 7.50)
        # Unknown / missing -> 2.00 GB/hr
        self.assertEqual(rl.get_resolution_target_rate('unknown'), 2.00)
        self.assertEqual(rl.get_resolution_target_rate(None), 2.00)

    def test_get_resolution_target_rate_custom(self):
        # Explicit max_gb_per_hour overrides resolution tiers
        self.assertEqual(rl.get_resolution_target_rate('480p', max_gb_per_hour=1.0), 1.0)
        self.assertEqual(rl.get_resolution_target_rate('1080p', max_gb_per_hour=0.85), 0.85)

    def test_is_oversized_equivalent_ratio(self):
        # 45-min SD episode (404p, target 1.25 GB/hr):
        # 1.02 GB for 47 min = 1.30 GB/hr > 1.25 -> True
        self.assertTrue(rl.is_oversized('404p', 1.02, '00:47:00'))
        # 0.28 GB for 47 min = 0.36 GB/hr < 1.25 -> False
        self.assertFalse(rl.is_oversized('404p', 0.28, '00:47:00'))

        # 22-min SD episode (480p, target 1.25 GB/hr):
        # 0.50 GB for 22 min = 1.36 GB/hr > 1.25 -> True
        self.assertTrue(rl.is_oversized('480p', 0.50, '00:22:00'))
        # 0.20 GB for 22 min = 0.55 GB/hr < 1.25 -> False
        self.assertFalse(rl.is_oversized('480p', 0.20, '00:22:00'))

        # 120-min 1080p movie (target 3.00 GB/hr):
        # 6.5 GB for 120 min = 3.25 GB/hr > 3.00 -> True
        self.assertTrue(rl.is_oversized('1080p', 6.5, '02:00:00'))
        # 5.5 GB for 120 min = 2.75 GB/hr < 3.00 -> False
        self.assertFalse(rl.is_oversized('1080p', 5.5, '02:00:00'))

    def test_is_oversized_custom_ratio(self):
        # With custom ratio of 0.8 GB/hr:
        # A file at 0.90 GB/hr is oversized
        self.assertTrue(rl.is_oversized('480p', 0.60, '00:40:00', max_gb_per_hour=0.8))
        # With custom ratio of 1.5 GB/hr:
        # Same file at 0.90 GB/hr is not oversized
        self.assertFalse(rl.is_oversized('480p', 0.60, '00:40:00', max_gb_per_hour=1.5))

    def test_dry_run_output_displays_ratio_info_and_hints(self):
        import io
        from contextlib import redirect_stdout

        candidates = [{
            'path': '/tmp/test_tv.mp4',
            'filename': 'TestShow s01e01.mp4',
            'size_bytes': int(1.02 * (1024 ** 3)),
            'size_gb': 1.02,
            'format': 'H264',
            'resolution': '404p',
            'fps': '23.98',
            'time': '00:47',
            'dur_m': 47.0,
            'rate_gb_hr': 1.30,
            'target_rate': 1.25,
            'sub': 'None',
            'jellyfin': '-',
            'bmp': 'NO',
            'srt': 'NO',
            'oversized': True
        }]

        f = io.StringIO()
        with redirect_stdout(f):
            with patch('resample_library.load_cache', return_value={}):
                with patch('resample_library.save_cache'):
                    with patch('resample_library.scan_candidates', return_value=candidates):
                        with patch('os.path.isdir', return_value=True):
                            with patch('resample_library.restore_larger_backups', return_value=[]):
                                with patch('resample_library.cleanup_stale_temp_files'):
                                    with self.assertRaises(SystemExit):
                                        rl.main(
                                            "--movies-dir", "/tmp",
                                            "--no-download-srt",
                                            "--dry-run"
                                        )

        output = f.getvalue()
        # Verify resolution explanation and GB/hr in header
        self.assertIn("Equivalent Ratio Criteria (Size / Length Ratio by Resolution Tier)", output)
        self.assertIn("► <= 540p (SD/DVD):  1.25 GB/hr", output)
        self.assertIn("[RUNNING THIS INSTANCE: 1 file (404p)]", output)
        self.assertIn("• <= 720p (HD):      1.75 GB/hr", output)
        self.assertIn("• <= 1080p (FHD):    3.00 GB/hr", output)
        self.assertIn("Hint: Pass --ratio <FLOAT> or --max-gb-per-hour <FLOAT>", output)

        # Verify table columns
        self.assertIn("Rate(GB/h)", output)
        self.assertIn("Thresh", output)
        self.assertIn("1.30", output)
        self.assertIn("1.25", output)
        self.assertIn("404p", output)
        self.assertIn("TestShow s01e01.mp4", output)

    def test_probe_file_meta_detects_deleted_srt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "My Movie (2020).m4v")
            with open(video_path, "wb") as f:
                f.write(b"dummy video data")

            st = os.stat(video_path)
            cache_key = f"{video_path}|{st.st_mtime}|{st.st_size}"
            cache = {
                cache_key: {
                    'format': 'H264',
                    'res': '1080p',
                    'fps': '23.98',
                    'time': '01:30',
                    'sub': 'SRT',
                    'jellyfin': 'DIRECT',
                    'raw_sub': 'YES',
                    'bmp': 'NO',
                    'srt': 'YES'
                }
            }

            self.assertEqual(rl.check_srt_file(video_path), 'NO')

            with patch('resample_library.check_subtitles_info', return_value=('None', '-', 'NO', 'NO', 'NO')):
                fmt, res, fps, time_str, sub_val, jf_val, bmp_val, srt_val = rl.probe_file_meta(video_path, cache=cache)

            self.assertEqual(sub_val, 'None')
            self.assertEqual(jf_val, '-')
            self.assertEqual(srt_val, 'NO')
            self.assertEqual(cache[cache_key]['sub'], 'None')
            self.assertEqual(cache[cache_key]['jellyfin'], '-')
            self.assertEqual(cache[cache_key]['srt'], 'NO')


if __name__ == '__main__':
    unittest.main()



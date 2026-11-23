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

    def test_detect_stutter_framerate(self):
        # Container fps < 48 should bypass immediately
        self.assertIsNone(rl.detect_stutter_framerate('/dummy/path.mp4', fps_str='23.98'))
        self.assertIsNone(rl.detect_stutter_framerate('/dummy/path.mp4', fps_str='29.97'))

        # Non-existent file
        self.assertIsNone(rl.detect_stutter_framerate('/nonexistent/video.mp4', fps_str='60'))

        # Mock ffmpeg mpdecimate detecting 24 fps content in 60 fps container
        with tempfile.NamedTemporaryFile(suffix='.mp4') as tmp:
            with patch('subprocess.check_output', return_value="120.0"):
                mock_res_24 = unittest.mock.MagicMock()
                mock_res_24.stderr = "frame=  144 fps= 24 q=-0.0 Lsize=N/A time=00:00:06.00 bitrate=N/A"
                with patch('subprocess.run', return_value=mock_res_24):
                    self.assertEqual(rl.detect_stutter_framerate(tmp.name, fps_str='60'), 23.976)

                mock_res_30 = unittest.mock.MagicMock()
                mock_res_30.stderr = "frame=  180 fps= 30 q=-0.0 Lsize=N/A time=00:00:06.00 bitrate=N/A"
                with patch('subprocess.run', return_value=mock_res_30):
                    self.assertEqual(rl.detect_stutter_framerate(tmp.name, fps_str='60'), 29.97)

                mock_res_60 = unittest.mock.MagicMock()
                mock_res_60.stderr = "frame=  360 fps= 60 q=-0.0 Lsize=N/A time=00:00:06.00 bitrate=N/A"
                with patch('subprocess.run', return_value=mock_res_60):
                    self.assertIsNone(rl.detect_stutter_framerate(tmp.name, fps_str='60'))

    def test_build_ffmpeg_cmd_decimate_stutter(self):
        # 24 fps decimation
        cmd_24 = rl.build_ffmpeg_cmd('/in.mp4', '/out.mp4', '2.5M', '1080p', decimate_stutter=True, target_fps=24)
        self.assertIn('-vf', cmd_24)
        self.assertIn('mpdecimate', cmd_24)
        self.assertIn('-r', cmd_24)
        r_idx = cmd_24.index('-r')
        self.assertEqual(cmd_24[r_idx + 1], '24000/1001')

        # 30 fps decimation
        cmd_30 = rl.build_ffmpeg_cmd('/in.mp4', '/out.mp4', '2.5M', '1080p', decimate_stutter=True, target_fps=30)
        self.assertIn('-r', cmd_30)
        r_idx = cmd_30.index('-r')
        self.assertEqual(cmd_30[r_idx + 1], '30000/1001')

        # Normal re-encoding without decimation
        cmd_norm = rl.build_ffmpeg_cmd('/in.mp4', '/out.mp4', '2.5M', '1080p', decimate_stutter=False)
        self.assertNotIn('mpdecimate', cmd_norm)
        self.assertNotIn('-r', cmd_norm)

    def test_scan_candidates_includes_stutter_when_sized_yes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "StutterMovie (2024).mp4")
            with open(video_path, "wb") as f:
                f.write(b"x" * 1024 * 1024)

            # Metadata says 1080p, 60fps, 100min duration, size 1GB (Rate = 0.6 GB/hr << 3.0 GB/hr)
            # Sized: YES (oversized=False), but judder is detected as 24 fps
            mock_meta = ('H264', '1080p', '60.0', '01:40', 'SRT', 'DIRECT', 'NO', 'YES')
            with patch('resample_library.probe_file_meta', return_value=mock_meta):
                with patch('resample_library.detect_stutter_framerate', return_value=23.976):
                    candidates = rl.scan_candidates(tmpdir, extensions={'.mp4'}, cache={}, max_gb_per_hour=3.0)

            self.assertEqual(len(candidates), 1)
            c = candidates[0]
            self.assertFalse(c['oversized'])
            self.assertTrue(c['has_stutter'])
            self.assertEqual(c['judder'], '24 fps')

    def test_scan_candidates_stutter_only_filters_out_oversized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = os.path.join(tmpdir, "OversizedNoStutter.mp4")
            f2 = os.path.join(tmpdir, "CleanWithStutter.mp4")
            with open(f1, "wb") as f:
                f.write(b"x" * 1024 * 1024)
            with open(f2, "wb") as f:
                f.write(b"y" * 1024 * 1024)

            def mock_probe(path, cache):
                if "Oversized" in path:
                    return ('H264', '1080p', '23.98', '01:00', 'SRT', 'DIRECT', 'NO', 'YES')
                else:
                    return ('H264', '1080p', '60.0', '02:00', 'SRT', 'DIRECT', 'NO', 'YES')

            def mock_detect(path, fps):
                if "CleanWithStutter" in path:
                    return 23.976
                return None

            with patch('resample_library.probe_file_meta', side_effect=mock_probe):
                with patch('resample_library.detect_stutter_framerate', side_effect=mock_detect):
                    with patch('resample_library.is_oversized', side_effect=lambda res, sz, t, **kw: True if '23.98' in str(res) or '01:00' in str(t) else False):
                        # With stutter_only=True: ONLY the stutter file is returned, oversized without stutter is excluded!
                        candidates = rl.scan_candidates(tmpdir, extensions={'.mp4'}, cache={}, stutter_only=True)
                        self.assertEqual(len(candidates), 1)
                        self.assertEqual(candidates[0]['filename'], "CleanWithStutter.mp4")
                        self.assertTrue(candidates[0]['has_stutter'])

    def test_resolve_library_path(self):
        self.assertEqual(rl.resolve_library_path(None), rl.DEFAULT_MOVIES_DIR)
        self.assertEqual(rl.resolve_library_path(""), rl.DEFAULT_MOVIES_DIR)
        self.assertEqual(rl.resolve_library_path("/media/daveg/Lib/Movies"), "/media/daveg/Lib/Movies")
        tv_path = rl.resolve_library_path("TV Shows")
        self.assertTrue(os.path.isdir(tv_path))
        self.assertTrue(tv_path.endswith("TV Shows"))

    def test_restore_larger_backups_does_not_revert_dejuddered_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            active_file = os.path.join(tmpdir, "Avatar (2022).mkv")
            bak_file = os.path.join(tmpdir, "Avatar (2022).mkv.bak")

            # Active file is larger (e.g. 5MB) than original .bak (e.g. 4MB)
            with open(active_file, "wb") as f:
                f.write(b"A" * (5 * 1024 * 1024))
            with open(bak_file, "wb") as f:
                f.write(b"B" * (4 * 1024 * 1024))

            # bak_file was 60fps (stutter), active_file is 23.98fps (de-juddered)
            def mock_probe(path, cache):
                if path.endswith(".bak"):
                    return ('H264', '720p', '60.0', '03:20', 'SRT', 'DIRECT', 'NO', 'YES')
                else:
                    return ('H264', '720p', '23.98', '03:20', 'SRT', 'DIRECT', 'NO', 'YES')

            def mock_detect(path, fps):
                if path.endswith(".bak"):
                    return 23.976
                return None

            with patch('resample_library.probe_file_meta', side_effect=mock_probe):
                with patch('resample_library.detect_stutter_framerate', side_effect=mock_detect):
                    restored = rl.restore_larger_backups(tmpdir, cache={})

            # It should NOT restore the stuttery .bak file
            self.assertEqual(len(restored), 0)
            self.assertTrue(os.path.isfile(active_file))
            self.assertEqual(os.path.getsize(active_file), 5 * 1024 * 1024)
            self.assertTrue(os.path.isfile(bak_file))


if __name__ == '__main__':
    unittest.main()



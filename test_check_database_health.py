"""
Unit tests for check_database_health.py, focusing on Rate in GB/hr calculations,
table headers, quiet mode, and file exports (CSV, JSON, TXT).
"""

import csv
import json
import os
import tempfile
import unittest

import check_database_health as cdh


class TestCheckDatabaseHealthRate(unittest.TestCase):
    def test_calculate_rate_gb_hr(self):
        # 1.02 GB for 47 minutes -> 1.30 GB/hr
        rate = cdh.calculate_rate_gb_hr(1.02, '00:47')
        self.assertEqual(rate, 1.30)

        # 3.00 GB for 2 hours -> 1.50 GB/hr
        rate = cdh.calculate_rate_gb_hr(3.00, '02:00')
        self.assertEqual(rate, 1.50)

        # 2.50 GB for 120 minutes numeric
        rate = cdh.calculate_rate_gb_hr(2.50, 120.0)
        self.assertEqual(rate, 1.25)

        # Invalid/zero cases
        self.assertIsNone(cdh.calculate_rate_gb_hr(None, '01:30'))
        self.assertIsNone(cdh.calculate_rate_gb_hr(0, '01:30'))
        self.assertIsNone(cdh.calculate_rate_gb_hr(1.5, None))
        self.assertIsNone(cdh.calculate_rate_gb_hr(1.5, '-'))
        self.assertIsNone(cdh.calculate_rate_gb_hr(1.5, 0))

    def test_format_rate_gb_hr(self):
        self.assertEqual(cdh.format_rate_gb_hr(1.3), "1.30")
        self.assertEqual(cdh.format_rate_gb_hr("0.95"), "0.95")
        self.assertEqual(cdh.format_rate_gb_hr(None), "-")
        self.assertEqual(cdh.format_rate_gb_hr("-"), "-")
        self.assertEqual(cdh.format_rate_gb_hr(0), "-")
        self.assertEqual(cdh.format_rate_gb_hr("invalid"), "-")

    def test_export_matched_file_csv_json_txt(self):
        matched_records = [
            (
                {
                    'imdb_id': 'tt0068646',
                    'title': 'The Godfather',
                    'display_title_year': 'Godfather, The (1972)',
                    'my_rating': 9.5,
                    'dvd': 1,
                    'file_time': '02:55',
                    'db_time': '02:55',
                    'dur_status': 'OK',
                    'watched': 'YES',
                    'certification': 'R',
                    'size_gb': 2.50,
                    'rate_gb_hr': 0.86
                },
                {
                    'filename': 'Godfather, The (1972).mp4',
                    'path': '/tmp/Godfather.mp4',
                    'ext': '.mp4',
                    'format': 'H264',
                    'resolution': '1080p',
                    'fps': '23.98',
                    'size_gb': 2.50,
                    'rate_gb_hr': 0.86,
                    'sub': 'SRT',
                    'jellyfin': 'DIRECT',
                    'sized': 'YES',
                    'modified': '2026-10-15 12:00'
                }
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # CSV export
            csv_path = os.path.join(tmpdir, "matched.csv")
            cdh.write_matched_file(csv_path, matched_records, 'csv')
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
            self.assertIn('GB_per_hr', rows[0])
            gb_idx = rows[0].index('GB_per_hr')
            self.assertEqual(rows[1][gb_idx], '0.86')

            # JSON export
            json_path = os.path.join(tmpdir, "matched.json")
            cdh.write_matched_file(json_path, matched_records, 'json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data[0]['gb_per_hr'], '0.86')
            self.assertEqual(data[0]['rate_gb_hr'], 0.86)

            # TXT export
            txt_path = os.path.join(tmpdir, "matched.txt")
            cdh.write_matched_file(txt_path, matched_records, 'txt')
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("[0.86 GB/h]", content)

    def test_export_missing_file_csv_json_txt(self):
        missing_movies = [
            {
                'imdb_id': 'tt0083946',
                'title': 'Fitzcarraldo',
                'display_title_year': 'Fitzcarraldo (1982)',
                'my_rating': 8.0,
                'dvd': 1,
                'time': '02:38',
                'watched': 'NO',
                'certification': 'PG'
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "missing.csv")
            cdh.write_missing_file(csv_path, missing_movies, 'csv')
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
            self.assertIn('GB_per_hr', rows[0])
            gb_idx = rows[0].index('GB_per_hr')
            self.assertEqual(rows[1][gb_idx], '-')

            json_path = os.path.join(tmpdir, "missing.json")
            cdh.write_missing_file(json_path, missing_movies, 'json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data[0]['gb_per_hr'], '-')

            txt_path = os.path.join(tmpdir, "missing.txt")
            cdh.write_missing_file(txt_path, missing_movies, 'txt')
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("[-]", content)

    def test_export_unmatched_file_csv_json_txt(self):
        unmatched_videos = [
            {
                'rel_dir': 'Extras',
                'filename': 'Making of Godfather (1972).mp4',
                'display_filename': 'Making of Godfather (1972).mp4',
                'path': '/tmp/Extras/Making of Godfather (1972).mp4',
                'ext': '.mp4',
                'format': 'H264',
                'resolution': '720p',
                'fps': '23.98',
                'size_gb': 0.75,
                'time': '00:45',
                'rate_gb_hr': 1.00,
                'sub': 'SRT',
                'jellyfin': 'DIRECT',
                'sized': 'YES'
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "unmatched.csv")
            cdh.write_unmatched_file(csv_path, unmatched_videos, 'csv')
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
            self.assertIn('GB_per_hr', rows[0])
            gb_idx = rows[0].index('GB_per_hr')
            self.assertEqual(rows[1][gb_idx], '1.00')

            json_path = os.path.join(tmpdir, "unmatched.json")
            cdh.write_unmatched_file(json_path, unmatched_videos, 'json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data[0]['gb_per_hr'], '1.00')

            txt_path = os.path.join(tmpdir, "unmatched.txt")
            cdh.write_unmatched_file(txt_path, unmatched_videos, 'txt')
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("[1.00 GB/h]", content)


class TestCheckDatabaseHealthLibrary(unittest.TestCase):
    def test_resolve_library_path_defaults(self):
        # Default when None or empty is DEFAULT_MOVIES_DIR
        self.assertEqual(cdh.resolve_library_path(None), cdh.DEFAULT_MOVIES_DIR)
        self.assertEqual(cdh.resolve_library_path(""), cdh.DEFAULT_MOVIES_DIR)
        self.assertEqual(cdh.resolve_library_path("   "), cdh.DEFAULT_MOVIES_DIR)

    def test_resolve_library_path_root_folder_name(self):
        # Folder name 'TV Shows' resolves relative to /media/daveg/Lib
        tv_path = cdh.resolve_library_path("TV Shows")
        self.assertTrue(os.path.isdir(tv_path))
        self.assertTrue(tv_path.endswith("TV Shows"))

        # Folder name 'Movies' resolves to /media/daveg/Lib/Movies
        movies_path = cdh.resolve_library_path("Movies")
        self.assertTrue(os.path.isdir(movies_path))
        self.assertTrue(movies_path.endswith("Movies"))

    def test_resolve_library_path_explicit_full_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved = cdh.resolve_library_path(tmpdir)
            self.assertEqual(resolved, os.path.abspath(tmpdir))

    def test_main_library_cli_arguments(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from unittest.mock import patch

        dummy_movies = [{
            'imdb_id': 'tt1',
            'title': 'Test Movie',
            'norm_title': 'test movie',
            'display_title': 'Test Movie',
            'display_title_year': 'Test Movie (2020)',
            'year': 2020,
            'rating': 8.0,
            'my_rating': 8.0,
            'dvd': 1,
            'watched': 'NO',
            'certification': 'R',
            'time': '01:30',
            'db_time': '01:30',
            'ext': '-',
            'format': '-',
            'resolution': '-',
            'fps': '-',
            'sub': '-',
            'jellyfin': '-',
            'sized': '-',
            'oversized': '-',
            'size_bytes': 0,
            'size_gb': '-',
            'compact_title': 'testmovie',
            'no_art_title': 'test movie'
        }]

        with tempfile.TemporaryDirectory() as tmpdir:
            f = io.StringIO()
            with redirect_stdout(f):
                with patch('check_database_health.load_db_movies', return_value=dummy_movies):
                    with patch('check_database_health.os.path.isfile', return_value=True):
                        # 1. Test --library flag
                        cdh.main("--library", tmpdir, "--skip-resolution")
            out = f.getvalue()
            self.assertIn(f"Library Directory:        {os.path.abspath(tmpdir)}", out)

            # 2. Test positional argument
            f = io.StringIO()
            with redirect_stdout(f):
                with patch('check_database_health.load_db_movies', return_value=dummy_movies):
                    with patch('check_database_health.os.path.isfile', return_value=True):
                        cdh.main(tmpdir, "--skip-resolution")
            out = f.getvalue()
            self.assertIn(f"Library Directory:        {os.path.abspath(tmpdir)}", out)

    def test_is_movies_library(self):
        self.assertTrue(cdh.is_movies_library(None))
        self.assertTrue(cdh.is_movies_library(""))
        self.assertTrue(cdh.is_movies_library(cdh.DEFAULT_MOVIES_DIR))
        self.assertTrue(cdh.is_movies_library("/media/daveg/Lib/Movies"))
        self.assertTrue(cdh.is_movies_library("/tmp/test/Movies"))
        self.assertFalse(cdh.is_movies_library("/media/daveg/Lib/TV Shows"))
        self.assertFalse(cdh.is_movies_library("TV Shows"))
        self.assertFalse(cdh.is_movies_library("/media/daveg/Lib/Videos"))
        self.assertFalse(cdh.is_movies_library("/tmp/some_dir"))

    def test_non_movies_library_skips_database(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from unittest.mock import patch, MagicMock

        mock_load_db = MagicMock()
        f = io.StringIO()
        with redirect_stdout(f):
            with patch('check_database_health.load_db_movies', mock_load_db):
                cdh.main("TV Shows", "--skip-resolution")
        out = f.getvalue()

        # Database should NOT be loaded
        mock_load_db.assert_not_called()
        # Database records and movie comparison should NOT be in output
        self.assertNotIn("IMDB_Films.db", out)
        self.assertNotIn("Missing Titles in Video Library", out)
        self.assertNotIn("Matched DB Titles", out)
        self.assertIn("TV Shows Video Library Health Report", out)
        self.assertIn("Video Library Files", out)

    def test_get_entry_colors_require_subtitles(self):
        c_red = '\033[91m'
        c_blue = '\033[94m'
        c_green = '\033[92m'
        c_orange = '\033[38;5;208m'
        c_yellow = '\033[93m'

        # Default require_subtitles=True (Movies): missing subtitles flag as blue
        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('-', '-', 'YES', require_subtitles=True)
        self.assertEqual(r_c, c_blue)
        self.assertEqual(s_c, c_blue)
        self.assertEqual(j_c, c_blue)

        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('None', '-', 'YES', require_subtitles=True)
        self.assertEqual(r_c, c_blue)
        self.assertEqual(s_c, c_blue)
        self.assertEqual(j_c, c_blue)

        # Missing subtitles + improperly sized: Blue takes precedence over Orange
        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('None', '-', 'NO', require_subtitles=True)
        self.assertEqual(r_c, c_blue)
        self.assertEqual(s_c, c_blue)
        self.assertEqual(j_c, c_blue)
        self.assertEqual(sz_c, c_orange)

        # Missing subtitles + duration mismatch: Red takes precedence over Blue
        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('None', '-', 'YES', dur_status='MISMATCH', require_subtitles=True)
        self.assertEqual(r_c, c_red)
        self.assertEqual(s_c, c_blue)
        self.assertEqual(j_c, c_blue)
        self.assertEqual(t_c, c_red)

        # require_subtitles=False (TV Shows): missing subtitles are NOT red or blue; row is clean green if sized
        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('-', '-', 'YES', require_subtitles=False)
        self.assertEqual(r_c, c_green)
        self.assertEqual(s_c, '')
        self.assertEqual(j_c, '')

        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('None', '-', 'YES', require_subtitles=False)
        self.assertEqual(r_c, c_green)
        self.assertEqual(s_c, '')
        self.assertEqual(j_c, '')

        # require_subtitles=False with oversized (NO): row is orange, subs not red or blue
        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('-', '-', 'NO', require_subtitles=False)
        self.assertEqual(r_c, c_orange)
        self.assertEqual(s_c, '')
        self.assertEqual(j_c, '')

        # require_subtitles=False with genuine desync/overrun: still flags red
        r_c, s_c, j_c, sz_c, t_c, rst = cdh.get_entry_colors('OVERRUN', 'DESYNC', 'YES', require_subtitles=False)
        self.assertEqual(r_c, c_red)
        self.assertEqual(s_c, c_red)
        self.assertEqual(j_c, c_red)

    def test_tv_shows_color_key_and_subtitles(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from unittest.mock import patch

        # TV Shows output
        f = io.StringIO()
        with redirect_stdout(f):
            cdh.main("TV Shows", "--skip-resolution")
        tv_out = f.getvalue()

        # TV Shows Color Key assertions
        self.assertIn("Note: TV shows may not have subtitles; missing subtitles are not flagged as health check failures.", tv_out)
        self.assertIn("Fails health check (desynced/overrun timestamps, or duration mismatch/split rip)", tv_out)
        self.assertNotIn("Fails health check (no subtitles", tv_out)
        self.assertNotIn("● Blue:", tv_out)

        # Movies output
        f = io.StringIO()
        dummy_movies = []
        with redirect_stdout(f):
            with patch('check_database_health.load_db_movies', return_value=dummy_movies):
                cdh.main("/media/daveg/Lib/Movies", "--skip-resolution")
        mov_out = f.getvalue()

        # Movies Color Key assertions
        self.assertIn("● Blue:", mov_out)
        self.assertIn("No subtitles (fix: run fetch_subtitles)", mov_out)
        self.assertIn("Fails health check (desynced/overrun subs, or duration mismatch/split rip)", mov_out)
        self.assertNotIn("Fails health check (no subtitles", mov_out)
        self.assertNotIn("Note: TV shows may not have subtitles", mov_out)

    def test_get_resolution_tier(self):
        self.assertEqual(cdh.get_resolution_tier('480p'), '540p')
        self.assertEqual(cdh.get_resolution_tier('540p'), '540p')
        self.assertEqual(cdh.get_resolution_tier('720p'), '720p')
        self.assertEqual(cdh.get_resolution_tier('1080p'), '1080p')
        self.assertEqual(cdh.get_resolution_tier('2160p'), '4k')
        self.assertEqual(cdh.get_resolution_tier('unknown'), 'unknown')
        self.assertEqual(cdh.get_resolution_tier('-'), 'unknown')
        self.assertEqual(cdh.get_resolution_tier(None), 'unknown')

    def test_get_resolution_target_rate(self):
        self.assertEqual(cdh.get_resolution_target_rate('480p'), 1.25)
        self.assertEqual(cdh.get_resolution_target_rate('540p'), 1.25)
        self.assertEqual(cdh.get_resolution_target_rate('720p'), 1.75)
        self.assertEqual(cdh.get_resolution_target_rate('1080p'), 3.00)
        self.assertEqual(cdh.get_resolution_target_rate('2160p'), 7.50)
        self.assertEqual(cdh.get_resolution_target_rate('-'), 2.00)

        # Custom ratio overrides resolution tier
        self.assertEqual(cdh.get_resolution_target_rate('480p', max_gb_per_hour=0.85), 0.85)
        self.assertEqual(cdh.get_resolution_target_rate('1080p', max_gb_per_hour=1.0), 1.0)

    def test_check_sized_equivalent_ratio(self):
        # 45-min SD episode (404p, target 1.25 GB/hr):
        # 1.02 GB for 47 min = 1.30 GB/hr > 1.25 -> oversized -> Sized: NO
        self.assertEqual(cdh.check_sized('404p', 1.02, '00:47:00'), 'NO')
        self.assertEqual(cdh.check_oversized('404p', 1.02, '00:47:00'), 'YES')

        # 0.28 GB for 47 min = 0.36 GB/hr < 1.25 -> properly sized -> Sized: YES
        self.assertEqual(cdh.check_sized('404p', 0.28, '00:47:00'), 'YES')
        self.assertEqual(cdh.check_oversized('404p', 0.28, '00:47:00'), 'NO')

        # 22-min SD episode (480p, target 1.25 GB/hr):
        # 0.50 GB for 22 min = 1.36 GB/hr > 1.25 -> oversized -> Sized: NO
        self.assertEqual(cdh.check_sized('480p', 0.50, '00:22:00'), 'NO')
        # 0.20 GB for 22 min = 0.55 GB/hr < 1.25 -> properly sized -> Sized: YES
        self.assertEqual(cdh.check_sized('480p', 0.20, '00:22:00'), 'YES')

        # 120-min 1080p movie (target 3.00 GB/hr):
        # 6.5 GB for 120 min = 3.25 GB/hr > 3.00 -> oversized -> Sized: NO
        self.assertEqual(cdh.check_sized('1080p', 6.5, '02:00:00'), 'NO')
        # 5.5 GB for 120 min = 2.75 GB/hr < 3.00 -> properly sized -> Sized: YES
        self.assertEqual(cdh.check_sized('1080p', 5.5, '02:00:00'), 'YES')

        # Custom ratio:
        # File at 0.90 GB/hr with ratio 0.8 -> oversized (NO)
        self.assertEqual(cdh.check_sized('480p', 0.60, '00:40:00', max_gb_per_hour=0.8), 'NO')
        # File at 0.90 GB/hr with ratio 1.5 -> properly sized (YES)
        self.assertEqual(cdh.check_sized('480p', 0.60, '00:40:00', max_gb_per_hour=1.5), 'YES')

    def test_main_ratio_cli_flag(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr

        f = io.StringIO()
        with redirect_stdout(f):
            cdh.main("TV Shows", "--ratio", "0.5", "--skip-resolution")
        out = f.getvalue()

        self.assertIn("Sizing Criteria:          Custom Ratio (0.50 GB/hr)", out)

    def test_cached_srt_deletion_detected(self):
        from unittest.mock import patch

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

            # Sidecar .srt does NOT exist on disk (was deleted)
            self.assertEqual(cdh.check_srt_file(video_path), 'NO')

            with patch('check_database_health.check_subtitles_info', return_value=('None', '-', 'NO', 'NO', 'NO')):
                meta = cdh.get_video_metadata(video_path, cache=cache)

            # Metadata should reflect that subtitles are missing, not stale 'SRT'
            self.assertEqual(meta[4], 'None')
            self.assertEqual(meta[5], '-')
            self.assertEqual(cache[cache_key]['sub'], 'None')
            self.assertEqual(cache[cache_key]['jellyfin'], '-')
            self.assertEqual(cache[cache_key]['srt'], 'NO')

    def test_is_entry_non_green(self):
        # 1. Clean green entry: Sized=YES, DIRECT subs, matched duration
        self.assertFalse(cdh.is_entry_non_green('SRT', 'DIRECT', 'YES', dur_status='OK', require_subtitles=True))
        self.assertFalse(cdh.is_entry_non_green('Text', 'DIRECT', 'YES', dur_status='OK', require_subtitles=True))

        # 2. Orange entry: Improperly sized (NO)
        self.assertTrue(cdh.is_entry_non_green('SRT', 'DIRECT', 'NO', dur_status='OK', require_subtitles=True))

        # 3. Yellow entry: Jellyfin transcode required (Bitmap subs)
        self.assertTrue(cdh.is_entry_non_green('Bitmap', 'TRANSCODE', 'YES', dur_status='OK', require_subtitles=True))

        # 4. Blue entry: Missing subtitles (require_subtitles=True)
        self.assertTrue(cdh.is_entry_non_green('None', '-', 'YES', dur_status='OK', require_subtitles=True))
        self.assertTrue(cdh.is_entry_non_green('-', '-', 'YES', dur_status='OK', require_subtitles=True))

        # 5. Blue bypassed for TV Shows (require_subtitles=False): clean if sized
        self.assertFalse(cdh.is_entry_non_green('None', '-', 'YES', dur_status='OK', require_subtitles=False))
        self.assertFalse(cdh.is_entry_non_green('-', '-', 'YES', dur_status='OK', require_subtitles=False))

        # 6. Red entry: Duration mismatch
        self.assertTrue(cdh.is_entry_non_green('SRT', 'DIRECT', 'YES', dur_status='MISMATCH', require_subtitles=True))

        # 7. Red entry: Subtitle overrun / desync
        self.assertTrue(cdh.is_entry_non_green('OVERRUN', 'DESYNC', 'YES', dur_status='OK', require_subtitles=True))

        # 8. Red entry: Incomplete multi-part
        self.assertTrue(cdh.is_entry_non_green('SRT', 'DIRECT', 'YES', dur_status='PART_1', is_multipart=True, require_subtitles=True))

        # 9. Red entry: Missing video (has_video=False)
        self.assertTrue(cdh.is_entry_non_green('-', '-', '-', has_video=False, require_subtitles=True))

    def test_main_non_green_cli_flag(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from unittest.mock import patch

        dummy_movies = [
            {
                'imdb_id': 'tt001',
                'title': 'Green Movie',
                'norm_title': 'green movie',
                'display_title': 'Green Movie',
                'display_title_year': 'Green Movie (2020)',
                'year': 2020,
                'rating': 8.0,
                'my_rating': 8.0,
                'dvd': 1,
                'watched': 'NO',
                'certification': 'R',
                'time': '01:30',
                'db_time': '01:30',
                'ext': '.mp4',
                'format': 'H264',
                'resolution': '1080p',
                'fps': '23.98',
                'sub': 'SRT',
                'jellyfin': 'DIRECT',
                'sized': 'YES',
                'oversized': 'NO',
                'size_bytes': 1024 * 1024 * 500,
                'size_gb': 0.5,
                'compact_title': 'greenmovie',
                'no_art_title': 'green movie'
            },
            {
                'imdb_id': 'tt002',
                'title': 'Orange Movie',
                'norm_title': 'orange movie',
                'display_title': 'Orange Movie',
                'display_title_year': 'Orange Movie (2021)',
                'year': 2021,
                'rating': 7.5,
                'my_rating': 7.5,
                'dvd': 2,
                'watched': 'NO',
                'certification': 'PG',
                'time': '01:30',
                'db_time': '01:30',
                'ext': '.mp4',
                'format': 'H264',
                'resolution': '1080p',
                'fps': '23.98',
                'sub': 'SRT',
                'jellyfin': 'DIRECT',
                'sized': 'NO',
                'oversized': 'YES',
                'size_bytes': 1024 * 1024 * 1024 * 6,
                'size_gb': 6.0,
                'compact_title': 'orangemovie',
                'no_art_title': 'orange movie'
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            movies_dir = os.path.join(tmpdir, "Movies")
            os.makedirs(movies_dir)
            f1 = os.path.join(movies_dir, "Green Movie (2020).mp4")
            s1 = os.path.join(movies_dir, "Green Movie (2020).en.srt")
            f2 = os.path.join(movies_dir, "Orange Movie (2021).mp4")
            s2 = os.path.join(movies_dir, "Orange Movie (2021).en.srt")
            with open(f1, "wb") as f:
                f.write(b"data")
            with open(s1, "w") as f:
                f.write("1\n00:00:01,000 --> 00:01:00,000\nHello\n")
            with open(f2, "wb") as f:
                f.write(b"data")
            with open(s2, "w") as f:
                f.write("1\n00:00:01,000 --> 00:01:00,000\nHello\n")

            # 1. With --non-green: Green Movie must be omitted, Orange Movie must appear
            buf = io.StringIO()
            with redirect_stdout(buf):
                with patch('check_database_health.os.path.isfile', return_value=True):
                    with patch('check_database_health.load_db_movies', return_value=dummy_movies):
                        with patch('check_database_health.batch_probe_metadata', return_value=[
                            ('H264', '1080p', '23.98', '01:30', 'SRT', 'DIRECT'),
                            ('H264', '720p', '23.98', '01:30', 'SRT', 'DIRECT')
                        ]):
                            with patch('check_database_health.check_sized', side_effect=lambda res, sz, tm, **kw: 'NO' if res == '720p' else 'YES'):
                                cdh.main("--library", movies_dir, "--non-green", "--show-only", "matched", "--quiet")
            out = buf.getvalue()
            self.assertIn("Orange Movie", out)
            self.assertNotIn("Green Movie", out)

            # 2. Without --non-green: Both Green Movie and Orange Movie must appear
            buf = io.StringIO()
            with redirect_stdout(buf):
                with patch('check_database_health.os.path.isfile', return_value=True):
                    with patch('check_database_health.load_db_movies', return_value=dummy_movies):
                        with patch('check_database_health.batch_probe_metadata', return_value=[
                            ('H264', '1080p', '23.98', '01:30', 'SRT', 'DIRECT'),
                            ('H264', '720p', '23.98', '01:30', 'SRT', 'DIRECT')
                        ]):
                            with patch('check_database_health.check_sized', side_effect=lambda res, sz, tm, **kw: 'NO' if res == '720p' else 'YES'):
                                cdh.main("--library", movies_dir, "--show-only", "matched", "--quiet")
            out = buf.getvalue()
            self.assertIn("Orange Movie", out)
            self.assertIn("Green Movie", out)

            # 3. Test standard tabular output header displays [NON-GREEN / ISSUES ONLY]
            buf = io.StringIO()
            with redirect_stdout(buf):
                with patch('check_database_health.os.path.isfile', return_value=True):
                    with patch('check_database_health.load_db_movies', return_value=dummy_movies):
                        with patch('check_database_health.batch_probe_metadata', return_value=[
                            ('H264', '1080p', '23.98', '01:30', 'SRT', 'DIRECT'),
                            ('H264', '720p', '23.98', '01:30', 'SRT', 'DIRECT')
                        ]):
                            with patch('check_database_health.check_sized', side_effect=lambda res, sz, tm, **kw: 'NO' if res == '720p' else 'YES'):
                                cdh.main("--library", movies_dir, "--non-green", "--show-only", "matched")
            out = buf.getvalue()
            self.assertIn("Orange Movie", out)
            self.assertNotIn("Green Movie (2020)", out)
            self.assertIn("[NON-GREEN / ISSUES ONLY]", out)


if __name__ == '__main__':
    unittest.main()

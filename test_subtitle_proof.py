import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import verify_jellyfin_subtitles as vjs
import checks_subtitles_vision as csv


class TestSubtitleProof(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.proof_dir = os.path.join(self.test_dir, "subtitle_proof")
        os.makedirs(self.proof_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_verify_movie_subtitles_saves_to_proof_dir(self):
        dummy_video = os.path.join(self.test_dir, "Test Movie (2024).m4v")
        with open(dummy_video, "wb") as f:
            f.write(b"dummy video data")

        cues = [
            {'start': 10.0, 'end': 15.0, 'mid': 12.0, 'clean_text': 'Hello world'},
            {'start': 60.0, 'end': 65.0, 'mid': 62.0, 'clean_text': 'Testing subtitles'},
            {'start': 120.0, 'end': 125.0, 'mid': 122.0, 'clean_text': 'Goodbye world'},
        ]

        def fake_capture(v_path, cue_sec, out_path, s_type, s_target):
            with open(out_path, "wb") as f:
                f.write(b"fake image data" * 100)
            return True

        with patch('verify_jellyfin_subtitles.get_subtitle_source', return_value=('sidecar_srt', 'dummy.srt', {})):
            with patch('verify_jellyfin_subtitles.extract_cues', return_value=cues):
                with patch('verify_jellyfin_subtitles.capture_subtitle_frame', side_effect=fake_capture):
                    res = vjs.verify_movie_subtitles(
                        video_path=dummy_video,
                        samples=3,
                        output_dir=self.proof_dir
                    )

        self.assertTrue(res['verified'])
        self.assertEqual(res['status'], 'PASS')
        self.assertEqual(res['cues_checked'], 3)
        self.assertEqual(res['cues_passed'], 3)
        self.assertEqual(len(res['frames']), 3)
        self.assertEqual(res['proof_dir'], self.proof_dir)

        # Check file existence in proof folder
        proof_files = sorted(os.listdir(self.proof_dir))
        self.assertEqual(len(proof_files), 3)
        self.assertTrue(proof_files[0].startswith("Test Movie (2024)_proof_01_"))
        self.assertTrue(proof_files[1].startswith("Test Movie (2024)_proof_02_"))
        self.assertTrue(proof_files[2].startswith("Test Movie (2024)_proof_03_"))

    def test_checks_subtitles_vision_passes_without_api_key(self):
        dummy_video = os.path.join(self.test_dir, "Vision Test (2024).m4v")
        with open(dummy_video, "wb") as f:
            f.write(b"dummy video data")

        cues = [{'start': 10.0, 'end': 15.0, 'mid': 12.0, 'clean_text': 'Dialogue line'}]

        def fake_capture(v_path, cue_sec, out_path, s_type, s_target):
            with open(out_path, "wb") as f:
                f.write(b"fake image data" * 100)
            return True

        with patch('verify_jellyfin_subtitles.get_subtitle_source', return_value=('sidecar_srt', 'dummy.srt', {})):
            with patch('verify_jellyfin_subtitles.extract_cues', return_value=cues):
                with patch('verify_jellyfin_subtitles.capture_subtitle_frame', side_effect=fake_capture):
                    res = csv.check_single_movie_vision(
                        video_path=dummy_video,
                        samples=1,
                        output_dir=self.proof_dir
                    )

        self.assertEqual(res['status'], 'PASS')
        self.assertIn('subtitle_proof', res['reason'])


if __name__ == '__main__':
    unittest.main()

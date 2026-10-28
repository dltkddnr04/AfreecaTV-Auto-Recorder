import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch

import recorder_core as rc


def settings():
    return {
        "check_interval": 10, "retry_max": 2, "http_timeout": 15,
        "stream_timeout": 90, "segment_timeout": 20,
        "segment_attempts": 5, "startup_timeout": 150,
        "stall_timeout": 300, "health_interval": 15, "min_free_mb": 0,
    }


class CoreTests(unittest.TestCase):
    def test_channel_ids_are_safe(self):
        self.assertEqual(rc.validated_channel("  Alpha_123 "), "alpha_123")
        for item in ("", "../root", "a/b", "a b", "x" * 65, "\x00"):
            with self.subTest(item=item), self.assertRaises(ValueError):
                rc.validated_channel(item)

    def test_invalid_timeout_fails_fast(self):
        for name, value in [("STALL_TIMEOUT", "bad"), ("CHECK_INTERVAL", "0"),
                            ("STARTUP_TIMEOUT", "-1"), ("RETRY_MAX", "999")]:
            with patch.dict(os.environ, {name: value}, clear=True):
                with self.assertRaises(ValueError):
                    rc.options_from_env()

    def test_non_hammering_retry_settings(self):
        cmd = rc.make_command("https://www.twitch.tv/channel", Path("output.capture"), settings())
        for name in ("--retry-streams", "--retry-max", "--retry-open",
                     "--http-timeout", "--stream-timeout",
                     "--stream-segment-timeout", "--stream-segment-attempts"):
            self.assertIn(name, cmd)
        self.assertEqual(cmd[-2:], ["--output", "output.capture"])
        self.assertEqual(cmd[cmd.index("--retry-max") + 1], "2")

    def test_twitch_and_soop_cli_common_core(self):
        self.assertTrue(callable(rc.serve))
        self.assertTrue(callable(rc.Recorder))

    def test_container_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "record.capture"
            path.write_bytes(b"\x47" + b"\x00" * 187 + b"\x47" + b"\x00" * 187 + b"\x47")
            self.assertEqual(rc.detect_container(path), ".ts")
            path.write_bytes(b"\x00\x00\x00\x18moof" + b"\x00" * 32)
            self.assertEqual(rc.detect_container(path), ".mp4")
            path.write_bytes(b"\x01\x02\x03")
            self.assertEqual(rc.detect_container(path), ".raw")

    def test_atomic_status_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            rc.atomic_status(path, {"state": "recording", "bytes": 42})
            self.assertEqual(json.loads(path.read_text())["bytes"], 42)
            self.assertEqual(list(Path(folder).glob(".status-*")), [])

    def test_restart_recovers_abandoned_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = rc.Recorder("streamer", "https://example.test", folder, settings())
            recorder.folder.mkdir()
            abandoned = recorder.folder / "old.capture"
            abandoned.write_bytes(b"\x47" + b"\x00" * 187 + b"\x47")
            recorder.recover()
            self.assertTrue((recorder.folder / "old.ts").exists())
            self.assertFalse(abandoned.exists())

    def test_unknown_capture_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = rc.Recorder("streamer", "https://example.test", folder, settings())
            recorder.folder.mkdir()
            abandoned = recorder.folder / "partial.capture"
            abandoned.write_bytes(b"unrecognized")
            saved = recorder.finalize(abandoned)
            self.assertEqual(saved.suffix, ".raw")
            self.assertEqual(saved.read_bytes(), b"unrecognized")

    def test_existing_target_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = rc.Recorder("streamer", "https://example.test", folder, settings())
            recorder.folder.mkdir()
            source = recorder.folder / "old.capture"
            source.write_bytes(b"original-raw")
            target = recorder.folder / "old.raw"
            target.write_bytes(b"existing")
            self.assertIsNone(recorder.finalize(source))
            self.assertEqual(target.read_bytes(), b"existing")
            self.assertTrue(source.exists())

    def test_empty_capture_not_reported_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = rc.Recorder("streamer", "https://example.test", folder, settings())
            recorder.folder.mkdir()
            source = recorder.folder / "empty.capture"
            source.touch()
            self.assertIsNone(recorder.finalize(source))
            self.assertTrue((recorder.folder / "empty.empty").exists())

    def test_startup_watchdog_restarts_stuck_child(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = rc.Recorder("streamer", "https://example.test", folder, settings())
            proc = Mock()
            proc.poll.return_value = None
            clock = [0.0]
            def advance(seconds):
                clock[0] += 50
                return False
            with patch.object(rc.time, "monotonic", side_effect=lambda: clock[0]), \
                 patch.object(recorder.stop_event, "wait", side_effect=advance), \
                 patch.object(recorder, "status"):
                code, reason = recorder._monitor(proc, Path(folder) / "no-file")
            self.assertIsNone(code)
            self.assertIn("startup watchdog", reason)

    def test_stall_watchdog_restarts_no_growth(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder) / "capture"
            capture.write_bytes(b"1234")
            recorder = rc.Recorder("streamer", "https://example.test", folder, settings())
            proc = Mock()
            proc.poll.return_value = None
            clock = [0.0]
            def advance(seconds):
                clock[0] += 90
                return False
            with patch.object(rc.time, "monotonic", side_effect=lambda: clock[0]), \
                 patch.object(recorder.stop_event, "wait", side_effect=advance), \
                 patch.object(recorder, "status"):
                code, reason = recorder._monitor(proc, capture)
            self.assertIsNone(code)
            self.assertIn("stalled watchdog", reason)

    def test_missing_executable_is_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = rc.Recorder("abc", "https://example.test", folder, settings())
            with patch.object(rc.shutil, "which", return_value=None):
                self.assertEqual(worker.run(), 1)

    def test_storage_errors_do_not_kill_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = rc.Recorder("abc", "https://example.test", folder, settings())
            def stop_on_sleep(_seconds):
                worker.stop()
                return True
            with patch.object(rc.shutil, "which", return_value="/path/streamlink"), \
                 patch.object(worker, "_check_storage", side_effect=OSError("disk full")), \
                 patch.object(worker.stop_event, "wait", side_effect=stop_on_sleep):
                self.assertEqual(worker.run(), 0)
                self.assertIn("disk full", worker.error)

    def test_stop_event_interrupts_monitor(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = rc.Recorder("abc", "https://example.test", folder, settings())
            worker.stop()
            proc = Mock()
            self.assertEqual(worker._monitor(proc, Path(folder) / "missing")[1], "stopped")

    @unittest.skipIf(os.name == "nt", "POSIX process group only")
    def test_posix_process_group_shutdown(self):
        proc = Mock(pid=1234, returncode=0)
        proc.poll.side_effect = [None]
        proc.wait.return_value = 0
        with patch.object(rc.os, "killpg") as kill:
            rc.stop_child(proc)
        kill.assert_called_once_with(1234, signal.SIGINT)

    def test_serve_missing_executable_fails_nonzero(self):
        with patch.object(rc.shutil, "which", return_value=None):
            self.assertEqual(rc.serve(["channel"], lambda n: "https://example.test/" + n), 2)

    def test_malformed_channel_does_not_create_path(self):
        self.assertEqual(rc.serve(["../outside"], lambda n: "https://example.test/" + n), 2)


if __name__ == "__main__":
    unittest.main()

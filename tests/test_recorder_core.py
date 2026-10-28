import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch

import recorder_core as core


class CoreTests(unittest.TestCase):
    def test_channel_validation(self):
        self.assertEqual(core.channel_id("Hello_2"), "hello_2")
        for value in ("", "../escape", "/tmp", "a-b", "a b", "x" * 65):
            with self.subTest(value=value), self.assertRaises(ValueError):
                core.channel_id(value)

    def test_environment_bounds(self):
        with patch.dict(os.environ, {"CHECK_INTERVAL": "0"}):
            with self.assertRaises(ValueError):
                core.settings()
        with patch.dict(os.environ, {"HTTP_TIMEOUT": "bad"}):
            with self.assertRaises(ValueError):
                core.settings()

    def test_streamlink_command_no_private_twitch_api(self):
        cmd = core.command("https://www.twitch.tv/channel", Path("test.capture"),
                           {"http": 15})
        self.assertEqual(cmd[0], "streamlink")
        self.assertEqual(cmd[-2:], ["--output", "test.capture"])
        for flag in ("--stream-timeout", "--stream-segment-timeout",
                     "--stream-segment-attempts", "--http-timeout", "--retry-open"):
            self.assertIn(flag, cmd)
        self.assertNotIn("--retry-streams", cmd)
        self.assertNotIn("gql.twitch.tv", " ".join(cmd))

    def test_file_format_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "one.capture"
            file.write_bytes(b"\x47" + b"\0" * 187 + b"\x47")
            self.assertEqual(core.output_suffix(file), ".ts")
            file.write_bytes(b"\0\0\0\x18ftypisom" + b"\0" * 20)
            self.assertEqual(core.output_suffix(file), ".mp4")
            file.write_bytes(b"\0\0\0\x18moof" + b"\0" * 20)
            self.assertEqual(core.output_suffix(file), ".mp4")
            file.write_bytes(b"unknown")
            self.assertEqual(core.output_suffix(file), ".raw")

    def test_finalize_preserves_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp) / "one.capture"
            capture.write_bytes(b"\x47" + b"\0" * 187 + b"\x47")
            output = core.finalize(capture)
            self.assertEqual(output.suffix, ".ts")
            self.assertTrue(output.exists())
            self.assertFalse(capture.exists())

    def test_unrecognized_media_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp) / "one.capture"
            capture.write_bytes(b"partial data")
            output = core.finalize(capture)
            self.assertEqual(output.suffix, ".raw")
            self.assertEqual(output.read_bytes(), b"partial data")

    def test_empty_file_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "empty.capture"
            file.touch()
            self.assertIsNone(core.finalize(file))
            self.assertFalse(file.exists())

    def test_existing_destination_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp) / "one.capture"
            capture.write_bytes(b"not media")
            target = Path(tmp) / "one.raw"
            target.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                core.finalize(capture)
            self.assertEqual(target.read_bytes(), b"existing")
            self.assertTrue(capture.exists())

    def test_invalid_channel_fails_nonzero(self):
        self.assertEqual(core.serve(["../bad"], lambda s: s), 2)

    def test_missing_streamlink_fails_nonzero(self):
        with patch.object(core.shutil, "which", return_value=None):
            self.assertEqual(core.serve(["channel"], lambda s: s), 2)

    def test_worker_catches_and_retries_errors(self):
        stop = core.threading.Event()
        def fail(*args, **kwargs):
            stop.set()
            raise OSError("network error")
        with tempfile.TemporaryDirectory() as tmp, patch.object(core, "record", side_effect=fail) as record:
            core.worker("channel", "https://twitch.tv/channel", stop,
                        {"interval": 5}, (), Path(tmp))
        self.assertEqual(record.call_count, 1)

    def test_stop_process_sends_interrupt_on_posix(self):
        if os.name == "nt":
            self.skipTest("POSIX only")
        proc = Mock(pid=1234)
        proc.poll.return_value = None
        proc.wait.return_value = 0
        with patch.object(core.os, "killpg") as kill:
            core.stop_process(proc)
        kill.assert_called_once_with(1234, signal.SIGINT)

    def test_watchdog_kills_stuck_streamlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Mock()
            fake.poll.return_value = None
            fake.returncode = -9
            clock = [0.0]
            def tick():
                clock[0] += 15
                return clock[0]
            with patch.object(core.subprocess, "Popen", return_value=fake), \
                 patch.object(core.time, "monotonic", side_effect=tick), \
                 patch.object(core, "stop_process") as kill:
                with self.assertRaisesRegex(RuntimeError, "No output progress"):
                    core.record("https://twitch.tv/channel", "channel",
                                Path(tmp), core.threading.Event(),
                                {"startup": 60, "stall": 60, "http": 15}, ())
            kill.assert_called_once_with(fake)

    def test_stopped_process_preserves_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Mock()
            fake.poll.return_value = 0
            fake.returncode = 0
            def popen(cmd, **kwargs):
                path = Path(cmd[-1])
                path.write_bytes(b"\x47" + b"\0" * 187 + b"\x47")
                return fake
            with patch.object(core.subprocess, "Popen", side_effect=popen):
                core.record("https://twitch.tv/channel", "channel",
                            Path(tmp), core.threading.Event(),
                            {"startup": 60, "stall": 60, "http": 15}, ())
            self.assertEqual(len(list(Path(tmp).glob("*.ts"))), 1)
            self.assertEqual(len(list(Path(tmp).glob("*.capture"))), 0)


if __name__ == "__main__":
    unittest.main()

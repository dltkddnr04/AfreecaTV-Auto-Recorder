import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import main


class SettingsTests(unittest.TestCase):
    def test_public_stream_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            config = main.read_settings(Path(directory))
        self.assertEqual(config["username"], "")
        self.assertEqual(config["check_interval"], 20)

    def test_credentials_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "config.json").write_text(json.dumps({"user_name": "old", "user_password": "oldpw"}))
            with patch.dict(os.environ, {"SOOP_USERNAME": "new", "SOOP_PASSWORD": "newpw"}, clear=True):
                config = main.read_settings(Path(directory))
        self.assertEqual((config["username"], config["password"]), ("new", "newpw"))

    def test_partial_credentials_and_newline_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOOP_USERNAME": "a"}, clear=True):
                with self.assertRaisesRegex(ValueError, "both"):
                    main.read_settings(Path(directory))
            with patch.dict(os.environ, {"SOOP_USERNAME": "a\nb", "SOOP_PASSWORD": "pw"}, clear=True):
                with self.assertRaisesRegex(ValueError, "newlines"):
                    main.read_settings(Path(directory))

    def test_invalid_interval_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"CHECK_INTERVAL": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CHECK_INTERVAL"):
                main.read_settings(Path(directory))


class CredentialTests(unittest.TestCase):
    def test_temporary_config_is_removed_and_private(self):
        with main.temporary_credentials("my-user", "my-password") as path:
            self.assertIsNotNone(path)
            self.assertIn("soop-username=my-user", Path(path).read_text())
            self.assertIn("soop-password=my-password", Path(path).read_text())
            if os.name != "nt":
                self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
        self.assertFalse(Path(path).exists())

    def test_no_credentials_no_temp_config(self):
        with main.temporary_credentials("", "") as path:
            self.assertIsNone(path)


class CommandTests(unittest.TestCase):
    def test_streamlink_uses_official_plugin_and_bounded_retries(self):
        settings = {
            "check_interval": 20, "retry_max": 4,
            "http_timeout": 15, "stream_timeout": 90,
            "segment_timeout": 20, "segment_attempts": 5,
        }
        command = main.build_command("abc_123", Path("out.ts"), settings, "/tmp/creds.conf")
        self.assertIn("https://play.sooplive.com/abc_123", command)
        self.assertIn("--retry-streams", command)
        self.assertIn("--stream-segment-attempts", command)
        self.assertIn("--config", command)
        self.assertNotIn("--soop-password", command)
        self.assertNotIn("my-password", command)
        self.assertEqual(command[-2:], ["--output", "out.ts"])

    def test_unique_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            first = main.make_output_path(Path(directory))
            second = main.make_output_path(Path(directory))
            self.assertNotEqual(first, second)
            self.assertEqual(first.suffix, ".ts")


class RecorderTests(unittest.TestCase):
    def make_settings(self):
        return {
            "username": "", "password": "", "check_interval": 20,
            "retry_max": 4, "http_timeout": 15, "stream_timeout": 90,
            "segment_timeout": 20, "segment_attempts": 5,
        }

    def test_failed_launch_exits_with_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = main.Recorder("abc", Path(directory), self.make_settings())
            with patch.object(main.subprocess, "Popen", side_effect=FileNotFoundError("missing")):
                self.assertEqual(recorder.run(), 1)

    def test_stop_during_backoff_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = main.Recorder("abc", Path(directory), self.make_settings())
            class FakeProcess:
                def wait(self):
                    return 1
                def poll(self):
                    return 1
            def start(*args, **kwargs):
                recorder.stop_event.set()
                return FakeProcess()
            with patch.object(main.subprocess, "Popen", side_effect=start):
                self.assertEqual(recorder.run(), 0)

    def test_signal_stops_child(self):
        class FakeProcess:
            pid = 999
            def poll(self):
                return None
        recorder = main.Recorder("abc", Path("."), self.make_settings())
        recorder.process = FakeProcess()
        with patch.object(main, "request_graceful_stop") as stop:
            recorder.stop()
        self.assertTrue(recorder.stop_event.is_set())
        stop.assert_called_once_with(recorder.process)

    def test_posix_stop_sends_interrupt_to_process_group(self):
        if os.name == "nt":
            self.skipTest("POSIX-only")
        class FakeProcess:
            pid = 1234
            def poll(self):
                return None
        with patch.object(main.os, "killpg") as kill:
            main.request_graceful_stop(FakeProcess())
        kill.assert_called_once_with(1234, signal.SIGINT)


if __name__ == "__main__":
    unittest.main()

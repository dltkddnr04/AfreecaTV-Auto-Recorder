import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import main
import recorder_core


class SoopGridCLITests(unittest.TestCase):
    def test_no_credentials_is_public_stream(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main.load_options(folder), ("", "", "", "auto"))

    def test_legacy_config_keys_map_to_grid_environment(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            (Path(folder) / "config.json").write_text(
                json.dumps({"user_name": "legacy-id", "user_password": "legacy-secret",
                            "stream_password": "broadcast-secret", "transport": "grid"}),
                encoding="utf-8",
            )
            self.assertEqual(
                main.load_options(folder),
                ("legacy-id", "legacy-secret", "broadcast-secret", "grid"),
            )

    def test_canonical_env_takes_priority(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SOOP_ACCOUNT_ID": "new-id", "SOOP_ACCOUNT_PASSWORD": "new-password",
            "SOOP_STREAM_PASSWORD": "stream", "SOOP_GRID_TRANSPORT": "hls",
            "SOOP_USERNAME": "legacy-id", "SOOP_PASSWORD": "legacy-password",
        }, clear=True):
            self.assertEqual(main.load_options(folder), ("new-id", "new-password", "stream", "hls"))

    def test_legacy_environment_remains_supported(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SOOP_USERNAME": "legacy", "SOOP_PASSWORD": "password",
        }, clear=True):
            self.assertEqual(main.load_options(folder), ("legacy", "password", "", "auto"))

    def test_unpaired_credentials_rejected(self):
        for env in (
            {"SOOP_ACCOUNT_ID": "only"},
            {"SOOP_ACCOUNT_PASSWORD": "only"},
            {"SOOP_STREAM_PASSWORD": "broadcast-only"},
        ):
            with self.subTest(env=env), tempfile.TemporaryDirectory() as folder, \
                 patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    main.load_options(folder)

    def test_invalid_transport_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SOOP_GRID_TRANSPORT": "experimental",
        }, clear=True):
            with self.assertRaises(ValueError):
                main.load_options(folder)

    def test_malformed_config_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            (Path(folder) / "config.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                main.load_options(folder)

    def test_plugin_detection_accepts_exact_plugin_name(self):
        with patch.object(main.subprocess, "run", return_value=Mock(
            returncode=0, stdout="plugins:\n  soop\n  soop_grid\n  twitch\n",
        )) as run:
            self.assertTrue(main.plugin_available())
        self.assertEqual(run.call_args.args[0], ["streamlink", "--plugins"])
        self.assertEqual(run.call_args.kwargs["timeout"], 20)

    def test_builtin_soop_only_is_not_accepted(self):
        with patch.object(main.subprocess, "run", return_value=Mock(
            returncode=0, stdout="plugins:\n  soop\n  twitch\n",
        )):
            self.assertFalse(main.plugin_available())

    def test_plugin_detection_handles_timeout(self):
        with patch.object(main.subprocess, "run", side_effect=subprocess.TimeoutExpired(
            ["streamlink", "--plugins"], 20,
        )):
            self.assertFalse(main.plugin_available())

    def test_missing_plugin_prevents_silent_hls_fallback(self):
        with patch.object(main, "load_options", return_value=("", "", "", "auto")), \
             patch.object(main, "plugin_available", return_value=False), \
             patch.object(main, "serve") as serve:
            self.assertEqual(main.main(["channel"]), 2)
        serve.assert_not_called()

    def test_default_auto_records_original_and_uses_grid_namespace(self):
        with patch.dict(os.environ, {"ENV_MARKER": "yes"}, clear=True), \
             patch.object(main, "load_options", return_value=("", "", "", "auto")), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as serve:
            self.assertEqual(main.main(["CHANNEL"]), 0)
        self.assertEqual(serve.call_args.args[0], ["CHANNEL"])
        self.assertEqual(serve.call_args.args[1]("channel"), "https://play.sooplive.com/channel")
        self.assertEqual(serve.call_args.kwargs["stream"], "original")
        self.assertEqual(serve.call_args.kwargs["extra_args"], ("--soop-grid-transport", "auto"))
        self.assertEqual(serve.call_args.kwargs["child_env"]["ENV_MARKER"], "yes")

    def test_grid_mode_requires_original(self):
        with patch.object(main, "load_options", return_value=("", "", "", "auto")), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as serve:
            main.main(["channel", "--transport", "grid"])
        self.assertEqual(serve.call_args.kwargs["stream"], "original")
        self.assertEqual(serve.call_args.kwargs["extra_args"], ("--soop-grid-transport", "grid"))

    def test_hls_mode_uses_best(self):
        with patch.object(main, "load_options", return_value=("", "", "", "auto")), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as serve:
            main.main(["channel", "--transport", "hls"])
        self.assertEqual(serve.call_args.kwargs["stream"], "best")

    def test_bno_uses_broadcast_specific_url(self):
        with patch.object(main, "load_options", return_value=("", "", "", "auto")), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as serve:
            main.main(["channel", "--bno", "12345"])
        self.assertEqual(serve.call_args.args[1]("channel"),
                         "https://play.sooplive.com/channel/12345")

    def test_multiple_channels_cannot_share_bno(self):
        with self.assertRaises(SystemExit) as cm:
            main.main(["one", "two", "--bno", "123"])
        self.assertEqual(cm.exception.code, 2)

    def test_password_only_in_child_environment(self):
        credentials = ("my-id", "super-secret", "broadcast-password", "auto")
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(main, "load_options", return_value=credentials), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as serve:
            main.main(["channel"])
            self.assertNotIn("SOOP_ACCOUNT_PASSWORD", os.environ)
        kwargs = serve.call_args.kwargs
        self.assertEqual(kwargs["child_env"]["SOOP_ACCOUNT_ID"], "my-id")
        self.assertEqual(kwargs["child_env"]["SOOP_ACCOUNT_PASSWORD"], "super-secret")
        self.assertEqual(kwargs["child_env"]["SOOP_STREAM_PASSWORD"], "broadcast-password")
        self.assertNotIn("super-secret", str(kwargs["extra_args"]))
        self.assertNotIn("--config", kwargs["extra_args"])

    def test_core_passes_original_and_child_env_to_streamlink(self):
        args = recorder_core.command(
            "https://play.sooplive.com/abc", Path("capture.ts"),
            {"http": 15}, ("--soop-grid-transport", "auto"), stream="original",
        )
        self.assertEqual(args[args.index("https://play.sooplive.com/abc") + 1], "original")
        self.assertNotIn("soop-password", " ".join(args))
        self.assertIn("--soop-grid-transport", args)

    def test_grid_child_environment_does_not_leak_into_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            event = recorder_core.threading.Event()
            proc = Mock(returncode=0)
            proc.poll.return_value = 0
            env = {"SOOP_ACCOUNT_ID": "id", "SOOP_ACCOUNT_PASSWORD": "hidden"}
            with patch.object(recorder_core.subprocess, "Popen", return_value=proc) as popen:
                recorder_core.record(
                    "https://play.sooplive.com/abc", "abc", Path(folder),
                    event, {"http": 15, "startup": 120, "stall": 180}, (),
                    stream="original", child_env=env,
                )
            self.assertEqual(popen.call_args.kwargs["env"], env)
            self.assertNotIn("hidden", " ".join(popen.call_args.args[0]))


if __name__ == "__main__":
    unittest.main()

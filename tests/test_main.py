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

    def test_compatibility_env_takes_priority_over_old_aliases(self):
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
        self.assertEqual(kwargs["child_env"]["SOOP_GRID_USERNAME"], "my-id")
        self.assertEqual(kwargs["child_env"]["SOOP_GRID_PASSWORD"], "super-secret")
        self.assertEqual(kwargs["child_env"]["SOOP_GRID_STREAM_PASSWORD"], "broadcast-password")
        self.assertNotIn("SOOP_ACCOUNT_ID", kwargs["child_env"])
        self.assertNotIn("SOOP_ACCOUNT_PASSWORD", kwargs["child_env"])
        self.assertNotIn("SOOP_STREAM_PASSWORD", kwargs["child_env"])
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


    def test_new_official_environment_overrides_compatibility_and_config(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SOOP_GRID_USERNAME": "new-user",
            "SOOP_GRID_PASSWORD": "new-pass",
            "SOOP_GRID_STREAM_PASSWORD": "new-stream",
            "SOOP_ACCOUNT_ID": "old-user",
            "SOOP_ACCOUNT_PASSWORD": "old-pass",
            "SOOP_STREAM_PASSWORD": "old-stream",
        }, clear=True):
            (Path(folder) / "config.json").write_text(
                json.dumps({"user_name": "config-user", "user_password": "config-pass",
                            "stream_password": "config-stream"}), encoding="utf-8"
            )
            self.assertEqual(
                main.load_options(folder), ("new-user", "new-pass", "new-stream", "auto")
            )

    def test_new_environment_explicit_empty_suppresses_legacy_values(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SOOP_GRID_USERNAME": "", "SOOP_GRID_PASSWORD": "",
            "SOOP_GRID_STREAM_PASSWORD": "",
            "SOOP_ACCOUNT_ID": "old-user", "SOOP_ACCOUNT_PASSWORD": "old-pass",
            "SOOP_STREAM_PASSWORD": "old-stream",
        }, clear=True):
            self.assertEqual(main.load_options(folder), ("", "", "", "auto"))

    def test_credential_pair_can_use_different_precedence_levels(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SOOP_GRID_USERNAME": "new-user",
            "SOOP_ACCOUNT_PASSWORD": "compat-pass",
        }, clear=True):
            self.assertEqual(main.load_options(folder), ("new-user", "compat-pass", "", "auto"))

    def test_canonical_account_suppresses_unpaired_legacy_credential(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "SOOP_GRID_USERNAME": "new-user", "SOOP_GRID_PASSWORD": "new-pass",
            "SOOP_ACCOUNT_ID": "legacy-without-password",
        }, clear=True):
            self.assertEqual(main.load_options(folder), ("new-user", "new-pass", "", "auto"))

    def test_hls_stream_password_only_allowed_from_new_environment(self):
        with patch.dict(os.environ, {"SOOP_GRID_STREAM_PASSWORD": "broadcast-secret"}, clear=True), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as recorder:
            self.assertEqual(main.main(["channel", "--transport", "hls"]), 0)
        self.assertEqual(recorder.call_args.kwargs["stream"], "best")
        env = recorder.call_args.kwargs["child_env"]
        self.assertEqual(env["SOOP_GRID_STREAM_PASSWORD"], "broadcast-secret")
        self.assertNotIn("SOOP_GRID_USERNAME", env)
        self.assertNotIn("SOOP_GRID_PASSWORD", env)

    def test_hls_stream_password_only_allowed_from_old_environment(self):
        with patch.dict(os.environ, {"SOOP_STREAM_PASSWORD": "legacy-secret"}, clear=True), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as recorder:
            self.assertEqual(main.main(["channel", "--transport", "hls"]), 0)
        self.assertEqual(
            recorder.call_args.kwargs["child_env"]["SOOP_GRID_STREAM_PASSWORD"], "legacy-secret"
        )
        self.assertNotIn("SOOP_STREAM_PASSWORD", recorder.call_args.kwargs["child_env"])

    def test_hls_password_only_from_config(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            (Path(folder) / "config.json").write_text(
                json.dumps({"stream_password": "config-secret", "transport": "hls"}),
                encoding="utf-8",
            )
            self.assertEqual(main.load_options(folder), ("", "", "config-secret", "hls"))

    def test_password_only_requires_hls_when_auto_or_grid(self):
        for mode in ("auto", "grid"):
            with self.subTest(mode=mode), \
                 patch.dict(os.environ, {"SOOP_GRID_STREAM_PASSWORD": "broadcast-secret"}, clear=True), \
                 patch.object(main, "plugin_available") as available, \
                 patch.object(main, "serve") as recorder:
                with self.assertRaises(SystemExit) as result:
                    main.main(["channel", "--transport", mode])
                self.assertEqual(result.exception.code, 2)
                recorder.assert_not_called()
                available.assert_not_called()

    def test_cli_transport_override_allows_hls_password_only(self):
        with patch.dict(os.environ, {
            "SOOP_GRID_STREAM_PASSWORD": "broadcast-secret",
            "SOOP_GRID_TRANSPORT": "grid",
        }, clear=True), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as recorder:
            self.assertEqual(main.main(["channel", "--transport", "hls"]), 0)
        self.assertEqual(recorder.call_args.kwargs["extra_args"],
                         ("--soop-grid-transport", "hls"))

    def test_normalization_clears_inherited_old_aliases(self):
        with patch.dict(os.environ, {
            "SOOP_GRID_USERNAME": "new-id", "SOOP_GRID_PASSWORD": "new-pass",
            "SOOP_ACCOUNT_ID": "old-id", "SOOP_ACCOUNT_PASSWORD": "old-pass",
            "SOOP_USERNAME": "older-id", "SOOP_PASSWORD": "older-pass",
            "SOOP_GRID_STREAM_PASSWORD": "",
            "SOOP_STREAM_PASSWORD": "older-stream",
        }, clear=True), \
             patch.object(main, "plugin_available", return_value=True), \
             patch.object(main, "serve", return_value=0) as recorder:
            self.assertEqual(main.main(["channel"]), 0)
        env = recorder.call_args.kwargs["child_env"]
        self.assertEqual(env["SOOP_GRID_USERNAME"], "new-id")
        self.assertEqual(env["SOOP_GRID_PASSWORD"], "new-pass")
        for key in ("SOOP_ACCOUNT_ID", "SOOP_ACCOUNT_PASSWORD", "SOOP_USERNAME",
                    "SOOP_PASSWORD", "SOOP_STREAM_PASSWORD", "SOOP_GRID_STREAM_PASSWORD"):
            self.assertNotIn(key, env)


if __name__ == "__main__":
    unittest.main()

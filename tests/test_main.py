import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main


class CLIConfigurationTests(unittest.TestCase):
    def test_public_without_credentials(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main.read_credentials(Path(d)), ("", ""))

    def test_mismatched_credentials_rejected(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"SOOP_USERNAME": "only"}, clear=True):
            with self.assertRaises(ValueError):
                main.read_credentials(Path(d))

    def test_secrets_never_in_command_line(self):
        with main.private_config("user", "secret") as path:
            self.assertIsNotNone(path)
            self.assertIn("soop-password=secret", Path(path).read_text())
            if os.name != "nt":
                self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
        self.assertFalse(Path(path).exists())

    def test_no_secrets_does_not_create_config(self):
        with main.private_config("", "") as config:
            self.assertIsNone(config)

    def test_cli_uses_supervisor(self):
        with patch.object(main, "read_credentials", return_value=("", "")), \
             patch.object(main, "serve", return_value=7) as run:
            self.assertEqual(main.main(["Channel_A", "Channel_B"]), 7)
        self.assertEqual(run.call_args.args[0], ["Channel_A", "Channel_B"])
        self.assertEqual(run.call_args.args[1]("alpha"), "https://play.sooplive.com/alpha")


if __name__ == "__main__":
    unittest.main()

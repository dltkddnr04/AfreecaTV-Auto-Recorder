"""CLI-only SOOP automatic recorder, supervised by recorder_core."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile

from recorder_core import serve


def read_credentials(project_dir):
    config_file = Path(project_dir) / "config.json"
    settings = {}
    if config_file.exists():
        with config_file.open("r", encoding="utf-8") as f:
            settings = json.load(f)
        if not isinstance(settings, dict):
            raise ValueError("config.json must contain a JSON object")
    username = os.environ.get("SOOP_USERNAME", settings.get("user_name", ""))
    password = os.environ.get("SOOP_PASSWORD", settings.get("user_password", ""))
    if not all(isinstance(value, str) for value in (username, password)):
        raise ValueError("SOOP username and password must be strings")
    if bool(username) != bool(password):
        raise ValueError("Set both SOOP_USERNAME and SOOP_PASSWORD, or neither")
    if any(c in value for value in (username, password) for c in ("\n", "\r", "\x00")):
        raise ValueError("Credentials cannot contain newline or NUL")
    return username, password


@contextmanager
def private_config(username, password):
    if not username:
        yield None
        return
    fd, path = tempfile.mkstemp(prefix="soop-streamlink-", suffix=".conf")
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"soop-username={username}\nsoop-password={password}\n")
        yield path
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unattended SOOP CLI recorder")
    parser.add_argument("channels", nargs="*", help="SOOP channel IDs")
    args = parser.parse_args(argv)
    channels = args.channels
    if not channels and sys.stdin.isatty():
        value = input("SOOP channel ID (Enter to exit): ").strip()
        if not value:
            return 0
        channels = [value]
    if not channels:
        parser.error("Provide at least one SOOP channel ID")

    try:
        username, password = read_credentials(Path(__file__).resolve().parent)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(f"Invalid credentials configuration: {exc}")
    with private_config(username, password) as path:
        extra = ["--config", path] if path else []
        return serve(channels, lambda channel: f"https://play.sooplive.com/{channel}", extra_args=extra)


if __name__ == "__main__":
    sys.exit(main())

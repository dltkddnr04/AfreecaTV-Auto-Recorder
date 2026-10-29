"""Minimal SOOP CLI for the sideloaded source.soop Streamlink plugin."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from recorder_core import serve

TRANSPORTS = ("auto", "grid", "hls")


def load_options(project_dir):
    """Normalize supported settings to the current soop_grid credential contract."""
    path = Path(project_dir) / "config.json"
    config = {}
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config, dict):
            raise ValueError("config.json must contain a JSON object")

    def option(env_names, config_key, default=""):
        for name in env_names:
            if name in os.environ:
                return os.environ[name]
        return config.get(config_key, default)

    # Follow the plugin's priority: canonical > compatibility alias > config.
    # Presence (even an empty string) suppresses lower-priority values.
    account = option(("SOOP_GRID_USERNAME", "SOOP_ACCOUNT_ID", "SOOP_USERNAME"), "user_name")
    password = option(("SOOP_GRID_PASSWORD", "SOOP_ACCOUNT_PASSWORD", "SOOP_PASSWORD"), "user_password")
    stream_password = option(("SOOP_GRID_STREAM_PASSWORD", "SOOP_STREAM_PASSWORD"), "stream_password")
    transport = option(("SOOP_GRID_TRANSPORT",), "transport", "auto")
    for name, value in (("user_name", account), ("user_password", password),
                        ("stream_password", stream_password), ("transport", transport)):
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError(f"{name} must be a valid string")
    if bool(account) != bool(password):
        raise ValueError("SOOP account ID and password must be paired")
    if transport not in TRANSPORTS:
        raise ValueError("SOOP transport must be auto, grid or hls")
    return account, password, stream_password, transport


def plugin_available():
    """Fail fast instead of silently recording via Streamlink's built-in SOOP plugin."""
    try:
        result = subprocess.run(
            ["streamlink", "--plugins"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and re.search(
        r"(?<![a-zA-Z0-9_])soop_grid(?![a-zA-Z0-9_])", result.stdout
    ) is not None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="SOOP auto recorder using installed source.soop Native Grid Streamlink plugin"
    )
    parser.add_argument("channels", nargs="+", help="SOOP channel IDs")
    parser.add_argument(
        "--transport", choices=TRANSPORTS,
        help="auto (Grid first, limited HLS fallback), grid (Native Grid only), hls (official SOOP)",
    )
    parser.add_argument(
        "--bno", help="Broadcast number; only supported when recording one channel"
    )
    args = parser.parse_args(argv)

    if args.bno is not None:
        if len(args.channels) != 1 or not args.bno.isascii() or not args.bno.isdecimal() or int(args.bno) == 0:
            parser.error("--bno requires one channel and a positive numeric broadcast number")

    try:
        account, password, stream_password, default_transport = load_options(
            Path(__file__).resolve().parent
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"Invalid SOOP configuration: {exc}")

    transport = args.transport or default_transport
    # Native Grid requires account credentials for password-protected streams.
    # The built-in SOOP plugin delegated to by hls permits stream-password only.
    if stream_password and not account and transport != "hls":
        parser.error("Broadcast-password-only mode requires --transport hls")
    if not plugin_available():
        print(
            "Required Streamlink plugin 'soop_grid' is unavailable. "
            "Install source.soop/tests/streamlink-grid-poc/dist/soop_grid.py "
            "as the Streamlink user plugin 'soop_grid.py'.",
            file=sys.stderr, flush=True,
        )
        return 2

    # Pass exactly one normalized credential namespace to the plugin.
    # Remove inherited aliases to prevent stale settings from overriding config.
    # Secrets never appear in process argv, temporary files, or logs.
    child_env = os.environ.copy()
    for key in (
        "SOOP_GRID_USERNAME", "SOOP_GRID_PASSWORD", "SOOP_GRID_STREAM_PASSWORD",
        "SOOP_ACCOUNT_ID", "SOOP_ACCOUNT_PASSWORD", "SOOP_STREAM_PASSWORD",
        "SOOP_USERNAME", "SOOP_PASSWORD",
    ):
        child_env.pop(key, None)
    if account:
        child_env["SOOP_GRID_USERNAME"] = account
        child_env["SOOP_GRID_PASSWORD"] = password
    if stream_password:
        child_env["SOOP_GRID_STREAM_PASSWORD"] = stream_password

    def channel_url(channel):
        url = f"https://play.sooplive.com/{channel}"
        return f"{url}/{args.bno}" if args.bno else url

    return serve(
        args.channels, channel_url,
        extra_args=("--soop-grid-transport", transport),
        stream="best" if transport == "hls" else "original",
        child_env=child_env,
    )


if __name__ == "__main__":
    sys.exit(main())

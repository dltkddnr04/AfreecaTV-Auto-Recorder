"""Unattended SOOP live-stream recording using Streamlink's maintained plugin.

Streamlink owns authentication, CDN routing, and HLS recovery. This wrapper owns
per-recording output files, process supervision, and shutdown/retry policy.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4


DEFAULT_CHECK_INTERVAL = 20
DEFAULT_RETRY_MAX = 4
DEFAULT_HTTP_TIMEOUT = 15
DEFAULT_STREAM_TIMEOUT = 90
DEFAULT_SEGMENT_TIMEOUT = 20
DEFAULT_SEGMENT_ATTEMPTS = 5
INITIAL_BACKOFF = 10
MAX_BACKOFF = 300
SHUTDOWN_TIMEOUT = 10


def log(message):
    print(f"[{datetime.now():%Y-%m-%dT%H-%M-%S}] {message}", flush=True)


def positive_int(raw, name, minimum=1, maximum=3600):
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def read_settings(project_dir):
    """Load credentials without requiring them for public streams."""
    path = project_dir / "config.json"
    data = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("config.json must contain a JSON object")

    username = os.environ.get("SOOP_USERNAME", data.get("user_name", ""))
    password = os.environ.get("SOOP_PASSWORD", data.get("user_password", ""))
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("SOOP credentials must be strings")
    if bool(username) != bool(password):
        raise ValueError("Set both SOOP username and password, or neither")
    for item in (username, password):
        if "\n" in item or "\r" in item or "\x00" in item:
            raise ValueError("SOOP credentials must not contain newlines or NUL bytes")

    return {
        "username": username,
        "password": password,
        "check_interval": positive_int(os.environ.get("CHECK_INTERVAL", DEFAULT_CHECK_INTERVAL), "CHECK_INTERVAL", 5, 300),
        "retry_max": positive_int(os.environ.get("RETRY_MAX", DEFAULT_RETRY_MAX), "RETRY_MAX", 1, 20),
        "http_timeout": positive_int(os.environ.get("HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT), "HTTP_TIMEOUT", 5, 120),
        "stream_timeout": positive_int(os.environ.get("STREAM_TIMEOUT", DEFAULT_STREAM_TIMEOUT), "STREAM_TIMEOUT", 10, 600),
        "segment_timeout": positive_int(os.environ.get("SEGMENT_TIMEOUT", DEFAULT_SEGMENT_TIMEOUT), "SEGMENT_TIMEOUT", 5, 120),
        "segment_attempts": positive_int(os.environ.get("SEGMENT_ATTEMPTS", DEFAULT_SEGMENT_ATTEMPTS), "SEGMENT_ATTEMPTS", 1, 10),
    }


@contextmanager
def temporary_credentials(username, password):
    """Keep account credentials out of process command lines and logs.

    POSIX mkstemp uses mode 0600. The file exists only while this process runs.
    """
    if not username:
        yield None
        return

    fd, path = tempfile.mkstemp(prefix="soop-streamlink-", suffix=".conf")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as config:
            config.write(f"soop-username={username}\nsoop-password={password}\n")
        yield path
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def make_output_path(recordings_dir):
    # A random suffix prevents Streamlink from prompting to overwrite or
    # replacing an earlier partial recording after a quick reconnect.
    return recordings_dir / f"{datetime.now():%Y-%m-%dT%H-%M-%S}-{uuid4().hex[:8]}.ts"


def build_command(channel, output_path, settings, credentials_file=None):
    command = [
        "streamlink",
        "--http-timeout", str(settings["http_timeout"]),
        "--stream-timeout", str(settings["stream_timeout"]),
        "--stream-segment-timeout", str(settings["segment_timeout"]),
        "--stream-segment-attempts", str(settings["segment_attempts"]),
        "--retry-streams", str(settings["check_interval"]),
        "--retry-max", str(settings["retry_max"]),
        "--retry-open", "3",
        "--skip",  # Never overwrite an existing partial recording.
    ]
    if credentials_file:
        command += ["--config", credentials_file]
    command += [f"https://play.sooplive.com/{channel}", "best", "--output", str(output_path)]
    return command


def request_graceful_stop(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
    except (OSError, ProcessLookupError, ValueError):
        try:
            process.terminate()
        except OSError:
            pass


def finish_process(process):
    if process.poll() is not None:
        return
    request_graceful_stop(process)
    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT)
        return
    except subprocess.TimeoutExpired:
        log("Streamlink did not exit gracefully; terminating")
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log("Streamlink did not terminate; killing")
        process.kill()
        process.wait()


class Recorder:
    def __init__(self, channel, recordings_dir, settings):
        self.channel = channel
        self.recordings_dir = recordings_dir
        self.settings = settings
        self.stop_event = threading.Event()
        self.process = None

    def stop(self):
        self.stop_event.set()
        if self.process is not None:
            request_graceful_stop(self.process)

    def run(self):
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        backoff = INITIAL_BACKOFF
        log(f"Monitoring {self.channel} (SOOP plugin; Ctrl+C to stop)")
        with temporary_credentials(self.settings["username"], self.settings["password"]) as credentials_file:
            while not self.stop_event.is_set():
                output_path = make_output_path(self.recordings_dir)
                command = build_command(self.channel, output_path, self.settings, credentials_file)
                started = time.monotonic()
                return_code = None
                try:
                    options = {"start_new_session": True} if os.name != "nt" else {
                        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                    }
                    self.process = subprocess.Popen(command, **options)
                    # The stop signal may have arrived while Popen was starting.
                    if self.stop_event.is_set():
                        request_graceful_stop(self.process)
                    return_code = self.process.wait()
                except OSError as exc:
                    # This can also be a transient OS error. Log it, then back off.
                    log(f"Unable to launch Streamlink: {exc}")
                    if isinstance(exc, FileNotFoundError):
                        log("Install Streamlink with: python -m pip install -r requirements.txt")
                        return 1
                finally:
                    if self.process is not None:
                        finish_process(self.process)
                        self.process = None

                if self.stop_event.is_set():
                    break
                duration = time.monotonic() - started
                bytes_written = output_path.stat().st_size if output_path.exists() else 0
                if return_code == 0 and bytes_written:
                    log(f"Recording ended: {output_path.name} ({bytes_written} bytes)")
                else:
                    log(f"Streamlink exited with code {return_code}; will retry (recorded {bytes_written} bytes)")

                # A session that ran for a while resets the backoff. Repeated
                # short failures instead grow the delay to avoid hammering SOOP.
                if duration >= 60:
                    backoff = INITIAL_BACKOFF
                delay = max(5, backoff)
                log(f"Rechecking in {delay}s")
                self.stop_event.wait(delay)
                if duration < 60:
                    backoff = min(backoff * 2, MAX_BACKOFF)
        log("Recorder stopped")
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unattended SOOP recorder")
    parser.add_argument("channel", nargs="?", help="SOOP channel ID (not display name)")
    args = parser.parse_args(argv)
    channel = args.channel
    if not channel and sys.stdin.isatty():
        channel = input("SOOP channel ID (Enter to exit): ").strip()
    if not channel:
        if sys.stdin.isatty():
            return 0
        parser.error("Specify the channel ID as an argument in non-interactive mode")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", channel):
        parser.error("Channel ID must consist of letters, digits or underscores")

    try:
        settings = read_settings(Path(__file__).resolve().parent)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"Invalid configuration: {exc}")
    if shutil.which("streamlink") is None:
        parser.error("Streamlink is not installed or not on PATH")

    recorder = Recorder(channel, Path.cwd() / channel, settings)

    def stop_handler(_signum, _frame):
        recorder.stop()

    signal.signal(signal.SIGINT, stop_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_handler)
    try:
        return recorder.run()
    finally:
        recorder.stop()


if __name__ == "__main__":
    sys.exit(main())

"""Unattended Streamlink process supervisor (stdlib only).

Designed for CLI use: bounded startup/stall watchdog, frequent offline probing,
crash recovery of staging files, atomic heartbeat status and graceful shutdown.
The recorded media is not independently validated for completeness.
"""
import argparse
from datetime import datetime, timezone
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
import uuid

CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
MEDIA_SUFFIX = {".ts", ".mp4", ".raw"}
POLL_SECONDS = 0.5


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message):
    print(f"[{now_iso()}] {message}", flush=True)


def validated_channel(value):
    value = str(value).strip().lower()
    if not CHANNEL_RE.fullmatch(value):
        raise ValueError("Channel ID must contain only letters, digits and underscores (1-64)")
    return value


def env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def options_from_env():
    return {
        "check_interval": env_int("CHECK_INTERVAL", 10, 5, 60),
        "retry_max": env_int("RETRY_MAX", 2, 1, 10),
        "http_timeout": env_int("HTTP_TIMEOUT", 15, 5, 120),
        "stream_timeout": env_int("STREAM_TIMEOUT", 90, 10, 600),
        "segment_timeout": env_int("SEGMENT_TIMEOUT", 20, 5, 120),
        "segment_attempts": env_int("SEGMENT_ATTEMPTS", 5, 1, 10),
        "startup_timeout": env_int("STARTUP_TIMEOUT", 150, 30, 1200),
        "stall_timeout": env_int("STALL_TIMEOUT", 300, 60, 3600),
        "health_interval": env_int("HEALTH_INTERVAL", 15, 5, 120),
        "min_free_mb": env_int("MIN_FREE_MB", 256, 0, 102400),
    }


def make_command(channel_url, path, options, extra_args=()):
    return [
        "streamlink",
        "--http-timeout", str(options["http_timeout"]),
        "--stream-timeout", str(options["stream_timeout"]),
        "--stream-segment-timeout", str(options["segment_timeout"]),
        "--stream-segment-attempts", str(options["segment_attempts"]),
        "--retry-streams", str(options["check_interval"]),
        "--retry-max", str(options["retry_max"]),
        "--retry-open", "3",
        "--skip", *extra_args,
        channel_url, "best", "--output", str(path),
    ]


def detect_container(path):
    with path.open("rb") as f:
        data = f.read(4096)
    if len(data) >= 8 and data[4:8] in (b"ftyp", b"styp", b"moof"):
        return ".mp4"
    if len(data) >= 377 and all(data[i] == 0x47 for i in (0, 188, 376)):
        return ".ts"
    if len(data) >= 189 and data[0] == data[188] == 0x47:
        return ".ts"
    return ".raw"


def stop_child(proc):
    """Stop a child process. Only this supervisor waits on/reaps the child."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGINT)
    except (OSError, ValueError):
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=8)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=4)
    except OSError:
        pass


def subprocess_options():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def atomic_status(path, payload):
    """Write inspection status without ever leaving a half-written JSON file."""
    fd, temporary = tempfile.mkstemp(prefix=".status-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Recorder:
    def __init__(self, channel, url, output_root=None, options=None, extra_args=(), reporter=log):
        self.channel = validated_channel(channel)
        self.url = url
        self.root = Path(output_root or Path.cwd()).resolve()
        self.folder = self.root / self.channel
        self.opts = options if options is not None else options_from_env()
        self.extra_args = tuple(extra_args)
        self.reporter = reporter
        self.stop_event = threading.Event()
        self._child = None
        self._status_last_write = 0
        self._last_status = {}
        self.error = None
        self.last_progress = None
        self.attempts = 0

    def report(self, message):
        try:
            self.reporter(f"[{self.channel}] {message}")
        except Exception:
            # A broken logger must not take the recorder out of service.
            try:
                print(f"[{self.channel}] {message}", file=sys.stderr, flush=True)
            except OSError:
                pass

    def stop(self):
        self.stop_event.set()

    def status(self, state, bytes_written=0, output=None, error=None, force=False):
        stamp = time.monotonic()
        if not force and stamp - self._status_last_write < self.opts["health_interval"]:
            return
        self._status_last_write = stamp
        info = {
            "channel": self.channel, "pid": os.getpid(), "updated_at": now_iso(),
            "state": state, "attempts": self.attempts,
            "bytes_written": bytes_written,
            "output": str(output) if output else None,
            "last_progress": self.last_progress,
            "last_error": error or self.error,
        }
        self._last_status = info
        try:
            atomic_status(self.folder / ".recorder-status.json", info)
        except OSError as exc:
            self.report(f"Unable to write status: {exc}")

    def _check_storage(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self.folder).free
        if free < self.opts["min_free_mb"] * 1024 * 1024:
            raise OSError(f"Not enough free space ({free // (1024 * 1024)} MiB)")
        # Check write permissions on each attempt, not only at startup.
        with tempfile.TemporaryFile(dir=self.folder):
            pass

    def finalize(self, staging):
        if not staging.exists():
            return None
        if not staging.is_file():
            raise OSError(f"Non-regular staging entry: {staging}")
        if staging.stat().st_size == 0:
            # An empty capture cannot contain media; retain it for diagnostics.
            empty = staging.with_suffix(".empty")
            if not empty.exists():
                staging.rename(empty)
            return None
        suffix = detect_container(staging)
        target = staging.with_suffix(suffix)
        if target.exists():
            self.report(f"Destination exists; leaving unmodified capture: {staging}")
            return None
        staging.rename(target)
        self.report(f"Preserved {target.name} ({target.stat().st_size} bytes; integrity unverified)")
        return target

    def recover(self):
        for staging in sorted(self.folder.glob("*.capture")):
            try:
                self.finalize(staging)
            except OSError as exc:
                self.report(f"Recovery failed for {staging.name}: {exc}")

    def _monitor(self, proc, staging):
        started = time.monotonic()
        last_growth = started
        previous_size = 0
        ever_written = False
        while not self.stop_event.is_set():
            if proc.poll() is not None:
                return proc.returncode, None
            try:
                size = staging.stat().st_size if staging.exists() else 0
            except OSError as exc:
                return None, f"Unable to inspect capture: {exc}"
            if size > previous_size:
                previous_size = size
                ever_written = True
                last_growth = time.monotonic()
                self.last_progress = now_iso()
            elapsed = time.monotonic() - (last_growth if ever_written else started)
            self.status("recording" if ever_written else "waiting", size, staging)
            limit = self.opts["stall_timeout"] if ever_written else self.opts["startup_timeout"]
            if elapsed > limit:
                return None, f"{'stalled' if ever_written else 'startup'} watchdog after {int(elapsed)}s"
            self.stop_event.wait(POLL_SECONDS)
        return None, "stopped"

    def _attempt(self):
        staging = self.folder / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex}.capture"
        command = make_command(self.url, staging, self.opts, self.extra_args)
        self.attempts += 1
        self.status("starting", output=staging, force=True)
        proc = None
        result, reason = None, None
        try:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                    **subprocess_options())
            self._child = proc
            result, reason = self._monitor(proc, staging)
        except OSError as exc:
            reason = f"Streamlink launch failure: {exc}"
        finally:
            if proc is not None:
                try:
                    stop_child(proc)
                except Exception as exc:
                    self.report(f"Child process shutdown failure: {exc}")
            self._child = None
        saved = self.finalize(staging)
        if reason and reason != "stopped":
            self.error = reason
            self.report(reason)
        elif result not in (None, 0):
            self.error = f"Streamlink exited ({result}); see Streamlink stderr"
            self.report(self.error)
        elif saved:
            self.error = None
            self.report("Recording ended; monitoring resumes")
        return result, saved

    def run(self):
        try:
            if shutil.which("streamlink") is None:
                raise RuntimeError("streamlink executable missing from PATH")
            self.folder.mkdir(parents=True, exist_ok=True)
            self.recover()
            self.report("Monitoring enabled")
            while not self.stop_event.is_set():
                try:
                    self._check_storage()
                    self.recover()
                    self._attempt()
                except (OSError, ValueError, RuntimeError) as exc:
                    self.error = f"Recorder error: {exc}"
                    self.report(self.error)
                except Exception as exc:
                    # Report unexpected exceptions rather than silently losing
                    # the only supervisor for this channel.
                    self.error = f"Unexpected recorder error ({type(exc).__name__}): {exc}"
                    self.report(self.error)
                if not self.stop_event.is_set():
                    self.status("retrying", error=self.error, force=True)
                    # Fixed short delay even for repeated offline checks:
                    # do not grow to 5 minutes and miss brief broadcasts.
                    self.stop_event.wait(self.opts["check_interval"])
            self.status("stopped", force=True)
            self.report("Stopped")
            return 0
        except Exception as exc:
            self.error = f"Fatal supervisor failure ({type(exc).__name__}): {exc}"
            self.report(self.error)
            return 1


def serve(channels, url_factory, output_root=None, extra_args=(), settings=None):
    """CLI main. Dead workers are restarted; fatal startup exits nonzero."""
    try:
        names = list(dict.fromkeys(validated_channel(c) for c in channels))
        if not names:
            raise ValueError("At least one channel required")
        opts = settings or options_from_env()
        if shutil.which("streamlink") is None:
            raise RuntimeError("streamlink executable missing from PATH")
    except (ValueError, RuntimeError) as exc:
        log(f"Configuration error: {exc}")
        return 2

    stopping = threading.Event()
    workers = {}
    threads = {}
    next_restart = {}

    def signal_handler(_signum, _frame):
        stopping.set()
        for worker in list(workers.values()):
            worker.stop()

    try:
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, signal_handler)
    except ValueError:
        # This can happen if called outside the main Python thread in tests.
        pass

    def spawn(name):
        worker = Recorder(name, url_factory(name), output_root, opts, extra_args)
        thread = threading.Thread(target=worker.run, name=f"record-{name}", daemon=False)
        workers[name] = worker
        threads[name] = thread
        thread.start()
        log(f"[{name}] Worker started")

    return_code = 0
    try:
        for name in names:
            spawn(name)
        while not stopping.wait(1):
            for name in names:
                thread = threads.get(name)
                if thread is not None and thread.is_alive():
                    continue
                if time.monotonic() < next_restart.get(name, 0):
                    continue
                log(f"[{name}] Worker unexpectedly stopped; restarting")
                spawn(name)
                next_restart[name] = time.monotonic() + 10
    except KeyboardInterrupt:
        stopping.set()
        return_code = 0
    except Exception as exc:
        log(f"Fatal CLI supervisor failure: {exc}")
        return_code = 1
    else:
        return_code = 0
    finally:
        stopping.set()
        for worker in list(workers.values()):
            worker.stop()
        for thread in list(threads.values()):
            if thread.ident is None:
                continue
            try:
                thread.join(timeout=20)
            except RuntimeError as exc:
                log(f"Unable to join worker thread: {exc}")
                return_code = 1
        alive = [name for name, thread in threads.items() if thread.is_alive()]
        if alive:
            log(f"Shutdown incomplete; workers still alive: {', '.join(alive)}")
            return_code = 1
    return return_code

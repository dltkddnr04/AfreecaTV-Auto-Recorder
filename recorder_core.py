"""Small, resilient CLI wrapper around Streamlink. No Twitch/SOOP API code."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime

POLL_SECONDS = 0.5


def channel_id(value):
    name = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{1,64}", name):
        raise ValueError("Channel ID must be 1-64 ASCII letters, digits or underscores")
    return name


def setting(name, default, lower, upper):
    try:
        number = int(os.environ.get(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not lower <= number <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return number


def settings():
    return {
        "interval": setting("CHECK_INTERVAL", 10, 5, 120),
        "startup": setting("STARTUP_TIMEOUT", 120, 30, 1200),
        "stall": setting("STALL_TIMEOUT", 180, 60, 3600),
        "http": setting("HTTP_TIMEOUT", 15, 5, 120),
    }


def command(url, destination, config, extra=()):
    # Streamlink owns source discovery, HLS, retries within segments, and CDN.
    return [
        "streamlink", "--http-timeout", str(config["http"]),
        "--stream-timeout", "60", "--stream-segment-timeout", "20",
        "--stream-segment-attempts", "5", "--retry-open", "2",
        "--skip", *extra, url, "best", "--output", str(destination),
    ]


def output_suffix(path):
    with path.open("rb") as file:
        head = file.read(376)
    if len(head) >= 8 and head[4:8] in (b"ftyp", b"styp", b"moof"):
        return ".mp4"
    if len(head) >= 189 and head[0] == head[188] == 0x47:
        return ".ts"
    return ".raw"


def finalize(path):
    """Keep partial media, even after Streamlink fails. Never overwrite."""
    if not path.is_file():
        return None
    if path.stat().st_size == 0:
        path.unlink()
        return None
    target = path.with_suffix(output_suffix(path))
    if target.exists():
        raise FileExistsError(f"Output already exists: {target}")
    path.rename(target)
    return target


def process_flags():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def stop_process(proc):
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGINT)
        proc.wait(timeout=7)
        return
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)
    except OSError:
        pass


def record(url, channel, folder, stop, config, extra):
    capture = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex}.capture"
    proc = None
    problem = None
    try:
        proc = subprocess.Popen(
            command(url, capture, config, extra), stdin=subprocess.DEVNULL,
            **process_flags(),
        )
        start = growth = time.monotonic()
        last_size = 0
        while not stop.is_set() and proc.poll() is None:
            size = capture.stat().st_size if capture.exists() else 0
            if size > last_size:
                last_size, growth = size, time.monotonic()
            timeout = config["stall"] if last_size else config["startup"]
            if time.monotonic() - (growth if last_size else start) > timeout:
                problem = f"No output progress for {timeout}s"
                break
            stop.wait(POLL_SECONDS)
    finally:
        if proc is not None:
            stop_process(proc)
        try:
            output = finalize(capture)
            if output:
                print(f"[{channel}] Saved {output} (not integrity-verified)", flush=True)
        except OSError as exc:
            print(f"[{channel}] Capture retained at {capture}: {exc}", file=sys.stderr, flush=True)
    if problem:
        raise RuntimeError(problem)
    if proc and not stop.is_set() and proc.returncode not in (0, None):
        raise RuntimeError(f"Streamlink exit code {proc.returncode}")


def worker(channel, url, stop, config, extra, root):
    folder = root / channel
    while not stop.is_set():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            record(url, channel, folder, stop, config, extra)
        except Exception as exc:
            # Errors must not silently terminate this channel's only monitor.
            print(f"[{channel}] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        stop.wait(config["interval"])


def serve(channels, url_factory, extra_args=(), output_root=None):
    try:
        unique = list(dict.fromkeys(channel_id(name) for name in channels))
        if not unique:
            raise ValueError("At least one channel ID is required")
        config = settings()
        if not shutil.which("streamlink"):
            raise ValueError("Streamlink executable not found in PATH")
    except (ValueError, AttributeError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr, flush=True)
        return 2

    stop = threading.Event()
    threads = {}
    root = Path.cwd() if output_root is None else Path(output_root)

    def shutdown(_signal=None, _frame=None):
        stop.set()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    exit_code = 0
    try:
        while not stop.is_set():
            for name in unique:
                if stop.is_set():
                    break
                thread = threads.get(name)
                if thread is None or not thread.is_alive():
                    if thread is not None:
                        print(f"[{name}] Recording worker restarted", file=sys.stderr, flush=True)
                    thread = threading.Thread(
                        target=worker,
                        args=(name, url_factory(name), stop, config, extra_args, root),
                        name=f"record-{name}", daemon=True,
                    )
                    threads[name] = thread
                    thread.start()
            stop.wait(1)
    except KeyboardInterrupt:
        stop.set()
    except Exception as exc:
        print(f"Fatal CLI error: {exc}", file=sys.stderr, flush=True)
        exit_code = 1
    finally:
        stop.set()
        for thread in threads.values():
            if thread.ident is not None:
                thread.join(timeout=14)
        if any(thread.is_alive() for thread in threads.values()):
            print("Some workers did not stop cleanly", file=sys.stderr, flush=True)
            exit_code = 1
    return exit_code

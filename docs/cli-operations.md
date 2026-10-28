# Unattended CLI operation and recovery

## Entrypoints

- Twitch single channel: `python twitch_auto_recorder_cli.py CHANNEL`
- Twitch multiple channels: `python tar_cli_multi.py CHANNEL_A CHANNEL_B`
- SOOP multiple channels: `python main.py CHANNEL_A CHANNEL_B`

Use **channel IDs**, not display names. Recordings are written into
`./CHANNEL/` under the *working directory*, with distinct unique filenames.
The actual stream container is detected: `.ts`, `.mp4`, or `.raw` for
unrecognized/partial output. The `.raw` format does **not** prove corruption;
check independently before conversion/deletion. Abandoned `.capture` files are
recovered at startup. Previously recorded output is never intentionally replaced.

## Watchdogs and limits

| Variable | Default | Purpose |
| --- | ---: | --- |
| `CHECK_INTERVAL` | 10 | Streamlink offline polling and process restart delay (seconds) |
| `RETRY_MAX` | 2 | Attempts per Streamlink discovery session |
| `HTTP_TIMEOUT` | 15 | Per-request HTTP timeout (seconds) |
| `STREAM_TIMEOUT` | 90 | Stream read inactivity timeout (seconds) |
| `SEGMENT_TIMEOUT` | 20 | Segment request timeout (seconds) |
| `SEGMENT_ATTEMPTS` | 5 | Segment attempt bound |
| `STARTUP_TIMEOUT` | 150 | Maximum time until first output bytes (seconds) |
| `STALL_TIMEOUT` | 300 | Maximum no-growth time after output starts (seconds) |
| `HEALTH_INTERVAL` | 15 | Status write interval (seconds) |
| `MIN_FREE_MB` | 256 | Minimum remaining disk space required before launching recording |

A fixed, short normal retry interval intentionally replaces the 10-to-300s
exponential backoff that could miss brief broadcasts. All timeouts are bounded,
but they are **not real-time guarantees**. Some APIs, filesystem operations, DNS,
or host failures can still stall without an external OS service supervisor.

Each channel writes atomic JSON health reports at
`CHANNEL/.recorder-status.json` containing PID, state, updated timestamp,
attempt count, last error, last observed capture bytes and progress time.
Watch `updated_at` externally: the process being alive does **not** prove
the recorder is healthy. The health file can itself fail to update when storage
is inaccessible, which must be treated as an unhealthy status.

There is no reliable way to reconstruct bytes not received during downtime.
Twitch advertising segments may deliberately cause gaps, and neither the output
extension nor the Streamlink exit code proves end-to-end audio/video integrity.

## Restart after crashes

On Linux, operate the CLI with `systemd` (or equivalent) and a suitable
`Restart=always` policy. Example **template**, adjust account/path/channels:

```ini
[Unit]
Description=Twitch recorder
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=recorder
WorkingDirectory=/srv/Twitch-Auto-Recorder
ExecStart=/srv/Twitch-Auto-Recorder/.venv/bin/python twitch_auto_recorder_cli.py CHANNEL
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

For SOOP substitute the repository working directory and `main.py CHANNEL`.
If credentials are needed, use `config.json` with restricted filesystem
permissions, or protect the environment with the operating system's secrets
mechanism. Avoid putting passwords on command lines.

On Windows, Task Scheduler can start the CLI on login/system startup and
restart it after failure. Confirm Streamlink is on PATH and set the working
directory explicitly. A PowerShell window closing without a supervisor can
end recording.

## Validation

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

CI validates Linux and Windows process configuration and fault injection, but
full 24-72h live Twitch/SOOP sessions, genuine outages, permission failures and
disk exhaustion still require an operational acceptance run before claiming
unattended production readiness.

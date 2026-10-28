# AfreecaTV-Auto-Recorder (SOOP)

SOOP (formerly AfreecaTV) CLI stream recording using the official Streamlink
SOOP plugin. No Grid/P2P recording is implemented.

## Installation and usage

Python 3.10+ and Streamlink 8.6.2+:

```bash
python -m pip install -r requirements.txt
python main.py CHANNEL_ID
python main.py CHANNEL_A CHANNEL_B
```

For a public stream, no credentials are required. For a login-required stream,
copy `config.example.json` to `config.json` and set `user_name` and
`user_password`, or set the pair `SOOP_USERNAME` and `SOOP_PASSWORD`.
Credentials are written to a mode-0600 temporary Streamlink config on
POSIX, are not passed as process command-line arguments, and are deleted
after the CLI stops. File ownership and host administrators remain trusted.

The CLI supervises one Streamlink child per channel with watchdogs, short
offline retry delays, exception handling, automatic worker restart,
uniquely named output captures, crash recovery, minimum free disk checks,
atomic per-channel status JSON, and graceful SIGINT/SIGTERM shutdown.

Output is stored under `CHANNEL/` in the working directory. The original
stream container is detected as `.ts`, `.mp4` or `.raw` if unidentified.
A filename extension or successful process exit does not prove media integrity.
There is no mechanism to reconstruct downtime gaps.

See [CLI operations and failure recovery](docs/cli-operations.md) for
timeout configuration, status monitoring and service restart setup.

## Verification

```bash
python -m unittest discover -s tests -v
```

MIT License — [LICENSE](LICENSE).

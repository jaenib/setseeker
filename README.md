# setseeker

`setseeker` takes DJ sets or other long-form audio, identifies tracks with Shazam, and then looks for those tracks on Soulseek through [`slskd`](https://github.com/slskd/slskd).

Normal download mode is not download-only anymore. Before any Soulseek transfer starts, `setseeker` runs a reciprocity audit against a real `slskd` daemon and blocks downloads when that backend is not healthy enough to contribute back.

`setseeker` itself is still not the long-lived share-capable client. `slskd` is the share-capable part, and `setseeker` now depends on it instead of pretending otherwise.

## Requirements

- Python 3.11
- [`ffmpeg`](https://ffmpeg.org/) on your `PATH`
- `slskd` for Soulseek search/download/share participation

`setup.sh` handles the Python environment and will bootstrap a repo-local `slskd` automatically if you do not already have one.

## Setup

From the repo root:

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` will:

- create `.venv` and install `requirements.txt`
- check for `ffmpeg` and try to install it if missing
- create the working folders: `sets`, `tracklists`, `spoils`, `user`, `logs`, `tmp/segments`, `tmp/queries`
- store encrypted Soulseek credentials in `user/slsk_cred.json` and `user/slsk.key`
- offer to import legacy credentials from `../user/`
- bootstrap a repo-local `slskd` under `user/slskd/`
- write `user/reciprocity_config.json`

You can rerun `setup.sh` any time. It reuses existing state, repairs the local `slskd` bootstrap if needed, and lets you rotate credentials.

## What Is Actually Checked

Before downloads begin, `setseeker` audits the configured `slskd` instance. The gate is based on real daemon state, not warning text.

It checks:

- at least one shared directory is configured
- share scanning completed successfully
- shared folder count is nonzero
- shared file count is nonzero, unless the download destination is already a configured shared path and this is the first download session
- the Soulseek listen port is configured and, when `slskd` is local, accepting local TCP connections
- the daemon is logged in and upload-capable
- the daemon is online as the long-lived share-capable backend
- the Soulseek account in `slskd` matches the downloader account used by `setseeker`

If any blocking check fails, normal download mode stops and prints exact remediation steps.

Read more in [docs/reciprocity_audit.md](docs/reciprocity_audit.md) and [docs/slskd_reciprocity_setup.md](docs/slskd_reciprocity_setup.md).

## Soulseek Login Flow

`seekspawner.py` resolves credentials in this order:

1. `SLSK_USERNAME` + `SLSK_PASSWORD` environment variables
2. encrypted files in `user/`
3. interactive prompt, with an option to save encrypted credentials

## Run It

Run the launcher directly. Manual venv activation is not required.

```bash
chmod +x launcher.sh
./launcher.sh "<source>"
```

`source` can be:

- a YouTube URL
- a SoundCloud URL
- a local audio file path
- a local folder containing audio files

`launcher.sh` will:

- auto-repair `.venv` if needed
- auto-bootstrap local `slskd` if needed
- ingest audio into `sets/`
- run `fileshazzer.py`
- run the reciprocity doctor/gate
- search and download through `slskd`

If you already placed MP3s in `sets/`, you can also just run:

```bash
./launcher.sh
```

## Useful Commands

Environment + reciprocity doctor:

```bash
./launcher.sh --doctor
```

Identify tracks only, no Soulseek step:

```bash
./launcher.sh --identify-only "<source>"
```

Include all historical tracklists instead of just the latest run:

```bash
./launcher.sh --all-tracklists
```

Unsafe development override for the reciprocity gate:

```bash
./launcher.sh --unsafe-disable-reciprocity-gate "<source>"
```

Manual script entry points:

```bash
python3.11 ingest.py --source "<source>"
python3.11 fileshazzer.py
python3.11 seekspawner.py
python3.11 seekspawner.py --doctor
python3.11 seekspawner.py --all-tracklists
python3.11 seekspawner.py --unsafe-disable-reciprocity-gate
python3.11 slskd_manager.py status
```

## slskd Setup

`setseeker` reads `user/reciprocity_config.json`.

You can start from [reciprocity_config.example.json](reciprocity_config.example.json), but the local bootstrap writes this file for you automatically in the normal case.

The configured `slskd` instance should:

- use the same Soulseek username as `setseeker`
- have one or more explicit shared directories
- finish a healthy share scan; zero files still warns, but the first download session is allowed when the downloads directory is already shared
- stay online as the actual share-capable client
- expose a readable downloads directory if you want files mirrored into `spoils/`

The repo-local bootstrap defaults to:

- web/API on `127.0.0.1`
- downloads in `spoils/`
- incomplete files in `tmp/slskd-incomplete/`
- sharing `spoils/` unless you choose another folder during setup

Normal mode searches and enqueues downloads through `slskd`. If `slskd` is local and its downloads directory is readable, `setseeker` mirrors completed files into `spoils/`. Otherwise the files stay in the daemon's own downloads directory and the output says so explicitly.

`seekspawner.py` logs skipped tracklist lines to `logs/skipped_queries.log`.

## Why You Might See "Already Exist"

By default, `setseeker` only queries tracklists from the latest `fileshazzer` run. That reduces pointless re-checks against older sets.

If you explicitly use `--all-tracklists`, more duplicate/existing-file messages are expected.

## Example Tracklist Output

```text
Final Tracklist:
[00:01:00] Umek - Center of Gravity
[00:13:30] Sade - Like Tattoo
[00:21:00] Zimmie Gix - Absolute Chill
[00:21:30] Andrea Frisina & Irregular Synth - Dub City
[00:22:00] Alan Fitzpatrick - Brian's Proper Dun One
[00:23:30] R.A.W. - Unbe (Erick 'More' Mix)
[00:24:00] Terrace - Magic O
...etc
```

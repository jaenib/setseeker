# setseeker

`fileshazzer.py` splits DJ sets (or any MP3 you throw at it) into segments, runs them through Shazam, and spits out a timestamped tracklist. `seekspawner.py` turns those IDs into Soulseek searches and downloads through a configured backend. Normal mode now runs on top of [`slskd`](https://github.com/slskd/slskd); the old [`slsk-batchdl`](https://github.com/fiso64/slsk-batchdl) path remains only as an explicit legacy fallback.

## Requirements

- Python 3.11
- [`ffmpeg`](https://ffmpeg.org/) command line tool available on your `$PATH`
- `slskd` for normal download mode
- Optional: [.NET 6 SDK](https://dotnet.microsoft.com/en-us/download) only if you want the legacy `slsk-batchdl` fallback
- `git` (only needed if you want setup to clone/build the optional legacy backend)

`setup.sh` handles the Python environment and folders. It only builds `slsk-batchdl` if `.NET` is already installed.

## Setup

From the repo root:

```
chmod +x setup.sh
./setup.sh
```

What that script takes care of:

- Creates a fresh virtual environment at `.venv` and installs `requirements.txt`
- Checks for `ffmpeg`; will try to install it if the binary isn't found
- If `.NET` is already installed, clones and builds the optional legacy `slsk-batchdl` backend
- Sets up the working folders: `sets`, `tracklists`, `spoils`, `user`, `logs`, `tmp/segments`, `tmp/queries`
- Uses one credential location: `user/slsk_cred.json` + `user/slsk.key`
- If old credentials exist in `../user/`, offers to import them so you don't lose your previous setup
- Supports non-interactive setup with `SLSK_USERNAME` and `SLSK_PASSWORD` if you prefer

You can rerun `setup.sh` any time; it will reuse what already exists, offer to rotate credentials, and rebuild the optional legacy backend if available.

## Reciprocity Gate

Normal download mode now requires a real `slskd` backend that passes a reciprocity audit.

- `setseeker` itself is still not the long-lived share-capable client
- the audit is backed by live `slskd` state, not warning text
- downloads are blocked by default when reciprocity is unhealthy
- normal search/download execution also goes through `slskd`
- the old `slsk-batchdl` path is legacy-only and still runs with `--no-modify-share-count`

See [docs/reciprocity_audit.md](docs/reciprocity_audit.md) and [docs/slskd_reciprocity_setup.md](docs/slskd_reciprocity_setup.md).

## Soulseek Login Flow

`seekspawner.py` resolves credentials in this order:

1. `SLSK_USERNAME` + `SLSK_PASSWORD` environment variables
2. Encrypted files in `user/`
3. Interactive prompt (with option to save encrypted credentials for next run)

## Run it

1. Run the launcher directly (no manual venv activation needed):

   ```
   chmod +x launcher.sh
   ./launcher.sh "<source>"
   ```

   `source` can be:
   - a YouTube URL (video or playlist)
   - a SoundCloud URL (track or playlist)
   - a local audio file path (mp3/wav/flac/...)
   - a local folder path with audio files

   `launcher.sh` auto-checks/fixes `.venv`, ingests/downloads audio into `sets/`, then runs `fileshazzer.py` followed by `seekspawner.py`.

2. Local file fallback is still supported:

   - put MP3 files directly in `sets/`
   - then run:

   ```
   ./launcher.sh
   ```

3. Optional helper modes:

   - **Environment + reciprocity doctor**

     ```
     ./launcher.sh --doctor
     ```

   - **Just fingerprint and build tracklists (no Soulseek download step)**

     ```
     ./launcher.sh --identify-only "<source>"
     ```

   - **Re-run against all historical tracklists (legacy tracklist scope)**

     ```
     ./launcher.sh --all-tracklists
     ```

   - **Unsafe override for development/testing**

     ```
     ./launcher.sh --unsafe-disable-reciprocity-gate "<source>"
     ```

   - **Force a specific download backend**

     ```
     ./launcher.sh --download-backend slskd "<source>"
     ./launcher.sh --download-backend legacy-sldl "<source>"
     ```

4. Advanced/manual mode (if you want to run scripts yourself):

   - `python3.11 ingest.py --source "<source>"` to only download/import audio into `sets/`
   - `python3.11 fileshazzer.py` for only the Shazam/tracklist stage
   - `python3.11 seekspawner.py` for only the Soulseek download stage
   - `python3.11 seekspawner.py --doctor` for reciprocity doctor output
   - `python3.11 seekspawner.py --all-tracklists` to include all historical tracklists
   - `python3.11 seekspawner.py --download-backend slskd`
   - `python3.11 seekspawner.py --download-backend legacy-sldl`
   - `python3.11 seekspawner.py --unsafe-disable-reciprocity-gate` to bypass blocking for development/testing only

## slskd Setup

`setseeker` looks for `user/reciprocity_config.json`.

Start from [reciprocity_config.example.json](reciprocity_config.example.json), then point it at your `slskd` instance.

The configured `slskd` backend should:

- use the same Soulseek username as `setseeker`
- have at least one shared directory configured
- complete a healthy share scan
- report nonzero shared folders and files
- stay online as the real share-capable client
- expose a downloads directory on the same machine if you want completed files mirrored into `spoils/`

Normal mode searches and enqueues downloads through `slskd`. If `slskd` runs locally and its downloads directory is readable, `setseeker` mirrors completed files into `spoils/`. If not, the files stay in the daemon's own downloads directory and `setseeker` tells you that explicitly.

`seekspawner.py` logs anything it had to skip to `logs/skipped_queries.log`. When local mirroring is available, completed downloads are copied or hard-linked into `spoils/`.

### Why you might see "already exist"

Setseeker now queries only tracklists from the **latest `fileshazzer` run** by default to reduce noisy re-checks across old sets.
If you explicitly choose `--all-tracklists`, expect more `already exist` lines.

## Example tracklist output

```
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

# setseeker

`fileshazzer.py` splits DJ sets (or any MP3 you throw at it) into segments, runs them through Shazam, and spits out a timestamped tracklist. `seekspawner.py` takes those IDs and hunts the files down on Soulseek via [`slsk-batchdl`](https://github.com/fiso64/slsk-batchdl). Bring your own Soulseek credentials (setup will store them for you), or create new ones if you don't have them

## Requirements

- Python 3.11
- [`ffmpeg`](https://ffmpeg.org/) command line tool available on your `$PATH`
- [.NET 6 SDK](https://dotnet.microsoft.com/en-us/download) so we can build `slsk-batchdl`
- `git` (only needed the first time `setup.sh` clones `slsk-batchdl`)

`setup.sh` tries to install `ffmpeg` and the .NET SDK for you on macOS or Debian/Ubuntu. If you're on anything else (or the script still complains that .NET is missing), install those pieces manually, then rerun `./setup.sh`.

## Setup

From the repo root:

```
chmod +x setup.sh
./setup.sh
```

What that script takes care of:

- Creates a fresh virtual environment at `.venv` and installs `requirements.txt`
- Checks for `ffmpeg`; will try to install it if the binary isn't found
- Makes sure `.NET 6` is around, then clones and builds `slsk-batchdl` into `slsk-batchdl/slsk-batchdl/bin/Release`
- Sets up the working folders: `sets`, `tracklists`, `spoils`, `user`, `logs`, `tmp/segments`, `tmp/queries`
- Uses one credential location: `user/slsk_cred.json` + `user/slsk.key`
- If old credentials exist in `../user/`, offers to import them so you don't lose your previous setup
- Supports non-interactive setup with `SLSK_USERNAME` and `SLSK_PASSWORD` if you prefer

You can rerun `setup.sh` any time; it will reuse what already exists, offer to rotate credentials, and rebuild `slsk-batchdl` if needed.

## Reciprocity Gate

Normal download mode now requires a real `slskd` backend that passes a reciprocity audit.

- `setseeker` itself is still not the long-lived share-capable client
- the audit is backed by live `slskd` state, not warning text
- downloads are blocked by default when reciprocity is unhealthy
- `slsk-batchdl` is run with `--no-modify-share-count` so it does not advertise fake share counts

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

   - **Re-run against all historical tracklists (legacy behavior)**

     ```
     ./launcher.sh --all-tracklists
     ```

   - **Unsafe override for development/testing**

     ```
     ./launcher.sh --unsafe-disable-reciprocity-gate "<source>"
     ```

4. Advanced/manual mode (if you want to run scripts yourself):

   - `python3.11 ingest.py --source "<source>"` to only download/import audio into `sets/`
   - `python3.11 fileshazzer.py` for only the Shazam/tracklist stage
   - `python3.11 seekspawner.py` for only the Soulseek download stage
   - `python3.11 seekspawner.py --doctor` for reciprocity doctor output
   - `python3.11 seekspawner.py --all-tracklists` to include all historical tracklists (legacy behavior)
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

`seekspawner.py` logs anything it had to skip to `logs/skipped_queries.log`, and downloads land in `spoils/`.

### Why you might see "already exist"

`sldl` checks your output folder to avoid duplicate downloads.  
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

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

## Community Sharing Flow (setseeker-owned)

The sharing etiquette flow is implemented in `seekspawner.py` (your repo), not by patching upstream `slsk-batchdl`.

- Default local share folder is the download folder: `spoils/`
- Change local share folder with `--share-dir <path>`
- Opt out of local share folder with `--no-share-dir`
- If no local share folder is configured, a reminder is shown at run start
- If you already broadcast elsewhere, mute that reminder with `--disable-share-reminder`
- `--skip-share-check` bypasses reminder for one run
- Session and cumulative share-vs-download stats are tracked
- Local state lives at `user/community_state.json`

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

   - **Environment doctor (recommended for troubleshooting)**

     ```
     ./launcher.sh --doctor
     ```

   - **Just fingerprint and build tracklists (no Soulseek download step)**

     ```
     ./launcher.sh --identify-only "<source>"
     ```

   - **Set or override the community share folder**

     ```
     ./launcher.sh --share-dir "/path/to/your/shared-music"
     ```

   - **Opt out of local share folder**

     ```
     ./launcher.sh --no-share-dir
     ```

   - **Skip share reminder for one run**

     ```
     ./launcher.sh --skip-share-check
     ```

   - **Mute reminder if you already share elsewhere**

     ```
     ./launcher.sh --disable-share-reminder
     ```

   - **Show cumulative share/download stats**

     ```
     ./launcher.sh --show-share-stats
     ```

4. Advanced/manual mode (if you want to run scripts yourself):

   - `python3.11 ingest.py --source "<source>"` to only download/import audio into `sets/`
   - `python3.11 fileshazzer.py` for only the Shazam/tracklist stage
   - `python3.11 seekspawner.py` for only the Soulseek download stage
   - `python3.11 seekspawner.py --help-share` for wrapper sharing help
   - `python3.11 seekspawner.py --show-share-stats` for stored stats only

`seekspawner.py` logs anything it had to skip to `logs/skipped_queries.log`, and downloads land in `spoils/`.

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

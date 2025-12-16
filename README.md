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
- Stores encrypted Soulseek credentials at `user/slsk_cred.json` + `user/slsk.key` (set `SLSK_USERNAME` and `SLSK_PASSWORD` in your shell to skip the prompt)

You can rerun `setup.sh` any time; it will reuse what already exists, offer to rotate credentials, and rebuild `slsk-batchdl` if needed.

## Run it

1. Drop MP3s into `sets/` or point `fileshazzer.py` at a SoundCloud link (the `soundcloud_url` variable near the top).
2. Activate the virtualenv:

   ```
   source .venv/bin/activate
   ```

3. Pick your workflow:

   - **Full pipeline (Shazam + Soulseek download)**

     ```
     chmod +x launcher.sh
     ./launcher.sh
     ```

     `launcher.sh` activates the venv, runs `fileshazzer.py`, then immediately hands the fresh queries to `seekspawner.py`.

   - **Just fingerprint and build tracklists**

     ```
     python3.11 fileshazzer.py
     ```

     Tracklists (and their original MP3s) end up under `tracklists/<set_name>/`. If Shazam throttles and things look frozen, give it a minute—it will continue. Want more reliable matches? Bump `segment_length` (default `60` seconds) at the top of the script so each chunk contains more audio.

   - **Already have a tracklist and only need Soulseek**

     ```
     python3.11 seekspawner.py
     ```

     The script looks for `*.txt` tracklists under `tracklists/`, parses them into `tmp/queries/queries.txt`, and fires those queries at Soulseek. You can drop your own tracklist files in there as long as they follow the same `[hh:mm:ss] Artist - Title` format.

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

# Reciprocity Audit

## What Is True Today

- `setseeker` is still a Python orchestration layer:
  - `ingest.py` imports source audio
  - `fileshazzer.py` identifies tracks with Shazam
  - `seekspawner.py` builds typed track queries and routes them to a backend
- This repo still does not implement its own Soulseek protocol client.
- Normal mode now uses `slskd` as both:
  - the reciprocity source of truth
  - the active search/download backend
- The repo can now bootstrap a local `slskd` instance automatically when it is missing.
- `slsk-batchdl` remains available only as an explicit legacy fallback backend.

## What The Current Downloader Actually Does

- Runs a reciprocity audit against a configured `slskd` instance.
- Blocks downloads by default unless that backend is minimally healthy.
- Creates searches through `slskd`, chooses a candidate file, enqueues the download, and waits for transfer completion.
- Reuses the same long-lived `slskd` daemon that can also advertise shares and serve uploads.
- Mirrors completed files into `spoils/` only when `slskd` is local and its downloads directory is readable from this machine.

## What It Does Not Do By Itself

- It still does not make `setseeker` itself a first-party long-lived Soulseek client.
- It still does not verify external port forwarding or browseability from outside the host.
- It still depends on `slskd` for truthful share serving, upload handling, and online presence.
- It still does not force `slskd` configuration changes remotely; shared directories remain explicit user configuration.

## Important Risk In The Legacy Stack

- Upstream `slsk-batchdl` logs in with a real Soulseek connection and, by default, calls `SetSharedCountsAsync(50, 1000)`.
- That can advertise synthetic share counts unless `--no-modify-share-count` is passed.
- `setseeker` now avoids that in two ways:
  - normal mode no longer uses `slsk-batchdl`
  - the legacy fallback still passes `--no-modify-share-count`

## What Can Be Implemented Safely Now

- A truthful reciprocity status object in Python.
- A doctor command that audits a real `slskd` backend.
- Download blocking unless the backend passes reciprocity checks.
- Normal search/download execution through `slskd`, not just reciprocity gating.
- Explicit legacy fallback and explicit unsafe override.

## What Still Requires A Larger Rewrite

- Making `setseeker` itself a real long-lived share-capable Soulseek client.
- Verifying true external reachability from outside the local host.
- Replacing `slskd` with a first-party protocol implementation.
- Building richer, deterministic search ranking that can fully replace mature client behavior across edge cases.

## Recommended Path Forward

1. Keep `slskd` as the standard backend for healthy operation.
2. Treat `legacy-sldl` as compatibility-only, not normal mode.
3. Keep public claims narrow:
   - `setseeker` requires a healthy `slskd` sharing backend for normal download mode.
   - `setseeker` now performs its own search/download work through that daemon.
   - `setseeker` itself is still not the share-capable client.
4. If the `slskd` path proves stable, remove the legacy backend entirely.

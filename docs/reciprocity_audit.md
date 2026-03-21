# Reciprocity Audit

## What Is True Today

- `setseeker` is a Python orchestration layer:
  - `ingest.py` brings in source audio
  - `fileshazzer.py` identifies tracks with Shazam
  - `seekspawner.py` turns tracklists into Soulseek download queries
- Soulseek download connectivity is delegated to upstream `slsk-batchdl`, invoked as:
  - `dotnet slsk-batchdl/slsk-batchdl/bin/Release/net6.0/sldl.dll ...`
- This repo does not implement its own Soulseek protocol client.
- This repo does not currently use `slskd` or Nicotine+ as the active download backend.

## What The Current Downloader Actually Does

- Searches and downloads from Soulseek through `slsk-batchdl`.
- Opens a Soulseek client connection for the duration of the download session.
- Uses a Soulseek listen port owned by `slsk-batchdl` / Soulseek.NET, not by Python code in this repo.
- Exits when the download session ends; it does not remain online as a long-lived sharing client.

## What It Does Not Do By Itself

- It does not configure or advertise real shared directories from this repo.
- It does not serve uploads from a configured music library in any verifiable way.
- It does not verify inbound reachability or browseability.
- It does not track truthful upload/download reciprocity metrics for the user account.
- It does not expose a stable share-capable daemon mode.

## Important Risk In The Current Stack

- Upstream `slsk-batchdl` logs in with a real Soulseek connection and, by default, calls `SetSharedCountsAsync(50, 1000)`.
- That means a plain `sldl` session can advertise synthetic share counts unless `--no-modify-share-count` is passed.
- `setseeker` now passes `--no-modify-share-count` so it no longer relies on fake share-count signaling.

## Lowest-Risk Honest Path

- Keep the existing set-identification pipeline.
- Keep `slsk-batchdl` as the download executor for now.
- Add a reciprocity gate backed by a real share-capable daemon: `slskd`.
- Block downloads unless `slskd` proves that the user is configured in a minimally reciprocal way.

This is the smallest step that is both technically credible and reviewable.

## What Can Be Implemented Safely Now

- A truthful reciprocity status object in Python.
- A doctor command that audits a real `slskd` backend.
- Download blocking unless the backend passes reciprocity checks.
- Explicit unsafe override for development/testing.
- Honest docs and config examples for `slskd` setup.

## What Requires A Larger Rewrite

- Making `setseeker` itself a real long-lived share-capable Soulseek client.
- Serving uploads directly from Python in this repo.
- Verifying external reachability from inside the app without an external probe.
- Replacing `slsk-batchdl` with a first-party Soulseek client implementation.

## Recommended Path Forward

1. Use `slskd` as the real reciprocity backend today.
2. Keep the gate strict: no configured `slskd`, no downloads.
3. Keep public claims narrow:
   - `setseeker` requires a healthy `slskd` sharing backend for normal download mode.
   - `setseeker` itself is not yet the share-capable client.
4. If the `slskd` path proves stable, add a backend adapter seam and migrate download/search operations away from `slsk-batchdl` over time.

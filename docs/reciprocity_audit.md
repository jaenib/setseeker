# Reciprocity Audit

## What Is True Today

- `setseeker` is a Python orchestration layer:
  - `ingest.py` imports source audio
  - `fileshazzer.py` identifies tracks with Shazam
  - `seekspawner.py` builds typed track queries and runs the Soulseek step
- `setseeker` is not its own Soulseek protocol implementation.
- Normal Soulseek operation now depends on `slskd`.
- The same `slskd` daemon is used for:
  - reciprocity auditing
  - search creation
  - download enqueueing
  - transfer observation
- The repo can bootstrap a local `slskd` automatically under `user/slskd/`.
- The old `slsk-batchdl` compatibility path has been removed from the repo.

## What The Current Downloader Does

- audits a configured `slskd` instance before download mode starts
- blocks downloads by default unless that daemon is minimally reciprocal
- creates searches through `slskd`
- picks candidate files from `slskd` search responses
- enqueues downloads through `slskd`
- waits for transfer completion through `slskd`
- mirrors completed files into `spoils/` only when the daemon is local and its downloads directory is readable

## What It Does Not Do By Itself

- It does not make `setseeker` itself a first-party long-lived Soulseek client.
- It does not independently advertise shares or serve uploads without `slskd`.
- It does not prove external reachability from outside the host.
- It does not remotely force share configuration changes in `slskd`; shared directories remain explicit user configuration.

## What Can Be Implemented Safely Now

- truthful reciprocity doctor output based on live daemon state
- blocking download mode unless the daemon passes reciprocity checks
- automatic local bootstrap of `slskd`
- normal search/download work through the same daemon being audited
- explicit unsafe override for development/testing

## What Still Requires A Larger Rewrite

- making `setseeker` itself the long-lived share-capable Soulseek client
- independent verification of real external browseability / inbound reachability
- replacing `slskd` with a first-party protocol implementation
- richer deterministic search ranking comparable to mature clients across edge cases

## Recommended Path Forward

1. Keep `slskd` as the only supported Soulseek backend.
2. Keep public claims narrow:
   - `setseeker` requires a healthy `slskd` sharing backend for normal download mode.
   - `setseeker` performs its search/download work through that daemon.
   - `setseeker` itself is still not the share-capable client.
3. Continue simplifying around the `slskd` path instead of carrying alternate download backends.

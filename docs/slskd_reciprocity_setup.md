# slskd Reciprocity Setup

`setseeker` now expects a real `slskd` instance for normal download mode.

## Minimum Setup

1. Install and run `slskd`.
2. Configure the same Soulseek username in `slskd` that `setseeker` uses for downloads.
3. Add at least one absolute shared directory in `slskd`.
4. Run a successful share scan until `slskd` reports nonzero shared folders and files.
5. Configure a Soulseek listen port in `slskd`.
6. Create an API key in `slskd` so `setseeker` can audit reciprocity state.

## setseeker Config

Create `user/reciprocity_config.json` using the example file in the repo root.

Recommended fields:

- `backend`: `slskd`
- `slskd.url`: the base web/API URL, for example `http://127.0.0.1:5030`
- `slskd.api_key`: a read-only or administrator API key
- `slskd.require_same_username`: keep this `true`

## What The Gate Checks

- At least one shared directory is configured.
- Share scan completed successfully.
- Shared folder count is nonzero.
- Shared file count is nonzero.
- Soulseek listen port is configured and, when `slskd` is local, locally bindable.
- The backend is logged into Soulseek and capable of serving uploads.
- The backend Soulseek username matches the downloader username.

## Doctor Command

Run:

```bash
./launcher.sh --doctor
```

The reciprocity section reports:

- pass/fail for each check
- exact blocking reasons
- exact remediation steps

## Unsafe Override

Normal downloads are blocked when reciprocity is unhealthy.

For development/testing only:

```bash
./launcher.sh --unsafe-disable-reciprocity-gate "<source>"
```

This mode is intentionally noisy and not presented as healthy operation.

# slskd Reciprocity Setup

`setseeker` now expects a real `slskd` instance for normal download mode.

That daemon is used for both:

- reciprocity auditing
- normal search/download execution

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
- `slskd.mirror_downloads_to_spoils`: keep this `true` if `slskd` is local and you want completed files mirrored into `spoils/`

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

Normal runs also print which download backend is active.

## Unsafe Override

Normal downloads are blocked when reciprocity is unhealthy.

For development/testing only:

```bash
./launcher.sh --unsafe-disable-reciprocity-gate "<source>"
```

This mode is intentionally noisy and not presented as healthy operation.

## Legacy Backend

`setseeker` still contains an explicit fallback backend for `slsk-batchdl`:

```bash
./launcher.sh --download-backend legacy-sldl "<source>"
```

That path is compatibility-only. It is not the recommended or default mode.

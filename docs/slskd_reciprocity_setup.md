# slskd Reciprocity Setup

`setseeker` expects a real `slskd` instance for normal Soulseek operation.

That daemon is used for both:

- reciprocity auditing
- normal search/download execution

## Automatic Bootstrap

On a normal local install, `setup.sh` and `launcher.sh` try to bootstrap a repo-local `slskd` automatically.

The bootstrap will:

- install a local `slskd` binary into `user/slskd/install/` if needed
- create a local app/config in `user/slskd/app/`
- reuse the Soulseek credentials already stored in `user/`
- write `user/reciprocity_config.json`
- start the daemon locally and keep the web/API bound to `127.0.0.1`

The default share/download folder for that local bootstrap is `spoils/`.

## Minimum Setup

1. Install and run `slskd`, or let `setseeker` bootstrap it locally.
2. Configure the same Soulseek username in `slskd` that `setseeker` uses for downloads.
3. Add at least one explicit shared directory in `slskd`.
4. Run a successful share scan. Zero shared files still warns, but the first download session is allowed when the download directory is already inside one of the configured shares.
5. Configure a Soulseek listen port in `slskd`.
6. Create an API key in `slskd` so `setseeker` can audit reciprocity state.

## setseeker Config

Create `user/reciprocity_config.json` using the example file in the repo root, or let the local bootstrap create it.

Recommended fields:

- `slskd.url`: base web/API URL, for example `http://127.0.0.1:5030`
- `slskd.api_key`: read-only or administrator API key
- `slskd.require_same_username`: usually keep this `true`
- `slskd.mirror_downloads_to_spoils`: keep this `true` if `slskd` is local and you want completed files mirrored into `spoils/`

## What The Gate Checks

- at least one shared directory is configured
- share scan completed successfully
- shared folder count is nonzero
- shared file count is nonzero, unless the download directory is already inside one of the configured shares and this is the first download session
- the Soulseek listen port is configured and, when `slskd` is local, locally bindable
- the daemon is logged into Soulseek and upload-capable
- the daemon username matches the downloader username

## Doctor Command

Run:

```bash
./launcher.sh --doctor
```

The reciprocity section reports:

- pass/fail for each check
- exact blocking reasons
- exact remediation steps

Normal runs also state that downloads are going through `slskd`.

## Unsafe Override

Normal downloads are blocked when reciprocity is unhealthy.

For development/testing only:

```bash
./launcher.sh --unsafe-disable-reciprocity-gate "<source>"
```

This mode is intentionally noisy and is not presented as healthy operation.

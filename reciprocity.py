from __future__ import annotations

import base64
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


RECIPROCITY_CONFIG_PATH = Path("user/reciprocity_config.json")
RECIPROCITY_CONFIG_EXAMPLE_PATH = Path("reciprocity_config.example.json")


@dataclass
class SlskdConfig:
    url: str = ""
    api_key: str = ""
    username: str = ""
    password: str = ""
    require_same_username: bool = True
    search_timeout_seconds: int = 15
    response_limit: int = 100
    file_limit: int = 10000
    poll_interval_seconds: float = 1.0
    transfer_timeout_seconds: int = 1800
    mirror_downloads_to_spoils: bool = True


@dataclass
class ReciprocityConfig:
    backend: str = "slskd"
    slskd: SlskdConfig = field(default_factory=SlskdConfig)


@dataclass
class ReciprocityStatus:
    backend: str
    backend_configured: bool
    backend_reachable: bool
    expected_username: Optional[str]
    backend_username: Optional[str]
    shares_configured: bool
    share_scan_ok: bool
    shared_directory_roots: int
    shared_folder_count: int
    shared_file_count: int
    listening_port_ok: Optional[bool]
    listening_port: Optional[int]
    upload_capable: bool
    background_share_mode: bool
    bytes_uploaded: int
    bytes_downloaded: int
    upload_count: int
    download_count: int
    overall_ok: bool
    empty_share_grace_active: bool = False
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fix_steps: list[str] = field(default_factory=list)


@dataclass
class SlskdSnapshot:
    base_url: str
    state: dict[str, Any]
    options: dict[str, Any]
    shares: dict[str, Any]
    uploads: list[dict[str, Any]]
    downloads: list[dict[str, Any]]


class ReciprocityAuditError(Exception):
    pass


def _env(name: str) -> str:
    from os import environ

    return environ.get(name, "").strip()


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ReciprocityAuditError(f"{path} contains invalid JSON") from exc
    if not isinstance(data, dict):
        raise ReciprocityAuditError(f"{path} must contain a JSON object")
    return data


def load_reciprocity_config(config_path: Path = RECIPROCITY_CONFIG_PATH) -> ReciprocityConfig:
    data: dict[str, Any] = {}
    if config_path.is_file():
        data = _load_json_file(config_path)

    backend = _env("SETSEEK_RECIPROCITY_BACKEND") or str(data.get("backend", "slskd")).strip() or "slskd"
    backend = backend.lower()
    if backend != "slskd":
        raise ReciprocityAuditError(f"Unsupported reciprocity backend '{backend}'. setseeker now only supports 'slskd'.")
    slskd_raw = data.get("slskd", {})
    if not isinstance(slskd_raw, dict):
        slskd_raw = {}

    slskd = SlskdConfig(
        url=_env("SETSEEK_SLSKD_URL") or str(slskd_raw.get("url", "")).strip(),
        api_key=_env("SETSEEK_SLSKD_API_KEY") or str(slskd_raw.get("api_key", "")).strip(),
        username=_env("SETSEEK_SLSKD_USERNAME") or str(slskd_raw.get("username", "")).strip(),
        password=_env("SETSEEK_SLSKD_PASSWORD") or str(slskd_raw.get("password", "")).strip(),
        require_same_username=bool(slskd_raw.get("require_same_username", True)),
        search_timeout_seconds=_safe_int(slskd_raw.get("search_timeout_seconds", 15), 15),
        response_limit=_safe_int(slskd_raw.get("response_limit", 100), 100),
        file_limit=_safe_int(slskd_raw.get("file_limit", 10000), 10000),
        poll_interval_seconds=_safe_float(slskd_raw.get("poll_interval_seconds", 1.0), 1.0),
        transfer_timeout_seconds=_safe_int(slskd_raw.get("transfer_timeout_seconds", 1800), 1800),
        mirror_downloads_to_spoils=bool(slskd_raw.get("mirror_downloads_to_spoils", True)),
    )

    return ReciprocityConfig(backend=backend, slskd=slskd)


def _deep_get(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_label(value: Optional[bool]) -> str:
    if value is True:
        return "OK"
    if value is False:
        return "FAIL"
    return "UNKNOWN"


def _flatten_transfer_groups(groups: Any) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    if isinstance(groups, dict):
        groups = [groups]
    if not isinstance(groups, list):
        return flattened

    for user_group in groups:
        if not isinstance(user_group, dict):
            continue
        for directory_group in user_group.get("directories", []) or []:
            if not isinstance(directory_group, dict):
                continue
            for item in directory_group.get("files", []) or []:
                if isinstance(item, dict):
                    flattened.append(item)
    return flattened


def _sum_transfer_bytes(items: list[dict[str, Any]]) -> int:
    return sum(_safe_int(item.get("bytesTransferred", 0)) for item in items)


def _sum_transfer_count(items: list[dict[str, Any]]) -> int:
    return len(items)


def _normalize_base_url(url: str) -> str:
    normalized = url.rstrip("/")
    if normalized.endswith("/api") or "/api/" in normalized:
        raise ReciprocityAuditError(
            "slskd URL should be the base web address (for example http://127.0.0.1:5030), not an /api path"
        )
    return normalized


def _is_local_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _probe_local_port(port: int, listen_ip: str) -> Optional[bool]:
    if port <= 0:
        return False

    target_host = "127.0.0.1"
    if listen_ip and listen_ip not in {"0.0.0.0", "::", "::0"}:
        if listen_ip in {"127.0.0.1", "::1"}:
            target_host = listen_ip
        else:
            # Best-effort only; non-loopback addresses may not be routable from the local host.
            target_host = listen_ip

    try:
        with socket.create_connection((target_host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _normalize_path_string(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    if text == "/":
        return text
    return text.rstrip("/")


def _extract_configured_share_paths(snapshot: SlskdSnapshot) -> list[str]:
    configured_paths: list[str] = []

    option_paths = _deep_get(snapshot.options, ["shares", "directories"], [])
    if isinstance(option_paths, list):
        configured_paths.extend(str(path).strip() for path in option_paths if str(path).strip())
    elif isinstance(option_paths, str) and option_paths.strip():
        configured_paths.append(option_paths.strip())

    for host_shares in snapshot.shares.values():
        if not isinstance(host_shares, list):
            continue
        for share in host_shares:
            if not isinstance(share, dict):
                continue
            for key in ("directory", "path", "shareDirectory", "sharePath"):
                value = share.get(key)
                if isinstance(value, str) and value.strip():
                    configured_paths.append(value.strip())
                    break

    return _unique_keep_order(configured_paths)


def _count_configured_share_roots(snapshot: SlskdSnapshot) -> int:
    configured_paths = _extract_configured_share_paths(snapshot)
    if configured_paths:
        return len(configured_paths)

    configured_shares = 0
    for host_shares in snapshot.shares.values():
        if isinstance(host_shares, list):
            configured_shares += sum(1 for item in host_shares if isinstance(item, dict))

    return configured_shares


def _extract_download_directory(snapshot: SlskdSnapshot) -> Optional[str]:
    candidates = (
        _deep_get(snapshot.options, ["directories", "downloads"], ""),
        _deep_get(snapshot.options, ["directories", "downloadsDirectory"], ""),
        _deep_get(snapshot.options, ["directories", "download"], ""),
    )

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return None


def _download_destination_is_shared(snapshot: SlskdSnapshot) -> bool:
    download_directory = _normalize_path_string(_extract_download_directory(snapshot))
    if not download_directory:
        return False

    shared_paths = _extract_configured_share_paths(snapshot)
    for shared_path in shared_paths:
        normalized_share_path = _normalize_path_string(shared_path)
        if not normalized_share_path:
            continue
        if normalized_share_path == "/":
            return download_directory.startswith("/")
        if download_directory == normalized_share_path or download_directory.startswith(f"{normalized_share_path}/"):
            return True
    return False


class SlskdApiClient:
    def __init__(self, config: SlskdConfig):
        if not config.url:
            raise ReciprocityAuditError("slskd URL is not configured")
        self.config = config
        self.base_url = _normalize_base_url(config.url)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.config.api_key:
            headers["X-API-Key"] = self.config.api_key
        elif self.config.username and self.config.password:
            token = base64.b64encode(f"{self.config.username}:{self.config.password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        return headers

    def _request_json(self, method: str, path: str, payload: Any = None, allow_no_content: bool = False) -> Any:
        data = None
        headers = self._headers()
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers=headers,
            method=method,
            data=data,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                response_payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_payload = ""
            try:
                error_payload = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                error_payload = ""
            if exc.code in {401, 403}:
                raise ReciprocityAuditError(
                    "slskd authentication failed; check API key or web credentials"
                ) from exc
            detail = f"slskd API returned HTTP {exc.code} for {path}"
            if error_payload:
                detail = f"{detail}: {error_payload}"
            raise ReciprocityAuditError(detail) from exc
        except urllib.error.URLError as exc:
            raise ReciprocityAuditError(f"could not reach slskd at {self.base_url}: {exc.reason}") from exc

        if allow_no_content and response_payload == "":
            return None
        try:
            return json.loads(response_payload)
        except json.JSONDecodeError as exc:
            if allow_no_content and response_payload == "":
                return None
            raise ReciprocityAuditError(f"slskd returned invalid JSON for {path}") from exc

    def _get_json(self, path: str) -> Any:
        return self._request_json("GET", path)

    def _delete_json(self, path: str) -> Any:
        return self._request_json("DELETE", path, allow_no_content=True)

    def _post_json(self, path: str, payload: Any) -> Any:
        return self._request_json("POST", path, payload=payload)

    def get_application(self) -> dict[str, Any]:
        data = self._get_json("/api/v0/application")
        if not isinstance(data, dict):
            raise ReciprocityAuditError("slskd application endpoint returned an unexpected response shape")
        return data

    def get_options(self) -> dict[str, Any]:
        data = self._get_json("/api/v0/options")
        if not isinstance(data, dict):
            raise ReciprocityAuditError("slskd options endpoint returned an unexpected response shape")
        return data

    def get_shares(self) -> dict[str, Any]:
        data = self._get_json("/api/v0/shares")
        if not isinstance(data, dict):
            raise ReciprocityAuditError("slskd shares endpoint returned an unexpected response shape")
        return data

    def list_downloads(self, include_removed: bool = False, username: Optional[str] = None) -> list[dict[str, Any]]:
        if username:
            path = f"/api/v0/transfers/downloads/{urllib.parse.quote(username, safe='')}"
        else:
            path = "/api/v0/transfers/downloads"
        separator = "&" if "?" in path else "?"
        data = self._get_json(f"{path}{separator}includeRemoved={'true' if include_removed else 'false'}")
        return _flatten_transfer_groups(data)

    def create_search(
        self,
        search_id,
        search_text: str,
        search_timeout: int,
        response_limit: int,
        file_limit: int,
    ) -> dict[str, Any]:
        payload = {
            "id": str(search_id),
            "searchText": search_text,
            "searchTimeout": search_timeout,
            "responseLimit": response_limit,
            "fileLimit": file_limit,
        }
        data = self._post_json("/api/v0/searches", payload)
        if not isinstance(data, dict):
            raise ReciprocityAuditError("slskd search creation returned an unexpected response shape")
        return data

    def get_search(self, search_id, include_responses: bool = False) -> dict[str, Any]:
        data = self._get_json(
            f"/api/v0/searches/{urllib.parse.quote(str(search_id), safe='')}?includeResponses={'true' if include_responses else 'false'}"
        )
        if not isinstance(data, dict):
            raise ReciprocityAuditError("slskd search status returned an unexpected response shape")
        return data

    def get_search_responses(self, search_id) -> list[dict[str, Any]]:
        data = self._get_json(f"/api/v0/searches/{urllib.parse.quote(str(search_id), safe='')}/responses")
        if not isinstance(data, list):
            raise ReciprocityAuditError("slskd search responses returned an unexpected response shape")
        return [response for response in data if isinstance(response, dict)]

    def delete_search(self, search_id) -> None:
        self._delete_json(f"/api/v0/searches/{urllib.parse.quote(str(search_id), safe='')}")

    def enqueue_download(self, username: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        data = self._post_json(f"/api/v0/transfers/downloads/{urllib.parse.quote(username, safe='')}", files)
        if not isinstance(data, dict):
            raise ReciprocityAuditError("slskd enqueue returned an unexpected response shape")
        return data

    def snapshot(self) -> SlskdSnapshot:
        state = self.get_application()
        options = self.get_options()
        shares = self.get_shares()
        uploads = _flatten_transfer_groups(self._get_json("/api/v0/transfers/uploads?includeRemoved=true"))
        downloads = self.list_downloads(include_removed=True)

        return SlskdSnapshot(
            base_url=self.base_url,
            state=state,
            options=options,
            shares=shares,
            uploads=uploads,
            downloads=downloads,
        )


def evaluate_slskd_snapshot(snapshot: SlskdSnapshot, config: ReciprocityConfig, expected_username: Optional[str]) -> ReciprocityStatus:
    status = ReciprocityStatus(
        backend="slskd",
        backend_configured=True,
        backend_reachable=True,
        expected_username=expected_username,
        backend_username=str(_deep_get(snapshot.state, ["user", "username"], "")).strip() or None,
        shares_configured=False,
        share_scan_ok=False,
        shared_directory_roots=0,
        shared_folder_count=_safe_int(_deep_get(snapshot.state, ["shares", "directories"], 0)),
        shared_file_count=_safe_int(_deep_get(snapshot.state, ["shares", "files"], 0)),
        listening_port_ok=None,
        listening_port=None,
        upload_capable=False,
        background_share_mode=False,
        bytes_uploaded=_sum_transfer_bytes(snapshot.uploads),
        bytes_downloaded=_sum_transfer_bytes(snapshot.downloads),
        upload_count=_sum_transfer_count(snapshot.uploads),
        download_count=_sum_transfer_count(snapshot.downloads),
        overall_ok=False,
    )

    status.shared_directory_roots = _count_configured_share_roots(snapshot)
    status.shares_configured = status.shared_directory_roots > 0

    state_server_logged_in = bool(_deep_get(snapshot.state, ["server", "isLoggedIn"], False))
    shares_ready = bool(_deep_get(snapshot.state, ["shares", "ready"], False))
    shares_scanning = bool(_deep_get(snapshot.state, ["shares", "scanning"], False))
    shares_faulted = bool(_deep_get(snapshot.state, ["shares", "faulted"], False))
    shares_cancelled = bool(_deep_get(snapshot.state, ["shares", "cancelled"], False))
    status.share_scan_ok = shares_ready and not shares_scanning and not shares_faulted and not shares_cancelled

    listen_port = _safe_int(_deep_get(snapshot.options, ["soulseek", "listenPort"], 0), 0)
    listen_ip = str(_deep_get(snapshot.options, ["soulseek", "listenIpAddress"], "0.0.0.0") or "0.0.0.0")
    status.listening_port = listen_port if listen_port > 0 else None

    parsed_base = urllib.parse.urlparse(snapshot.base_url)
    if listen_port <= 0:
        status.listening_port_ok = False
    elif _is_local_host(parsed_base.hostname or ""):
        status.listening_port_ok = _probe_local_port(listen_port, listen_ip)
        if status.listening_port_ok is False:
            status.warnings.append(
                f"Configured Soulseek listen port {listen_port} did not accept a local TCP connection on {listen_ip}."
            )
    else:
        status.listening_port_ok = None
        status.warnings.append(
            f"slskd is configured at remote host {parsed_base.hostname}; local port-bind verification is not possible from setseeker."
        )

    upload_slots = _safe_int(_deep_get(snapshot.options, ["global", "upload", "slots"], 0), 0)
    status.upload_capable = state_server_logged_in and upload_slots > 0 and status.shares_configured
    status.background_share_mode = state_server_logged_in

    if not state_server_logged_in:
        status.blocking_reasons.append("slskd is not logged in to the Soulseek network.")

    if config.slskd.require_same_username and expected_username:
        if not status.backend_username:
            status.blocking_reasons.append("Could not determine the Soulseek username used by slskd.")
        elif status.backend_username != expected_username:
            status.blocking_reasons.append(
                f"Downloader account '{expected_username}' does not match slskd account '{status.backend_username}'."
            )

    if not status.shares_configured:
        status.blocking_reasons.append("No shared directories are configured in slskd.")

    if not status.share_scan_ok:
        status.blocking_reasons.append("slskd share scan is not healthy yet (not ready, still scanning, or faulted).")

    if status.shared_folder_count <= 0:
        status.blocking_reasons.append("slskd reports zero shared folders.")

    status.empty_share_grace_active = (
        status.shared_file_count <= 0 and status.shares_configured and _download_destination_is_shared(snapshot)
    )
    if status.shared_file_count <= 0:
        if status.empty_share_grace_active:
            status.warnings.append(
                "slskd reports zero shared files, but its download directory is in one of the shares. "
                "A first download session is allowed so new files can populate that share."
            )
        else:
            status.blocking_reasons.append(
                "slskd reports zero shared files, and its download directory is not configured as one of the shares."
            )

    if status.listening_port_ok is False:
        status.blocking_reasons.append("The configured Soulseek listen port is not accepting local connections.")

    if not status.upload_capable:
        status.blocking_reasons.append("The configured slskd instance is not currently upload-capable.")

    if not status.background_share_mode:
        status.blocking_reasons.append("No long-lived share-capable backend is currently online.")

    if status.listening_port_ok is None:
        status.warnings.append(
            "External reachability is not verified. Port forwarding / inbound connectivity still needs to be confirmed outside setseeker."
        )

    share_setup_needs_attention = (
        not status.shares_configured
        or not status.share_scan_ok
        or status.shared_folder_count <= 0
        or (status.shared_file_count <= 0 and not status.empty_share_grace_active)
    )

    fix_steps: list[str] = []
    if not status.shares_configured:
        fix_steps.append("Add at least one absolute shared directory to slskd and restart or reload it.")
    if not status.share_scan_ok or (status.shared_file_count <= 0 and not status.empty_share_grace_active):
        fix_steps.append("Run a successful slskd share scan and wait until the share cache reports ready with nonzero files.")
    if status.listening_port_ok is False:
        fix_steps.append("Set a valid slskd Soulseek listen port and make sure the daemon is actually bound to it.")
    if config.slskd.require_same_username and expected_username and status.backend_username and status.backend_username != expected_username:
        fix_steps.append("Use the same Soulseek username in setseeker and slskd, or disable the gate only for development.")
    if not state_server_logged_in:
        fix_steps.append("Log slskd into Soulseek and keep it running as the long-lived share-capable client.")
    if status.listening_port_ok is None:
        fix_steps.append("Confirm port forwarding or inbound reachability outside setseeker; this doctor can only verify local bind state.")
    if share_setup_needs_attention:
        fix_steps.append(
            f"Open the slskd web UI at {snapshot.base_url}, join Soulseek chat rooms there, and ask other users for help if you get stuck configuring your shares."
        )

    status.fix_steps = _unique_keep_order(fix_steps)
    status.overall_ok = len(status.blocking_reasons) == 0
    return status


def evaluate_reciprocity_status(config: ReciprocityConfig, expected_username: Optional[str]) -> ReciprocityStatus:
    if not config.slskd.url:
        status = ReciprocityStatus(
            backend="slskd",
            backend_configured=False,
            backend_reachable=False,
            expected_username=expected_username,
            backend_username=None,
            shares_configured=False,
            share_scan_ok=False,
            shared_directory_roots=0,
            shared_folder_count=0,
            shared_file_count=0,
            listening_port_ok=None,
            listening_port=None,
            upload_capable=False,
            background_share_mode=False,
            bytes_uploaded=0,
            bytes_downloaded=0,
            upload_count=0,
            download_count=0,
            overall_ok=False,
        )
        status.blocking_reasons.append("slskd is not configured yet.")
        status.fix_steps.append(
            f"Create {RECIPROCITY_CONFIG_PATH} with a reachable slskd API endpoint."
        )
        status.fix_steps.append("Configure slskd with shared directories and keep it running as the real share-capable client.")
        return status

    try:
        snapshot = SlskdApiClient(config.slskd).snapshot()
    except ReciprocityAuditError as exc:
        status = ReciprocityStatus(
            backend="slskd",
            backend_configured=True,
            backend_reachable=False,
            expected_username=expected_username,
            backend_username=None,
            shares_configured=False,
            share_scan_ok=False,
            shared_directory_roots=0,
            shared_folder_count=0,
            shared_file_count=0,
            listening_port_ok=None,
            listening_port=None,
            upload_capable=False,
            background_share_mode=False,
            bytes_uploaded=0,
            bytes_downloaded=0,
            upload_count=0,
            download_count=0,
            overall_ok=False,
        )
        status.blocking_reasons.append(f"slskd backend is not reachable: {exc}")
        status.fix_steps.append("Start slskd and confirm its web/API address is correct.")
        status.fix_steps.append("Provide a valid API key or web credentials for the configured slskd instance.")
        return status

    return evaluate_slskd_snapshot(snapshot, config, expected_username)


def config_error_status(message: str, expected_username: Optional[str]) -> ReciprocityStatus:
    status = ReciprocityStatus(
        backend="config-error",
        backend_configured=False,
        backend_reachable=False,
        expected_username=expected_username,
        backend_username=None,
        shares_configured=False,
        share_scan_ok=False,
        shared_directory_roots=0,
        shared_folder_count=0,
        shared_file_count=0,
        listening_port_ok=None,
        listening_port=None,
        upload_capable=False,
        background_share_mode=False,
        bytes_uploaded=0,
        bytes_downloaded=0,
        upload_count=0,
        download_count=0,
        overall_ok=False,
    )
    status.blocking_reasons.append(message)
    status.fix_steps.append(
        f"Repair or recreate {RECIPROCITY_CONFIG_PATH} using {RECIPROCITY_CONFIG_EXAMPLE_PATH} as a template."
    )
    return status


def format_reciprocity_doctor(status: ReciprocityStatus) -> str:
    overall = "ALLOWED" if status.overall_ok else "BLOCKED"
    lines = [
        "Reciprocity doctor",
        f"- Backend: {status.backend}",
        f"- Shares: {_share_status_label(status)}"
        f" ({status.shared_directory_roots} configured roots, {status.shared_folder_count} folders, {status.shared_file_count} files)",
        f"- Scan: {'OK' if status.share_scan_ok else 'FAIL'}",
        f"- Reachability: {_bool_label(status.listening_port_ok)}"
        + (f" (listen port {status.listening_port})" if status.listening_port else ""),
        f"- Upload mode: {'OK' if status.upload_capable else 'FAIL'}",
        f"- Background share mode: {'OK' if status.background_share_mode else 'FAIL'}",
        f"- Account match: {'OK' if _account_match_ok(status) else 'UNKNOWN' if not status.backend_username else 'FAIL'}"
        + _account_match_suffix(status),
        f"- Transfer totals: uploaded {format_bytes(status.bytes_uploaded)} in {status.upload_count} uploads; "
        f"downloaded {format_bytes(status.bytes_downloaded)} in {status.download_count} downloads",
        f"- Overall download eligibility: {overall}",
    ]

    if status.blocking_reasons:
        lines.append("- Blocking reasons:")
        lines.extend(f"  - {reason}" for reason in status.blocking_reasons)

    if status.warnings:
        lines.append("- Warnings:")
        lines.extend(f"  - {warning}" for warning in status.warnings)

    if status.fix_steps:
        lines.append("- Fix steps:")
        lines.extend(f"  - {step}" for step in status.fix_steps)

    return "\n".join(lines)


def format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size = float(size_bytes)
    for suffix in ("KiB", "MiB", "GiB", "TiB"):
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.1f} {suffix}"
    return f"{size:.1f} PiB"


def _account_match_ok(status: ReciprocityStatus) -> bool:
    if not status.expected_username:
        return False
    if not status.backend_username:
        return False
    return status.expected_username == status.backend_username


def _account_match_suffix(status: ReciprocityStatus) -> str:
    if not status.expected_username:
        return " (downloader username unavailable)"
    if not status.backend_username:
        return f" (expected {status.expected_username}, backend unknown)"
    return f" ({status.expected_username} vs {status.backend_username})"


def _share_status_label(status: ReciprocityStatus) -> str:
    if not status.shares_configured or status.shared_folder_count <= 0:
        return "FAIL"
    if status.shared_file_count > 0:
        return "OK"
    if status.empty_share_grace_active:
        return "WARN"
    return "FAIL"


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique

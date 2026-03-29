from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

from reciprocity import RECIPROCITY_CONFIG_PATH, SlskdApiClient, SlskdConfig


REPO_ROOT = Path(__file__).resolve().parent
USER_DIR = REPO_ROOT / "user"
LOCAL_SLSKD_ROOT = USER_DIR / "slskd"
LOCAL_SLSKD_INSTALL_ROOT = LOCAL_SLSKD_ROOT / "install"
LOCAL_SLSKD_APP_DIR = LOCAL_SLSKD_ROOT / "app"
LOCAL_SLSKD_CONFIG_PATH = LOCAL_SLSKD_APP_DIR / "slskd.yml"
LOCAL_SLSKD_BOOTSTRAP_PATH = LOCAL_SLSKD_ROOT / "bootstrap.json"
LOCAL_SLSKD_PID_PATH = LOCAL_SLSKD_ROOT / "slskd.pid"
LOCAL_SLSKD_LOG_PATH = LOCAL_SLSKD_ROOT / "slskd.log"

CREDENTIAL_DIR = USER_DIR
DOWNLOAD_DIR = REPO_ROOT / "spoils"
INCOMPLETE_DIR = REPO_ROOT / "tmp" / "slskd-incomplete"
DEFAULT_SHARE_DIR = DOWNLOAD_DIR
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 5030
DEFAULT_SLSK_LISTEN_PORT = 50300
GITHUB_LATEST_RELEASE_API = "https://api.github.com/repos/slskd/slskd/releases/latest"
BOOTSTRAP_ENCRYPTION_KEY_PATH = USER_DIR / "slskd.key"
SENSITIVE_BOOTSTRAP_FIELDS = {"api_key", "jwt_key", "web_password"}
SAFE_METADATA_FIELDS = {"web_url", "share_dir", "downloads_dir", "soulseek_username", "listen_port", "web_port"}


class SlskdBootstrapError(Exception):
    pass


@dataclass
class SlskdApiHealth:
    configured: bool
    authenticated: bool
    service_up: bool
    detail: str = ""


@dataclass
class SoulseekCredentials:
    username: str
    password: str
    source: str


def cred_paths(cred_dir: Path):
    return cred_dir / "slsk_cred.json", cred_dir / "slsk.key"


def cred_pair_exists(cred_dir: Path) -> bool:
    cred_path, key_path = cred_paths(cred_dir)
    return cred_path.is_file() and key_path.is_file()


def load_cred(cred_dir: Path):
    cred_path, key_path = cred_paths(cred_dir)
    data = json.loads(cred_path.read_text(encoding="utf-8"))
    key = key_path.read_bytes()
    fernet = Fernet(key)
    return data["username"], fernet.decrypt(data["password_encrypted"].encode("utf-8")).decode("utf-8")


def resolve_credentials(allow_prompt: bool) -> SoulseekCredentials:
    env_user = os.environ.get("SLSK_USERNAME", "").strip()
    env_pw = os.environ.get("SLSK_PASSWORD", "").strip()
    if env_user and env_pw:
        return SoulseekCredentials(env_user, env_pw, "environment variables")

    if cred_pair_exists(CREDENTIAL_DIR):
        username, password = load_cred(CREDENTIAL_DIR)
        return SoulseekCredentials(username, password, "user/")

    if not allow_prompt:
        raise SlskdBootstrapError("Soulseek credentials are not stored yet. Run ./setup.sh first or export SLSK_USERNAME/SLSK_PASSWORD.")

    username = ""
    while not username:
        username = input("Soulseek username for local slskd: ").strip()

    password = ""
    while not password:
        password = getpass("Soulseek password for local slskd: ").strip()

    return SoulseekCredentials(username, password, "interactive prompt")


def ensure_directories():
    for path in (LOCAL_SLSKD_ROOT, LOCAL_SLSKD_INSTALL_ROOT, LOCAL_SLSKD_APP_DIR, DOWNLOAD_DIR, INCOMPLETE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def choose_share_dir(non_interactive: bool, explicit_share_dir: Optional[str]) -> Path:
    if explicit_share_dir:
        return Path(explicit_share_dir).expanduser().resolve()

    default_path = DEFAULT_SHARE_DIR.resolve()
    if non_interactive or not sys.stdin.isatty():
        return default_path

    answer = input(f"Folder to share through slskd [{default_path}]: ").strip()
    if not answer:
        return default_path
    return Path(answer).expanduser().resolve()


def is_tcp_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(preferred: int, host: str = "127.0.0.1", attempts: int = 50) -> int:
    for offset in range(attempts):
        candidate = preferred + offset
        if is_tcp_port_free(candidate, host=host):
            return candidate
    raise SlskdBootstrapError(f"Could not find a free TCP port near {preferred}")


def _get_or_create_bootstrap_key() -> bytes:
    """Get or create the encryption key for bootstrap metadata."""
    if BOOTSTRAP_ENCRYPTION_KEY_PATH.is_file():
        return BOOTSTRAP_ENCRYPTION_KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    BOOTSTRAP_ENCRYPTION_KEY_PATH.write_bytes(key)
    BOOTSTRAP_ENCRYPTION_KEY_PATH.chmod(0o600)
    return key


def _encrypt_sensitive_fields(data: dict) -> dict:
    """Encrypt sensitive fields in bootstrap metadata."""
    encrypted = data.copy()
    key = _get_or_create_bootstrap_key()
    fernet = Fernet(key)
    for field in SENSITIVE_BOOTSTRAP_FIELDS:
        if field in encrypted and encrypted[field]:
            plaintext = str(encrypted[field]).encode("utf-8")
            encrypted[field] = fernet.encrypt(plaintext).decode("utf-8")
    return encrypted


def _decrypt_sensitive_fields(data: dict) -> dict:
    """Decrypt sensitive fields in bootstrap metadata."""
    decrypted = data.copy()
    if not BOOTSTRAP_ENCRYPTION_KEY_PATH.is_file():
        return decrypted
    key = BOOTSTRAP_ENCRYPTION_KEY_PATH.read_bytes()
    fernet = Fernet(key)
    for field in SENSITIVE_BOOTSTRAP_FIELDS:
        if field in decrypted and decrypted[field]:
            try:
                ciphertext = decrypted[field].encode("utf-8")
                decrypted[field] = fernet.decrypt(ciphertext).decode("utf-8")
            except Exception:
                # If decryption fails, leave the value as-is (may be unencrypted old data)
                pass
    return decrypted


def _build_safe_metadata_display(web_url: str, share_dir: str, downloads_dir: str) -> dict:
    """Build safe metadata for display from individual parameters (not from sensitive dict)."""
    return {
        "web_url": web_url,
        "share_dir": share_dir,
        "downloads_dir": downloads_dir,
    }


def _sanitize_metadata_for_display(metadata: dict) -> dict:
    """Return only safe, non-sensitive metadata fields for display/logging."""
    return {k: v for k, v in metadata.items() if k in SAFE_METADATA_FIELDS}


def load_bootstrap_metadata() -> dict:
    if not LOCAL_SLSKD_BOOTSTRAP_PATH.is_file():
        return {}
    try:
        data = json.loads(LOCAL_SLSKD_BOOTSTRAP_PATH.read_text(encoding="utf-8"))
        return _decrypt_sensitive_fields(data)
    except json.JSONDecodeError as exc:
        raise SlskdBootstrapError(f"{LOCAL_SLSKD_BOOTSTRAP_PATH} contains invalid JSON") from exc


def save_bootstrap_metadata(data: dict):
    encrypted_data = _encrypt_sensitive_fields(data)
    # Sensitive fields are encrypted before writing, so this is safe
    LOCAL_SLSKD_BOOTSTRAP_PATH.write_text(json.dumps(encrypted_data, indent=2), encoding="utf-8")  # nosec B303
    LOCAL_SLSKD_BOOTSTRAP_PATH.chmod(0o600)


def detect_release_asset_name(tag_name: str) -> str:
    version = tag_name.lstrip("v")
    system = platform.system().lower()
    machine = platform.machine().lower()
    libc_name = platform.libc_ver()[0].lower()
    is_musl = system == "linux" and (libc_name == "musl" or Path("/etc/alpine-release").exists())

    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return f"slskd-{version}-osx-arm64.zip"
        if machine in {"x86_64", "amd64"}:
            return f"slskd-{version}-osx-x64.zip"
    elif system == "linux":
        prefix = "linux-musl" if is_musl else "linux"
        if machine in {"x86_64", "amd64"}:
            return f"slskd-{version}-{prefix}-x64.zip"
        if machine in {"arm64", "aarch64"}:
            return f"slskd-{version}-{prefix}-arm64.zip"
        if machine in {"armv7l", "armv6l", "arm"}:
            return f"slskd-{version}-{prefix}-arm.zip"

    raise SlskdBootstrapError(f"Unsupported platform for automatic slskd bootstrap: {system}/{machine}")


def get_latest_release_info() -> tuple[str, str]:
    with urllib.request.urlopen(GITHUB_LATEST_RELEASE_API, timeout=15) as response:
        payload = json.load(response)
    tag_name = str(payload["tag_name"])
    asset_name = detect_release_asset_name(tag_name)
    for asset in payload.get("assets", []):
        if asset.get("name") == asset_name:
            return tag_name.lstrip("v"), str(asset["browser_download_url"])
    raise SlskdBootstrapError(f"Could not find release asset {asset_name} in the latest slskd release")


def find_installed_local_executable() -> Optional[Path]:
    if not LOCAL_SLSKD_INSTALL_ROOT.exists():
        return None
    candidates = sorted(LOCAL_SLSKD_INSTALL_ROOT.rglob("slskd"), reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_available_executable() -> Optional[Path]:
    local = find_installed_local_executable()
    if local:
        return local
    system_path = shutil.which("slskd")
    return Path(system_path).resolve() if system_path else None


def install_local_slskd() -> tuple[Path, str]:
    ensure_directories()
    version, download_url = get_latest_release_info()
    target_dir = LOCAL_SLSKD_INSTALL_ROOT / version
    executable = target_dir / "slskd"
    if executable.is_file():
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable, version

    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="setseeker-slskd-") as tmpdir:
        archive_path = Path(tmpdir) / "slskd.zip"
        urllib.request.urlretrieve(download_url, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(target_dir)

    executable = None
    for candidate in target_dir.rglob("slskd"):
        if candidate.is_file():
            executable = candidate
            break
    if executable is None:
        raise SlskdBootstrapError(f"Downloaded slskd release {version}, but no executable was found")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable, version


def bootstrap_config(non_interactive: bool, explicit_share_dir: Optional[str]) -> dict:
    ensure_directories()
    metadata = load_bootstrap_metadata()
    if LOCAL_SLSKD_CONFIG_PATH.is_file():
        if metadata:
            if not RECIPROCITY_CONFIG_PATH.is_file():
                write_reciprocity_config(metadata)
            return metadata
        if RECIPROCITY_CONFIG_PATH.is_file():
            reciprocity_data = json.loads(RECIPROCITY_CONFIG_PATH.read_text(encoding="utf-8"))
            slskd_data = reciprocity_data.get("slskd", {})
            synthesized = {
                "web_url": str(slskd_data.get("url", "")),
                "api_key": str(slskd_data.get("api_key", "")),
                "share_dir": str(DEFAULT_SHARE_DIR.resolve()),
                "downloads_dir": str(DOWNLOAD_DIR.resolve()),
                "incomplete_dir": str(INCOMPLETE_DIR.resolve()),
            }
            save_bootstrap_metadata(synthesized)
            return synthesized
        raise SlskdBootstrapError(
            f"Local slskd config already exists at {LOCAL_SLSKD_CONFIG_PATH}, but bootstrap metadata is missing. "
            "Review it manually or remove it before re-running automatic bootstrap."
        )

    credentials = resolve_credentials(allow_prompt=not non_interactive)
    share_dir = choose_share_dir(non_interactive=non_interactive, explicit_share_dir=explicit_share_dir)
    share_dir.mkdir(parents=True, exist_ok=True)

    web_port = find_free_port(DEFAULT_WEB_PORT, host=DEFAULT_WEB_HOST)
    listen_port = find_free_port(DEFAULT_SLSK_LISTEN_PORT, host="0.0.0.0")
    web_username = "setseeker"
    web_password = secrets.token_urlsafe(18)
    api_key = secrets.token_urlsafe(32)
    jwt_key = secrets.token_urlsafe(24)

    metadata = {
        "web_url": f"http://{DEFAULT_WEB_HOST}:{web_port}",
        "web_port": web_port,
        "listen_port": listen_port,
        "api_key": api_key,
        "jwt_key": jwt_key,
        "web_username": web_username,
        "web_password": web_password,
        "share_dir": str(share_dir),
        "downloads_dir": str(DOWNLOAD_DIR.resolve()),
        "incomplete_dir": str(INCOMPLETE_DIR.resolve()),
        "soulseek_username": credentials.username,
    }

    yaml_text = render_slskd_yaml(
        soulseek_username=credentials.username,
        soulseek_password=credentials.password,
        share_dir=share_dir.resolve(),
        downloads_dir=DOWNLOAD_DIR.resolve(),
        incomplete_dir=INCOMPLETE_DIR.resolve(),
        web_port=web_port,
        listen_port=listen_port,
        web_username=web_username,
        web_password=web_password,
        api_key=api_key,
        jwt_key=jwt_key,
    )

    # slskd.yml must contain plaintext Soulseek password because slskd reads and uses it for authentication
    # File permissions are restricted to 0o600 (owner read/write only) for security
    LOCAL_SLSKD_CONFIG_PATH.write_text(yaml_text, encoding="utf-8")
    LOCAL_SLSKD_CONFIG_PATH.chmod(0o600)
    save_bootstrap_metadata(metadata)
    write_reciprocity_config(metadata)
    return metadata


def write_reciprocity_config(metadata: dict):
    key = _get_or_create_bootstrap_key()
    fernet = Fernet(key)
    api_key = metadata.get("api_key", "")
    encrypted_api_key = fernet.encrypt(str(api_key).encode("utf-8")).decode("utf-8") if api_key else ""

    # Extract only safe (non-sensitive) fields from metadata for config
    web_url = str(metadata.get("web_url", "")).strip()

    config_data = {
        "slskd": {
            "url": web_url,
            "api_key": encrypted_api_key,
            "api_key_encrypted": True,
            "username": "",
            "password": "",
            "require_same_username": True,
            "search_timeout_seconds": 15,
            "response_limit": 100,
            "file_limit": 10000,
            "poll_interval_seconds": 1.0,
            "transfer_timeout_seconds": 1800,
            "mirror_downloads_to_spoils": True,
        },
    }
    RECIPROCITY_CONFIG_PATH.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    RECIPROCITY_CONFIG_PATH.chmod(0o600)


def yaml_quote(value: str) -> str:
    return json.dumps(str(value))


def render_slskd_yaml(
    soulseek_username: str,
    soulseek_password: str,
    share_dir: Path,
    downloads_dir: Path,
    incomplete_dir: Path,
    web_port: int,
    listen_port: int,
    web_username: str,
    web_password: str,
    api_key: str,
    jwt_key: str,
) -> str:
    return "\n".join(
        [
            "directories:",
            f"  incomplete: {yaml_quote(str(incomplete_dir))}",
            f"  downloads: {yaml_quote(str(downloads_dir))}",
            "shares:",
            "  directories:",
            f"    - {yaml_quote(str(share_dir))}",
            "  filters:",
            r"    - '\.ini$'",
            r"    - 'Thumbs.db$'",
            r"    - '\.DS_Store$'",
            "web:",
            f"  port: {web_port}",
            f"  ip_address: {yaml_quote(DEFAULT_WEB_HOST)}",
            "  https:",
            "    disabled: true",
            "  authentication:",
            "    disabled: false",
            f"    username: {yaml_quote(web_username)}",
            f"    password: {yaml_quote(web_password)}",
            "    jwt:",
            f"      key: {yaml_quote(jwt_key)}",
            "      ttl: 604800000",
            f"    api_key: {yaml_quote(api_key)}",
            "    api_keys:",
            "      setseeker:",
            f"        key: {yaml_quote(api_key)}",
            "        role: administrator",
            "        cidr: 127.0.0.1/32,::1/128",
            "soulseek:",
            f"  username: {yaml_quote(soulseek_username)}",
            f"  password: {yaml_quote(soulseek_password)}",
            "  listen_ip_address: 127.0.0.1",
            f"  listen_port: {listen_port}",
            "transfers:",
            "  upload:",
            "    slots: 20",
            "  download:",
            "    slots: 500",
            "",
        ]
    )


def _probe_slskd_web_service(base_url: str) -> bool:
    normalized = base_url.rstrip("/")
    if not normalized:
        return False
    request = urllib.request.Request(f"{normalized}/api/v0/session/enabled", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
        return True
    except urllib.error.HTTPError as exc:
        return exc.code in {200, 401, 403}
    except Exception:
        return False


def configured_api_health() -> SlskdApiHealth:
    if not RECIPROCITY_CONFIG_PATH.is_file():
        return SlskdApiHealth(configured=False, authenticated=False, service_up=False, detail="user/reciprocity_config.json is missing")

    base_url = ""
    try:
        config = json.loads(RECIPROCITY_CONFIG_PATH.read_text(encoding="utf-8"))
        slskd = config.get("slskd", {})
        base_url = str(slskd.get("url", ""))
        client = SlskdApiClient(
            SlskdConfig(
                url=base_url,
                api_key=str(slskd.get("api_key", "")),
                username=str(slskd.get("username", "")),
                password=str(slskd.get("password", "")),
            )
        )
        client.get_application()
        return SlskdApiHealth(configured=True, authenticated=True, service_up=True)
    except Exception as exc:
        return SlskdApiHealth(
            configured=True,
            authenticated=False,
            service_up=_probe_slskd_web_service(base_url),
            detail=str(exc),
        )


def configured_api_reachable() -> bool:
    return configured_api_health().authenticated


def _bootstrap_failure_message(health: SlskdApiHealth) -> str:
    if health.service_up:
        detail = health.detail or "slskd accepted HTTP connections, but setseeker could not authenticate to the API."
        return (
            "slskd is running, but setseeker could not authenticate to its API. "
            f"{detail} "
            f"If this local config was bootstrapped by an older setseeker version, update {LOCAL_SLSKD_CONFIG_PATH} so "
            "web.authentication includes api_key (and jwt for web login), then restart slskd."
        )
    detail = health.detail or "the daemon never opened a usable API endpoint"
    return f"slskd did not become reachable. {detail}. Check {LOCAL_SLSKD_LOG_PATH} for details."


def read_pid() -> Optional[int]:
    if not LOCAL_SLSKD_PID_PATH.is_file():
        return None
    try:
        return int(LOCAL_SLSKD_PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_local_slskd(non_interactive: bool, explicit_share_dir: Optional[str]) -> dict:
    metadata = bootstrap_config(non_interactive=non_interactive, explicit_share_dir=explicit_share_dir)
    write_reciprocity_config(metadata)

    if configured_api_reachable():
        return metadata

    executable = find_available_executable()
    version = "system"
    if executable is None:
        executable, version = install_local_slskd()
    metadata["version"] = version
    metadata["executable"] = str(executable)
    save_bootstrap_metadata(metadata)

    pid = read_pid()
    if pid and process_is_running(pid):
        deadline = time.time() + 20
        while time.time() < deadline:
            health = configured_api_health()
            if health.authenticated:
                return metadata
            time.sleep(1)
        raise SlskdBootstrapError(_bootstrap_failure_message(configured_api_health()))

    with open(LOCAL_SLSKD_LOG_PATH, "ab") as log_file:
        process = subprocess.Popen(
            [
                str(executable),
                "--headless",
                "--no-logo",
                "--app-dir",
                str(LOCAL_SLSKD_APP_DIR),
                "--config",
                str(LOCAL_SLSKD_CONFIG_PATH),
            ],
            cwd=str(executable.parent),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    LOCAL_SLSKD_PID_PATH.write_text(str(process.pid), encoding="utf-8")

    deadline = time.time() + 30
    while time.time() < deadline:
        health = configured_api_health()
        if health.authenticated:
            return metadata
        time.sleep(1)

    raise SlskdBootstrapError(_bootstrap_failure_message(configured_api_health()))


def ensure_local_slskd(non_interactive: bool, explicit_share_dir: Optional[str]) -> dict:
    ensure_directories()
    if configured_api_reachable():
        metadata = load_bootstrap_metadata()
        if metadata:
            return metadata
    return start_local_slskd(non_interactive=non_interactive, explicit_share_dir=explicit_share_dir)


def print_status():
    metadata = load_bootstrap_metadata()
    print(f"config: {LOCAL_SLSKD_CONFIG_PATH}")
    print(f"reciprocity config: {RECIPROCITY_CONFIG_PATH}")
    if metadata:
        print(f"web url: {metadata.get('web_url', '(unknown)')}")
        print(f"share dir: {metadata.get('share_dir', '(unknown)')}")
        print(f"downloads dir: {metadata.get('downloads_dir', '(unknown)')}")
        print(f"api reachable: {'yes' if configured_api_reachable() else 'no'}")
        print(f"log: {LOCAL_SLSKD_LOG_PATH}")
    else:
        print("slskd has not been bootstrapped yet.")


def parse_args():
    parser = argparse.ArgumentParser(description="Install/bootstrap/start a repo-local slskd instance for setseeker.")
    subparsers = parser.add_subparsers(dest="command", required=False)

    ensure_parser = subparsers.add_parser("ensure", help="Install/bootstrap/start local slskd if needed.")
    ensure_parser.add_argument("--non-interactive", action="store_true", help="Do not prompt; use repo defaults.")
    ensure_parser.add_argument("--share-dir", help="Explicit directory to share through slskd.")

    install_parser = subparsers.add_parser("install", help="Install the local slskd binary only.")
    install_parser.add_argument("--non-interactive", action="store_true", help="Accepted for symmetry.")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Create local config and reciprocity config.")
    bootstrap_parser.add_argument("--non-interactive", action="store_true", help="Do not prompt; use repo defaults.")
    bootstrap_parser.add_argument("--share-dir", help="Explicit directory to share through slskd.")

    start_parser = subparsers.add_parser("start", help="Start the local slskd daemon.")
    start_parser.add_argument("--non-interactive", action="store_true", help="Do not prompt; use repo defaults.")
    start_parser.add_argument("--share-dir", help="Explicit directory to share through slskd.")

    subparsers.add_parser("status", help="Print local slskd bootstrap status.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = args.command or "ensure"
    non_interactive = bool(getattr(args, "non_interactive", False))
    share_dir = getattr(args, "share_dir", None)

    try:
        if command == "ensure":
            metadata = ensure_local_slskd(non_interactive=non_interactive, explicit_share_dir=share_dir)
            web_url = str(metadata.get('web_url', '(unknown)'))
            share_dir_str = str(metadata.get('share_dir', '(unknown)'))
            print(f"Local slskd ready at {web_url}")
            print(f"Share dir: {share_dir_str}")
            return 0
        if command == "install":
            executable, version = install_local_slskd()
            print(f"Installed local slskd {version} at {executable}")
            return 0
        if command == "bootstrap":
            metadata = bootstrap_config(non_interactive=non_interactive, explicit_share_dir=share_dir)
            print(f"Wrote local slskd config at {LOCAL_SLSKD_CONFIG_PATH}")
            print(f"Reciprocity config written to {RECIPROCITY_CONFIG_PATH}")
            share_dir_str = str(metadata.get('share_dir', '(unknown)'))
            print(f"Share dir: {share_dir_str}")
            return 0
        if command == "start":
            metadata = start_local_slskd(non_interactive=non_interactive, explicit_share_dir=share_dir)
            web_url = str(metadata.get('web_url', '(unknown)'))
            print(f"Local slskd started at {web_url}")
            return 0
        if command == "status":
            print_status()
            return 0
    except SlskdBootstrapError as exc:
        print(f"slskd bootstrap error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive user-facing boundary
        print(f"Unexpected slskd bootstrap error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
